# nsfc-proposal 第二轮改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 nsfc-proposal 写出的申请书更接近中标书：立项依据可以新增已核验的引用，年度计划按项目类型定年数，研究内容自动配研究框架图与各研究的设计图，写法规则补上检验力、对照与否证的要求，并修几处运行中暴露的小缺陷。

**Architecture:** 改动分布在四个 skill：nsfc-justification-writer（写作提示词）、nsfc-research-content-writer（年数、风险词）、nsfc-proposal（出图脚本、写法规则、一致性检查）、research-literature-search（摘要补全遇到额度用尽时跳过该服务）。出图沿用团队 graphical-abstract-generator 的调用方式：同一网关、同一套凭据，网关地址从环境变量读取，仓库中不出现域名。

**Tech Stack:** Python 3 标准库、PyYAML、requests；pytest（unittest 风格）；LaTeX（graphicx，已由模板加载）。

**Spec:** `docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md`。本轮新增要求来自申请人 2026-10-10 在对话中的决定，记录如下：

- 立项依据可以新增引用，以实际引用信息为准。
- 面上项目的年度计划不得写死为三年。
- 出图使用 graphical-abstract-generator 调用生图模型的方式。
- 生图网关地址读环境变量 `WISMODEL_IMAGE_URL`，域名不进仓库。
- 每次运行出研究框架图 1 张，每项研究内容各 1 张设计图，尺寸 2K，自检不合格最多重画 2 次。
- 用户材料上传 WisDoc 不需要先问（自建服务）。
- 网页版本轮不动。

## Global Constraints

- 分支 `nsfc-proposal`，远程 `lauorie`（git@github.com:Lauorie/guoziran.git）。每个任务结束不推送，由控制者在终审后统一推送。
- 不新增必需的第三方依赖：只用标准库、PyYAML、requests。
- 脚本用 `Path(__file__).resolve()` 定位 skill 资产；文件读写显式 `encoding="utf-8"`。
- 输出路径限制在 project_root（P）或任务目录（T，目录名以 `task-` 开头且父目录名为 `.bensz-api`）内；越界报错，退出码 2。
- 仓库中不得出现本机用户目录的绝对路径和团队服务的域名；检查用的 `git grep` 模式由控制者在派发任务时给出，不写进仓库。
- 凭据（`WISMODEL_API_KEY` 等）和网关地址不得出现在标准输出、日志、异常信息、索引文件或测试快照中。
- 对用户与正文中，生图服务一律称「WisImage」，不写底层模型名。
- 正文占位格式固定为 `【待补充：……】`；内部编号（G1、Q1、T1、S1 等）不进正文。
- HTTP 请求不附带个人邮箱或身份信息。
- 版本号不再改动（本分支的版本已经提升且尚未发布）：nsfc-proposal 0.1.0、nsfc-justification-writer 1.4.0、nsfc-research-content-writer 1.1.0、research-literature-search 1.1.0。改动记入各自 CHANGELOG 的现有版本段落，BAC 行仍在段落最后；根 `CHANGELOG.md` `[Unreleased]` 同步一句。
- 测试放 `tests/<skill名>/`，unittest 风格，文件名全仓唯一（带 skill 缩写前缀）。测试不联网，产物写系统临时目录。测试命令（仓库根目录）：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider -W ignore::pytest.PytestConfigWarning tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/research-literature-search`
- 提交信息 `<type>(<skill>): <中文摘要>`，末尾附 `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`（写实际完成提交的模型）。每次提交前测试 0 failed；`find skills tests -name __pycache__ -o -name .pytest_cache` 无输出。
- 文档风格：短句，少副词，不写宣传用语。

## Review Focus

1. 项目类型写法五花八门（「国家自然科学基金面上项目」「青年科学基金项目（C类）」「地区基金」、空字符串）：年数按关键词匹配，匹配不到时取默认 3 年并在 assumptions.md 记一条。测试在 Task 2。
2. 生图服务返回 200 但没有图片、返回的不是图片字节、或返回巨大的数据：报失败，不写坏文件，正文保留占位。测试在 Task 3。
3. 凭据缺失或 `.env` 行尾带注释：在发出请求前报「未配置」，不把空 token 或带注释的地址发出去，信息里不含值。测试在 Task 3。
4. 正文 `\includegraphics` 指向不存在的文件（重画后改了文件名、图被删）：一致性检查报错，不等到编译才发现。测试在 Task 3。
5. 摘要补全时某个服务当日额度用尽（429 且 Retry-After 很长）：本次运行不再请求它，其余服务照常，汇总写明。测试在 Task 4。

---

### Task 1: 立项依据的写作提示词允许新增已核验的引用

nsfc-justification-writer 的 `coach` 输出一段「可直接复制的写作提示词」，其中写着「不新增引用」「不修改任何标题层级」。nsfc-proposal 第 6.1 步要求新增 `\subsubsection`（科学技术价值）并引用已入 `.bib` 的文献，两边冲突。funded-1 运行按 6.1 执行，没有出问题；换一次运行照提示词写，立项依据就会少引文献。

**Files:**
- Modify: `skills/nsfc-justification-writer/scripts/core/writing_coach.py`（`_copyable_prompt` 第 99–125 行附近，第 134 行附近的 skeleton/draft 任务说明）
- Modify: `skills/nsfc-justification-writer/references/tier2_semantic_review.md:23`
- Modify: `skills/nsfc-justification-writer/SKILL.md:90`（只在必要时改措辞，保持「不新增无法核验的引用」的意思）
- Modify: `skills/nsfc-justification-writer/CHANGELOG.md`（1.4.0 段）
- Create: `tests/nsfc-justification-writer/test_njw_coach_prompt.py`

**Interfaces:**
- Consumes: 无。
- Produces: `_copyable_prompt(stage=..., style_preamble=...)` 的输出不再含「不新增引用」「不修改任何标题层级」。

- [ ] **Step 1: 写失败的测试**

```python
"""coach 提示词：可以新增已核验的引用，可以新增配置允许的标题。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "nsfc-justification-writer" / "scripts"))

from core.writing_coach import _copyable_prompt  # noqa: E402

STAGES = ("skeleton", "draft", "revise", "polish", "final", "auto")


class CoachPromptTest(unittest.TestCase):
    def test_no_stage_forbids_new_citations(self):
        for stage in STAGES:
            text = _copyable_prompt(stage=stage, style_preamble="")
            self.assertNotIn("不新增引用", text, stage)
            self.assertNotIn("不修改任何标题层级", text, stage)

    def test_new_citations_must_be_verified(self):
        text = _copyable_prompt(stage="draft", style_preamble="")
        self.assertIn("可以新增引用", text)
        self.assertIn(".bib", text)
        self.assertIn("引用台账", text)

    def test_headings_follow_config(self):
        text = _copyable_prompt(stage="draft", style_preamble="")
        self.assertIn("allowed_new_heading_commands", text)


if __name__ == "__main__":
    unittest.main()
```

先确认 `core.writing_coach` 的导入路径与现有测试（`tests/nsfc-justification-writer/test_njw_change_guard.py`）一致，不一致时照现有测试的写法改导入。

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-justification-writer/test_njw_coach_prompt.py`
Expected: FAIL（提示词仍含「不新增引用」）

- [ ] **Step 3: 改提示词**

`_copyable_prompt` 的约束改为下面几行（替换原「不修改任何标题层级」「不新增引用」两行）：

```python
        + "- 保留现有标题；需要时可新增 config.yaml 中 allowed_new_heading_commands 允许的标题命令（如 \\subsubsection）\n"
        + "- 可以新增引用：只引用已检索核验、已写入项目 .bib 且在引用台账（proposal/citation_ledger.jsonl）中有记录的文献；表述以该文献的实际信息（摘要或全文）为准，不夸大\n"
        + "- 没有可核验文献支持的论断，改写为有边界的表述并记录待核验项\n"
```

各阶段的 `focus` 去掉括号中的「不新增引用」：draft 写「只写自动确定的正文范围段落；新增引用须符合上面的核验要求」；revise 写「……修复逻辑跳跃与不可核验表述」；polish 写「先在内部锁定论证、事实和引用，再按专业可读性准则润色语言（不删除必要术语或限定）」；final 写「按 DoD 做最终自检：结构/字数/引用/术语一致性」。第 134 行附近「不新增标题或环境」改为「只新增 allowed_new_heading_commands 允许的标题，不新增环境」。

`tier2_semantic_review.md:23` 改为：「不新增事实、实验结果、研究对象细节或绝对化结论；新增文献只能是已写入 .bib 并在引用台账中有记录的条目，表述不超出其摘要或全文。」

- [ ] **Step 4: 运行，确认通过**

Run: 全局约束中的测试命令。Expected: 0 failed。

- [ ] **Step 5: 提交**

```bash
git add skills/nsfc-justification-writer tests/nsfc-justification-writer/test_njw_coach_prompt.py CHANGELOG.md
git commit -m "fix(nsfc-justification-writer): 写作提示词允许新增已核验的引用"
```

CHANGELOG 1.4.0 段补一句：「coach 提示词不再禁止新增引用：只要文献已核验、已入 .bib 并在引用台账中有记录即可引用；不再禁止新增配置允许的标题（来源：申请人 2026-10-10 决定）。」

---

### Task 2: 年度计划按项目类型定年数；「首次」不再误报

面上项目执行期 4 年，nsfc-research-content-writer 的模板、信息表、检查脚本和 NSFC_General 模板说明都写死为三年。检查脚本还把「首次测试前」「首次到实验室」当作宣传用语报出。

**Files:**
- Modify: `skills/nsfc-research-content-writer/config.yaml`（新增 `yearly_plan` 段；`quality_contract.yearly_plan_must_include` 第一条改为「按研究期限分年任务（不跨年）」；`checks.risk_phrases` 中的「首次」改为短语列表）
- Modify: `skills/nsfc-research-content-writer/scripts/check_project_outputs.py`
- Modify: `skills/nsfc-research-content-writer/SKILL.md`（第 71、93 行附近）、`references/yearly_plan_template.md`、`references/output_skeletons.md`、`references/info_form.md`（第 10 项）、`references/dod_checklist.md`、`references/anti_patterns.md`
- Modify: `skills/nsfc-proposal/scripts/case_render.py`（第 209 行附近信息表第 10 项）
- Modify: `skills/nsfc-proposal/SKILL.md`（6.2 一句）
- Modify: `projects/NSFC_General/AGENTS.md:18,56`（三年 → 四年）；`projects/NSFC_Local/AGENTS.md`（若有「三年」字样，改为四年）。`NSFC_Young` 保持三年。
- Modify: 两个 skill 的 CHANGELOG
- Test: `tests/nsfc-research-content-writer/test_nrcw_years.py`（新建）、`tests/nsfc-proposal/test_np_render.py`（追加）

**Interfaces:**
- Produces（nsfc-research-content-writer）：`scripts/plan_years.py`，函数 `duration_years(project_type: str, config_path: Path | None = None) -> tuple[int, bool]`，返回（年数, 是否命中关键词）。`check_project_outputs.py` 新增参数 `--years N` 与 `--project-type TEXT`（二选一；都不给时默认 3）。
- Consumes（nsfc-proposal）：`case_render.py` 通过 `SK/nsfc-research-content-writer/scripts/plan_years.py` 计算年数（用 importlib 按路径加载，不改 sys.path 的全局状态）。

`config.yaml` 新增（年数表只此一处）：

```yaml
yearly_plan:
  # 按项目类型中的关键词定研究期限（年）；按顺序匹配，先命中先用。匹配不到时用 default_years，并提示记入 assumptions.md。
  duration_by_keyword:
    - [重点, 5]
    - [面上, 4]
    - [地区, 4]
    - [青年, 3]
  default_years: 3
  max_years: 5
```

`checks.risk_phrases` 中的「首次」换成：`首次提出`、`首次发现`、`首次实现`、`首次揭示`、`首次构建`、`首次建立`、`国内首次`、`国际首次`、`世界首次`。其余风险词不变。检查脚本只按列表匹配，不再匹配单独的「首次」。

- [ ] **Step 1: 写失败的测试**

```python
"""研究期限按项目类型取年数；年度计划检查按年数核对；「首次」不误报。"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "nsfc-research-content-writer"
CHECKER = SKILL / "scripts" / "check_project_outputs.py"


def _load_plan_years():
    spec = importlib.util.spec_from_file_location("plan_years", SKILL / "scripts" / "plan_years.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DurationYearsTest(unittest.TestCase):
    def test_keywords(self):
        py = _load_plan_years()
        cases = {
            "国家自然科学基金面上项目": (4, True),
            "面上项目": (4, True),
            "青年科学基金项目（C类）": (3, True),
            "地区科学基金项目": (4, True),
            "重点项目": (5, True),
            "": (3, False),
            "联合基金": (3, False),
        }
        for text, expected in cases.items():
            self.assertEqual(py.duration_years(text), expected, text)


def _project(tmp: Path, yearly: str) -> Path:
    (tmp / "extraTex").mkdir()
    (tmp / "extraTex" / "2.1.研究内容.tex").write_text("\\subsubsection{研究内容}\n研究内容正文。\n", encoding="utf-8")
    (tmp / "extraTex" / "2.2.特色与创新.tex").write_text("创新正文。\n", encoding="utf-8")
    (tmp / "extraTex" / "2.3.年度研究计划.tex").write_text(yearly, encoding="utf-8")
    return tmp


FOUR_YEARS = "".join(f"\\textbf{{第{i}年}}：任务{i}。\n" for i in range(1, 5))
THREE_YEARS = "".join(f"\\textbf{{第{i}年}}：任务{i}。\n" for i in range(1, 4))


class CheckerYearsTest(unittest.TestCase):
    def run_checker(self, root: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CHECKER), "--project-root", str(root), *extra],
                              capture_output=True, text=True, encoding="utf-8")

    def test_general_requires_fourth_year(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), THREE_YEARS)
            res = self.run_checker(root, "--project-type", "面上项目")
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("第4年", res.stdout + res.stderr)

    def test_general_four_years_passes(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), FOUR_YEARS)
            res = self.run_checker(root, "--project-type", "面上项目")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_young_default_three_years(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), THREE_YEARS)
            res = self.run_checker(root)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_extra_year_beyond_duration_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), FOUR_YEARS)
            res = self.run_checker(root, "--years", "3")
            self.assertIn("第4年", res.stdout + res.stderr)

    def test_shouci_plain_usage_not_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), THREE_YEARS)
            (root / "extraTex" / "2.1.研究内容.tex").write_text("被试首次测试前完成问卷。本研究首次提出该框架。\n", encoding="utf-8")
            res = self.run_checker(root)
            out = res.stdout + res.stderr
            self.assertIn("首次提出", out)
            self.assertNotIn("'首次'", out)


if __name__ == "__main__":
    unittest.main()
```

先读 `check_project_outputs.py` 现有的内容检查（例如 2.1 需要的最少内容），让测试项目满足它们；必要时给测试项目加最少的内容。超出研究期限的年份按 WARN 还是 ERROR 处理，按现有脚本对「缺年份」的处理方式定，并在报告中说明。

`tests/nsfc-proposal/test_np_render.py` 追加：项目类型为「面上项目」时，content-writer 信息表第 10 项写「研究期限 4 年」并要求分 4 年；类型为空时写 3 年，并出现一句「项目类型未写明，按 3 年」。

- [ ] **Step 2: 运行，确认失败**

- [ ] **Step 3: 实现**
  - 新建 `plan_years.py`：读 `config.yaml` 的 `yearly_plan`（PyYAML），按顺序匹配关键词，返回 `(years, matched)`；年数超出 `1..max_years` 时报配置错误。
  - `check_project_outputs.py`：`--years`、`--project-type` 互斥；年份检查从固定的第 1–3 年改为第 1–N 年，各年接受「第N年」「第 N 年」「第一年……第五年」写法；出现第 N+1 年时报出。风险词按新列表匹配。
  - `case_render.py` 第 10 项改为「**研究期限与分年硬约束**：研究期限 N 年（项目类型：X）；按 N 年分年度写，不跨年」，类型匹配不到时追加「项目类型未写明，按 3 年；请在 assumptions.md 记一条 AI 拟定项」。
  - 文档中的「三年」改为「按研究期限（N 年）」，示例写四年时注明面上项目；`yearly_plan_template.md` 增加第四年、第五年的写法说明（「研究期限为 4 年或 5 年时照此增加」）。
  - nsfc-proposal SKILL.md 6.2 加一句：「检查脚本加 `--project-type "<项目类型>"`；研究期限以 content-writer 的 `yearly_plan` 表为准。」

- [ ] **Step 4: 运行全局测试命令，0 failed**

- [ ] **Step 5: 提交（两次）**

```bash
git commit -m "fix(nsfc-research-content-writer): 年度计划按项目类型定年数，「首次」只拦宣传说法"
git commit -m "fix(nsfc-proposal): 信息表按项目类型写研究期限"
```

---

### Task 3: 自动出图（研究框架图与各研究的设计图）

中标书有 6 张图：研究框架图 1 张，各研究的设计图 5 张。funded-1 只有 1 处框架图占位，评审因此扣分。本任务沿用 graphical-abstract-generator 调用生图模型的方式：同一网关接口、同一套凭据、同样的请求体，新增出图脚本、作图说明，并在 6.2 中把图放进正文。

调用方式（照 graphical-abstract-generator 的 `scripts/generate_image.py`；该文件在团队 skill 目录中，实现者可以读，但不复制其中的域名）：

- POST 到 `WISMODEL_IMAGE_URL`（完整接口地址，从环境变量或 `.env` 读）。
- 请求头：`Authorization: Bearer <WISMODEL_API_KEY>`、`Content-Type: application/json`、`X-Channel: qiewenclaw`、`x-req-location: <DEPLOY_REGION>`、`Accept-Encoding: identity`、`User-Agent: nsfc-proposal-figures/0.1`。
- 请求体：`{"model": <figures.model>, "messages": [{"role": "user", "content": <prompt>}], "modalities": ["image", "text"], "max_tokens": 16000, "image_config": {"aspect_ratio": ..., "image_size": ...}}`。
- 不走环境中的代理：`proxies={"http": None, "https": None}`。
- 响应：`choices[0].message.images[0].image_url.url` 是 `data:image/...;base64,...`，解码后写 PNG。
- 超时 300 秒；5xx 与网络错误重试 1 次，间隔 3 秒；4xx 立即失败（402 记「额度不足」）。

**Files:**
- Create: `skills/nsfc-proposal/scripts/figures.py`
- Create: `skills/nsfc-proposal/references/figure_guide.md`
- Modify: `skills/nsfc-proposal/config.yaml`（新增 `figures` 段）
- Modify: `skills/nsfc-proposal/scripts/consistency_check.py`（新增 `missing_figure_file`）
- Modify: `skills/nsfc-proposal/SKILL.md`（输入、第 6.2 步、第 7 步、第 8 步、失败与恢复、输出管理）
- Modify: `skills/nsfc-proposal/references/section_boundaries.md:8,38`（占位改为「出图失败时的占位」）
- Modify: `skills/nsfc-proposal/README.md`、`CHANGELOG.md`
- Test: `tests/nsfc-proposal/test_np_figures.py`（新建）、`tests/nsfc-proposal/test_np_consistency.py`（追加）

**Interfaces:**
- Produces：`python3 S/scripts/figures.py render --project-root P --task-root T --prompt-file <T 下的文件> --name <名称> [--aspect-ratio 1:1|16:9|9:16|21:9] [--image-size 1K|2K|4K] [--force]`。
  - 成功：写 `P/figures/nsfc-proposal/<名称>.png`；提示词副本写 `T/nsfc-proposal/output/figures/<名称>.prompt.md`；索引 `T/nsfc-proposal/output/figures/index.json` 追加一条 `{"name", "png", "prompt", "aspect_ratio", "image_size", "sha256", "status": "ok", "bytes", "created"}`（路径相对 P 或 T）；标准输出一行 `已生成 figures/nsfc-proposal/<名称>.png`；退出码 0。
  - 未配置（缺 `WISMODEL_IMAGE_URL`、`WISMODEL_API_KEY` 或 `DEPLOY_REGION`；或地址含空白或 `#`；或不是 https/http 地址）：不发请求，索引记 `status: "not_configured"`，退出码 3。
  - 生成失败：索引记 `status: "failed"` 与类别（`http_4xx`、`credit`、`http_5xx`、`network`、`no_image`、`bad_image`、`too_large`），退出码 1，不写 PNG。
  - 参数或路径错误：退出码 2。
  - `--name` 须匹配 `^[a-z0-9][a-z0-9_-]{0,47}$`；目标 PNG 已存在且没加 `--force` 时退出码 2（重画用新名称，如 `fig1-framework-v2`）。
- Produces（consistency_check）：errors 新增 `missing_figure_file`，`detail` 写文件与 `\includegraphics` 的参数；`LABELS` 补「图片文件不存在」。

`config.yaml` 新增：

```yaml
figures:
  enabled: true
  model: google/gemini-3.1-flash-image   # 生图模型；对用户与正文一律称 WisImage
  image_size: 2K                          # 1K / 2K / 4K
  framework_aspect_ratio: "1:1"           # 研究框架图
  design_aspect_ratio: "16:9"             # 各研究的设计图
  max_rerenders: 2                        # 自检不合格时最多重画次数
  timeout_s: 300
  max_image_bytes: 31457280               # 30 MB
```

凭据与地址的查找顺序与 `wisdoc_client.py` 相同：已有环境变量 → 当前目录及各级父目录的 `.env` → project_root 及各级父目录的 `.env` → skill 目录；只读需要的三个键；未加引号的值在 ` #` 处截断。可以把 `wisdoc_client.py` 中的 `.env` 读取函数提到一个小的共享模块（例如 `scripts/envfile.py`）供两者使用；若这样做，`wisdoc_client.py` 的行为与测试不变。

- [ ] **Step 1: 写失败的测试**（`tests/nsfc-proposal/test_np_figures.py`，替换 `requests.post`，不联网）

必须覆盖的用例：

1. 成功：假响应返回一张 1×1 PNG 的 data URL → 退出码 0；PNG 写到 `P/figures/nsfc-proposal/fig1-framework.png`，内容以 `\x89PNG` 开头；提示词副本与 index.json 存在；请求体的 `image_config` 为 `{"aspect_ratio": "1:1", "image_size": "2K"}`；请求头含 `X-Channel: qiewenclaw` 与 `User-Agent: nsfc-proposal-figures/0.1`。
2. 未配置：清空三个变量（测试内用 `mock.patch.dict(os.environ, ..., clear=False)` 删除并阻止读到本机 `.env`，例如把 cwd 和 project_root 放进临时目录）→ 退出码 3，`requests.post` 未被调用，index 记 `not_configured`。
3. `.env` 行尾注释：`WISMODEL_IMAGE_URL=https://gw.example.test/img  # 注释` → 截断后正常使用；地址含 `#` 而无空格时报未配置。
4. 4xx：返回 400 → 退出码 1，只调用 1 次；返回 402 → 类别 `credit`。
5. 5xx 后成功：第一次 502，第二次成功 → 退出码 0，调用 2 次（`sleep` 可注入，测试中不真睡）。
6. 200 但没有图片（`images` 为空，`content` 为拒绝文字）→ 退出码 1，类别 `no_image`，不写 PNG。
7. data URL 解码后不是 PNG/JPEG/WebP 魔数 → `bad_image`；超过 `max_image_bytes` → `too_large`。
8. 名称非法（`../x`、`Fig1`）→ 退出码 2；目标已存在且无 `--force` → 退出码 2；`--prompt-file` 不在 T 下 → 退出码 2。
9. 机密不外泄：设置哨兵 token `sk-SENTINEL-123` 与哨兵地址 `https://gw.sentinel.test/img`，在成功、失败、未配置三种情况下，捕获 stdout、stderr、logging 输出和 index.json，断言都不含哨兵 token 与哨兵主机名。
10. 一致性检查：正文 `\includegraphics[width=\linewidth]{figures/nsfc-proposal/fig9.png}` 而文件不存在 → errors 含 `missing_figure_file`、退出码 1；文件存在 → 无该错误；不写扩展名时按 `.png`、`.pdf`、`.jpg` 依次查找；注释掉的 `\includegraphics` 不检查。

- [ ] **Step 2: 运行，确认失败**

- [ ] **Step 3: 实现 `figures.py`**（结构建议，函数名照此，便于测试注入）

```python
def load_settings(project_root: Path) -> ImageSettings: ...          # 读三个键，校验地址；缺失抛 FiguresNotConfigured（信息不含值）
def build_payload(prompt: str, model: str, aspect: str, size: str) -> dict: ...
def call_gateway(settings, payload, *, post=requests.post, sleep=time.sleep, timeout=300) -> dict: ...
def extract_image(result: dict, max_bytes: int) -> bytes: ...        # 校验魔数与大小，失败抛 FigureError(category)
def render(project_root, task_root, prompt_file, name, aspect, size, force, *, post=..., sleep=...) -> int: ...
```

日志只写类别和字节数，不写地址、token、响应正文中的长文本（拒绝文字截取前 200 字，且先删去其中的 URL）。

- [ ] **Step 4: 写 `references/figure_guide.md`**（自拟措辞，不复制中标书的句子）。内容：

  1. **何时出图**：第 5 步之后、写 2.1 之前。框架图 1 张，每项研究内容 1 张设计图。`figures.enabled` 为 false 或脚本返回 3 时不出图，正文保留占位。
  2. **先写 Figure Brief**（内部）：图的目的、必须出现的对象、分区、连接关系、可见文字清单。所有可见文字取自 `scientific_case.yaml` 的术语、研究内容名称、科学问题的短写，每个标签不超过 12 个汉字，全图不超过 30 个标签。数字只写科学论证与研究方案中已经确定的样本量、时长。
  3. **提示词写法**：用中文写；第一段说明这是「国家自然科学基金申请书正文中的科研示意图，白底、扁平矢量风格、配色不超过 4 种、无照片、无真人面孔、无商标、无水印」。随后按分区（ZONE 1、ZONE 2……）写结构，再写连接，最后写可见文字规则：「图中所有可见文字只能使用以下内容：……；ZONE 等结构词不得画成文字；不得出现英文、拼音或其他汉字」。
  4. **研究框架图的结构**：顶栏写核心科学问题；下面按研究内容一至 N 自上而下分 N 块面板，每块写研究名称、所含任务或实验（用箭头表示先后）、底栏写预期发现；左侧一条纵线把各块串起来，标出前一项研究的产出如何进入下一项；每块面板的颜色不同。画幅取 `figures.framework_aspect_ratio`。
  5. **设计图的结构**：(A) 条件示意：各组或各条件一格，用图标表示操纵；(B) 流程时间轴：各阶段一段，写明时长，阶段之间画出休息或基线段；(C) 测量：写明测量对象与部位（如近红外通道覆盖的脑区、行为编码的事件类型）。只画该研究方案中写明的内容。画幅取 `figures.design_aspect_ratio`。
  6. **自检**：用 Read 读 PNG，逐条核对：没有乱码或错字；每个可见标签都在可见文字清单中；分区与研究内容的数量、顺序一致；数字与研究方案一致。不合格时缩短或减少标签，改写提示词，用新名称（`-v2`、`-v3`）重画，最多 `figures.max_rerenders` 次；仍不合格时不用这张图，正文保留占位，在 `stages.md` 记录原因。
  7. **放进正文**：给 nsfc-research-content-writer 的约束中写明每张图的路径、图注与标签。框架图放在 2.1 开头；设计图放在对应研究内容的「设计」小标题下。写法：

     ```latex
     \begin{figure}[htbp]
       \centering
       \includegraphics[width=0.95\textwidth]{figures/nsfc-proposal/fig1-framework.png}
       \caption{研究框架。}
       \label{fig:np-framework}
     \end{figure}
     ```

     正文用「如图~\ref{fig:np-framework}所示」引用，不写死图号。
  8. **核对与声明**：每张图在 `assumptions.md`「## 待核实项」各记一条（「图 X 由 AI 生成，请核对内容与标签」）；AI 使用说明写明「研究框架图与设计图由 WisImage 根据科学论证生成，经 AI 自检，申请人核对」，不写模型名。

- [ ] **Step 5: 改 SKILL.md**
  - 输入：可选项加「生图服务凭据（`WISMODEL_IMAGE_URL`、`WISMODEL_API_KEY`、`DEPLOY_REGION`，环境变量或 `.env`）；没有时不出图，保留占位」。
  - 6.2 开头加「出图」一段：按 `references/figure_guide.md` 写提示词，存为 `T/nsfc-proposal/output/figures/<名称>.prompt.txt`，逐张运行 `figures.py render`（前台运行，Bash 超时 600000 ms），读图自检；把通过自检的图的路径、图注、标签写进给 nsfc-research-content-writer 的约束。原「研究内容开头放一处可见占位」改为「出图失败或未配置时，才放占位」。
  - 第 7 步：`missing_figure_file` 的处理（文件名对不上时改正文中的路径，不改文件名去迁就）。
  - 第 8 步：收尾报告列出生成的图与重画次数；AI 使用说明写 WisImage。
  - 失败与恢复：未配置（退出码 3）→ 保留占位，报告写明；额度不足（`credit`）→ 停止出图，保留占位；`no_image`、`bad_image` → 改写提示词换名重画，计入重画次数。
  - 输出管理：`P/figures/nsfc-proposal/` 是本 skill 的写入目录，加入允许写入的目录列表（`config.yaml` 的 `guardrails.allowed_write_dirs`，若该键存在）。

- [ ] **Step 6: `consistency_check.py` 加 `missing_figure_file`**：在去注释、跨行拼接后的文本上匹配 `\includegraphics(\[[^\]]*\])?\{([^}]*)\}`，路径相对 P 解析，必须仍在 P 内（越界也报 `missing_figure_file`）；无扩展名时依次试 `.png`、`.pdf`、`.jpg`、`.jpeg`。

- [ ] **Step 7: 运行全局测试命令，0 failed；按派发时给出的模式 `git grep` 团队服务域名，无输出**

- [ ] **Step 8: 提交（两次）**

```bash
git commit -m "feat(nsfc-proposal): 用 WisImage 生成研究框架图与设计图"
git commit -m "docs(nsfc-proposal): 6.2 先出图再写研究内容"
```

---

### Task 4: 写法规则与小缺陷

**Files:**
- Modify: `skills/nsfc-proposal/SKILL.md`（规则 5、第 3 步）
- Modify: `skills/nsfc-proposal/references/scientific_case_guide.md`（第 9 步）、`references/section_boundaries.md`（研究内容部分）、`references/evidence_wording.md`（政策文件）
- Modify: `skills/nsfc-proposal/scripts/bib_resolve.py`（第 391 行附近）
- Modify: `skills/research-literature-search/scripts/search_runner.py`（`enrich_abstracts`，第 437–487 行）
- Modify: 相关 CHANGELOG
- Test: `tests/research-literature-search/`（追加到现有 enrich 测试文件，或新建 `test_rls_enrich_exhausted.py`）、`tests/nsfc-proposal/test_np_bib_resolve.py`（追加）

**Interfaces:**
- Produces：`enrich_abstracts(...)` 的汇总新增 `"exhausted_providers": [...]`；`bib_resolve.run(..., dry_run=True)` 写 `bib_resolve.dryrun.json`，不动 `bib_resolve.json`。

**4a 摘要补全：服务额度用尽后跳过。** 某个服务在重试用尽后仍以 429 失败时，本次运行把它记为额度用尽，后面的记录不再请求它；该记录的 `attempts` 记 `{"source": ..., "status": "skipped_exhausted"}`；汇总写 `exhausted_providers`。判断 429：`status_code` 属性、`response.status_code` 或错误信息中的 HTTP 429（复用 `_RETRYABLE_STATUS` 的写法，单独判断 429）。

测试：
1. 假 fetcher：`openalex` 对第一条抛出 429，`semantic_scholar` 正常 → 处理三条记录后 `openalex` 只被调用 `retries + 1` 次，汇总 `exhausted_providers == ["openalex"]`。
2. 500 用尽重试后不记为额度用尽，下一条仍请求。

**4b bib_resolve `--dry-run`**：dry-run 时汇总写 `bib_resolve.dryrun.json`；SKILL.md 中 `--dry-run` 的说明同步改。测试：先正常运行一次写出 `bib_resolve.json`，再 dry-run，前者内容不变，后者出现。

**4c 写法规则（文档）**：

- **政策文件**（规则 5 与 `evidence_wording.md`）：国家或部门的政策文件、课程标准、行业指南，联网到发文机关的官方网站核对文件名、发文机关与年份后，可在正文写明，如「《中小学综合实践活动课程指导纲要》（教育部，2017）」，不进 `.bib`，网址与核对日期记入 `literature_leads.md` 的「## 官方文件」。核对不到的不写，按背景类论断处理。正文只写文件明文规定的内容。
- **摘要补全失败**（第 3 步）：`enrich-abstracts` 的汇总 `filled / attempted` 低于一半，或出现 `exhausted_providers` 时，背景类论断也可以写成论断问句检索，以拿到带完整摘要的记录；在 `stages.md` 记录这一偏离及原因。
- **检验力**（`scientific_case_guide.md` 第 9 步与 `section_boundaries.md`）：
  - 效应量与自由度要和实际检验的模型一致（层级回归按新增的预测变量个数算）。
  - 以班级或学校为单位分组的研究，要计入聚类（设计效应或多层模型的检验力），写明组内相关系数的假设。
  - 写出最小可检测效应后，与所引文献报告的效应量比较；最小可检测效应更大时，写明这一比较的检验力不足，或增加样本，或把它降为次要分析。
- **对照与基线**（`section_boundaries.md` 研究内容部分，各研究的「设计」）：
  - 采集神经或生理信号时，各任务阶段之间设静息或低负荷基线，写明时长。
  - 操纵可能带来非特异效应（如动作本身、操作时长、新奇感）时，设一个排除这一效应的对照条件，例如「照样制作」。
  - 这两条只在研究涉及相应测量时适用，不强加给数据驱动研究。
- **否证条件**（`scientific_case_guide.md`）：每个分假设各写一条可单独判定的否证条件。核心假设的判定不得要求「几项同时失败」才算不成立。
- 以上规则的示例用通用写法自拟，不复制中标书的句子。

- [ ] **Step 1–2：写 4a、4b 的失败测试，运行确认失败**
- [ ] **Step 3：实现 4a、4b；改 4c 文档**
- [ ] **Step 4：运行全局测试命令（含 `test_np_skill_docs.py`），0 failed**
- [ ] **Step 5：提交（三次）**

```bash
git commit -m "fix(research-literature-search): 摘要补全遇到额度用尽的服务后跳过它"
git commit -m "fix(nsfc-proposal): bib_resolve 试运行不覆盖汇总文件"
git commit -m "docs(nsfc-proposal): 补政策文件、检验力、对照与否证的写法"
```

---

### Task 5: 验证运行 funded-2（控制者安排，不改代码）

在 Task 1–4 合并后，用 `input_funded.md` 重新在线运行一次 nsfc-proposal（运行目录 `<eval-dir>/funded-2`，模板 NSFC_General，全自动）。运行代理不得读取中标书原件及 `funded-comparison.md`。

核对：

- 是否生成框架图与各研究的设计图，自检与重画次数。
- 年度计划是否为 4 年。
- 立项依据引用的不同文献数与 funded-1 相比是否减少。
- 是否写明政策文件。
- 检验力是否计入聚类、是否做了最小可检测效应的比较。
- `audit` 与 `consistency_check` 是否清零。

结果写进 `funded-comparison.md` 新的一节，不重做盲评（是否重做由申请人决定）。之后按 SDD 做整个第二轮的终审，终审通过后推送 `lauorie/nsfc-proposal`。
