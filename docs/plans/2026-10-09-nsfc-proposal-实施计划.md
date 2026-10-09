# nsfc-proposal 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本仓库 fork 中新建 `nsfc-proposal`，以 nsfc-* 写作 skill 为主线，并入 nsfc-writer 的科学论证、证据图谱和章节分工，接入 wispaper 检索，修复写作 skill 的已知缺陷，并用肺结节示例完成验收。

**Architecture:** `nsfc-proposal` 是编排型 skill：脚本只做确定性工作（建骨架、校验、生成信息表、补全文献元数据、一致性扫描），语义工作由宿主 AI 按 `SKILL.md` 执行。三份共享文件放在 `{project_root}/proposal/`，三个写作 skill 读取它们；没有这些文件时，写作 skill 保持原有行为。wispaper 的结果通过 `research-literature-search run --host-results` 填进预留的 `mcp` 检索源位置。

**Tech Stack:** Python 3.12（本机 3.12.3，上游要求 ≥3.11）、PyYAML 6.0.1、requests 2.31.0、unittest + pytest 9.0.2、LaTeX（项目自带 `scripts/nsfc_build.py`）。

**Spec:** `docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md`（下称「设计文档」）。执行者需同时阅读设计文档和本计划。

## Global Constraints

- 分支：`nsfc-proposal`。不推送远程；推送需申请人另行确认。
- 不新增第三方依赖；只用标准库、PyYAML、requests。
- 脚本用 `Path(__file__).resolve()` 定位 skill 自身资产；不依赖当前工作目录定位 skill 资产；文件读写显式 `encoding="utf-8"`。
- 用户给出的路径必须限制在 `project_root` 内（越界报错，退出码 2）。
- 正文占位格式固定为 `【待补充：……】`，写在正文中，不写成 LaTeX 注释。
- 内部编号（`G1`、`Q1`、`T1`、`C1`、`S1` 等）不得进入正文。
- 措辞强度：`multi_verified` → 可写「多项研究表明」；`single_verified` → 只写「有研究报道」；`unsupported` → 不写成事实；`applicant_material` → 按材料原样写。线索（`lead:`）和摘要片段不能作为支持证据。
- HTTP 请求不附带个人邮箱或其他身份信息；User-Agent 固定为 `nsfc-proposal-bib-resolve/0.1`。
- 版本只改 `config.yaml:skill_info.version`：nsfc-proposal `0.1.0`；nsfc-justification-writer `1.3.0 → 1.4.0`；nsfc-research-content-writer `1.0.0 → 1.1.0`；nsfc-research-foundation-writer `0.1.2 → 0.2.0`；research-literature-search `1.0.4 → 1.1.0`；nsfc-abstract `2.1.2 → 2.1.3`。仓库版本号和 Git tag 不动。
- `metadata.author`：nsfc-proposal 写 `Lauorie`；改动的现有 skill 保持 `Bensz Conan`。
- BAC 已由负责人豁免：每个改动 skill 的 `CHANGELOG.md` 新版本段落和根 `CHANGELOG.md` 条目末尾写「本分支未写 BAC 记录，经负责人同意。」
- 测试放 `tests/<skill名>/`，unittest 风格，文件名全仓唯一（加 skill 缩写前缀）。从仓库根目录运行：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider <路径>`。测试产物写系统临时目录，不写 `tests/` 或 skill 目录。
- 提交信息：`<type>(<skill>): <中文摘要>`，type 取 feat/fix/docs/test；末尾附 `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`。
- `SKILL.md` 的公共约束块从 `docs/templates/skill-common-constraints.md` 第 2 行（`### 公共硬约束`）逐字复制到末行（`<!-- End of canonical common constraints. -->`）。

## Review Focus

1. **`\bibliography` 写在被 `\input` 的文件里，或一次列多个 bib**（`projects/NSFC_Young` 把它放在 `references/reference.tex`）：`bib_targets` 必须沿 `\input` 找到它，并拆开逗号列表。测试在 Task 6。
2. **已有 `.bib` 的 DOI 写法不同**（`https://doi.org/10.X`、大写、`doi = "..."`）：视为同一 DOI，不重复写入；`.bib` 末尾没有换行时，追加的条目不得粘连。DOI 归一化的测试在 Task 6，追加的测试在 Task 10。
3. **手改 YAML 后类型出错**（`questions` 写成字符串、`tasks` 条目是字符串、`version: "2"`）：`validate` 报告错误，不抛异常。测试在 Task 8。
4. **正文中的 `50\%`**：转义的百分号不是注释，不能被判为隐藏占位；真正的 `% 待补` 注释要被检出。测试在 Task 11。
5. **CrossRef/OpenAlex 超时或返回 5xx**：该条记入线索并注明原因，其余条目继续处理；全部失败时 `.bib` 不被改动。测试在 Task 10。

## 与设计文档的四处细化

写计划时发现以下四点，Task 14 同步修改设计文档：

1. **摘要片段不另设状态值。** `rls.paper.v1` 的 `abstract_status` 只允许 `present/missing/attempted/not_requested`。wispaper 的摘要片段改为：`abstract` 置空、`abstract_status` 为 `missing`、片段原文存入 `provenance.host_abstract_snippet`，并加 `abstract_snippet_only` 警告。之后由 `enrich-abstracts` 补全。
2. **从链接提取 DOI 放在检索端。** 由 research-literature-search 的 wispaper 适配器完成，下游拿到的规范记录已带 DOI；`bib_resolve.py` 只处理规范记录，没有 DOI 时按标题检索。
3. **research-content-writer 的检查脚本自相矛盾。** 它的 `SKILL.md` 禁止正文出现 S1–S4，`scripts/check_project_outputs.py` 却要求正文至少出现 3 个 `S` 编号。Task 4 改为检查编号泄漏。
4. **AI 使用说明的落点要看模板。** `projects/NSFC_General/main.tex` 引用了 `extraTex/4.5.生成式人工智能.tex`；`projects/NSFC_Young/main.tex` 有该文件却没有引用；`NSFC_Local` 没有该文件。`case.py init` 检查 `main.tex` 的引用树：没有引用时，AI 使用说明改写到 `proposal/ai_declaration.md`，并在 `assumptions.md` 记一条待核实项。nsfc-proposal 不改 `main.tex`。

## File Structure

| 路径 | 动作 | 职责 |
|---|---|---|
| `skills/nsfc-justification-writer/scripts/core/change_guard.py` | 改 | 允许新增白名单内的标题命令 |
| `skills/nsfc-justification-writer/scripts/core/versioning.py` | 改 | `list_runs` 只认运行记录目录；跨任务目录查找 run |
| `skills/nsfc-justification-writer/scripts/core/config_loader.py` | 改 | `RUNS_DIR_ENV` 常量；缓存目录跟随 `--task-root` |
| `skills/nsfc-justification-writer/scripts/run.py` | 改 | `--task-root`；`diff/rollback/list-runs` 跨任务目录查找；传入标题白名单 |
| `skills/nsfc-justification-writer/config.yaml` | 改 | `guardrails.allowed_new_heading_commands`；版本 |
| `skills/nsfc-justification-writer/SKILL.md`、`references/tier2_semantic_review.md`、`CHANGELOG.md` | 改 | 读取 `proposal/`；Tier2 新增两项检查 |
| `skills/nsfc-research-content-writer/scripts/check_project_outputs.py`、`config.yaml`、`SKILL.md`、`CHANGELOG.md` | 改 | 检查 S 编号泄漏；读取 `proposal/` |
| `skills/nsfc-research-foundation-writer/SKILL.md`、`config.yaml`、`CHANGELOG.md` | 改 | 读取 `proposal/`；缺失项写可见占位 |
| `skills/nsfc-abstract/SKILL.md`、`config.yaml`、`CHANGELOG.md` | 改 | 以科学论证为准 |
| `skills/research-literature-search/scripts/providers/host_results.py` | 新建 | wispaper 返回 → provider 原始记录 |
| `skills/research-literature-search/scripts/search_runner.py` | 改 | `run_search(host_results=...)`；`--host-results` |
| `skills/research-literature-search/SKILL.md`、`config.yaml`、`CHANGELOG.md` | 改 | 文档与版本 |
| `skills/nsfc-proposal/SKILL.md`、`README.md`、`CHANGELOG.md`、`config.yaml` | 新建 | skill 入口、说明、配置 |
| `skills/nsfc-proposal/references/{scientific_case_guide,evidence_wording,section_boundaries,confirm_prompt}.md` | 新建 | AI 执行指南 |
| `skills/nsfc-proposal/assets/{scientific_case,evidence_map,section_plan}.yaml` | 新建 | 空白模板 |
| `skills/nsfc-proposal/scripts/proposal_common.py` | 新建 | 路径、YAML、配置、LaTeX 注释拆分、Markdown 小节追加 |
| `skills/nsfc-proposal/scripts/latex_files.py` | 新建 | 沿 `\input` 遍历编译树；定位并读取 `.bib` |
| `skills/nsfc-proposal/scripts/case.py` | 新建 | CLI：init/validate/render/to-info-form/bump/status/mark-written |
| `skills/nsfc-proposal/scripts/case_validate.py` | 新建 | 三份 YAML 的校验规则 |
| `skills/nsfc-proposal/scripts/case_render.py` | 新建 | 渲染确认点 Markdown 和三种信息表 |
| `skills/nsfc-proposal/scripts/bib_resolve.py` | 新建 | 元数据补全与 `.bib` 追加 |
| `skills/nsfc-proposal/scripts/consistency_check.py` | 新建 | 跨章确定性检查 |
| `tests/nsfc-justification-writer/test_njw_*.py` | 新建 | Task 1–3 |
| `tests/nsfc-research-content-writer/test_nrcw_checker.py` | 新建 | Task 4 |
| `tests/research-literature-search/test_rls_host_results.py` | 新建 | Task 5 |
| `tests/nsfc-proposal/test_np_*.py` | 新建 | Task 6–13 |
| `skills/README.md`、`CHANGELOG.md`、设计文档 | 改 | Task 14 |
| `/home/juli/guoziran/nsfc-proposal-eval/`（仓库外） | 新建 | 验收输入、项目副本、盲评材料（Task 15–20） |

---

## 阶段一：修复与小改动（Task 1–5，彼此独立）

### Task 1: justification-writer 允许新增标题命令

**Files:**
- Modify: `skills/nsfc-justification-writer/scripts/core/change_guard.py`（整文件替换，原 44 行）
- Modify: `skills/nsfc-justification-writer/scripts/run.py:547`（`inspect_proposal` 调用处）
- Modify: `skills/nsfc-justification-writer/config.yaml:46-60`（`guardrails` 段）
- Test: `tests/nsfc-justification-writer/test_njw_change_guard.py`

**Interfaces:**
- Produces: `inspect_proposal(*, original: str, proposed: str, target_path: Path, project_root: Path, allowed_new_headings: Sequence[str] = ()) -> ChangeGuardResult`；配置键 `guardrails.allowed_new_heading_commands: list[str]`。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-justification-writer/test_njw_change_guard.py
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-justification-writer/scripts"
sys.path.insert(0, str(SCRIPTS))

from core.change_guard import inspect_proposal  # noqa: E402


class ChangeGuardHeadingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.target = self.root / "extraTex" / "1.1.立项依据.tex"
        self.target.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _inspect(self, original: str, proposed: str, allowed: tuple[str, ...] = ()):
        return inspect_proposal(
            original=original,
            proposed=proposed,
            target_path=self.target,
            project_root=self.root,
            allowed_new_headings=allowed,
        )

    def test_new_subsubsection_allowed_when_configured(self) -> None:
        result = self._inspect("\\justifying\n", "\\justifying\n\\subsubsection{研究背景}\n正文。\n", ("subsubsection",))
        self.assertTrue(result.ok)
        self.assertEqual(result.structural_hits, [])

    def test_new_subsubsection_rejected_without_allowlist(self) -> None:
        result = self._inspect("\\justifying\n", "\\justifying\n\\subsubsection{研究背景}\n正文。\n")
        self.assertFalse(result.ok)
        self.assertEqual(result.structural_hits, ["\\subsubsection"])

    def test_removing_existing_heading_still_rejected(self) -> None:
        result = self._inspect("\\subsubsection{旧标题}\n旧正文。\n", "新正文。\n", ("subsubsection",))
        self.assertFalse(result.ok)
        self.assertIn("\\subsubsection", result.structural_hits)

    def test_renaming_existing_heading_rejected(self) -> None:
        result = self._inspect("\\subsubsection{旧标题}\n正文。\n", "\\subsubsection{新标题}\n正文。\n", ("subsubsection",))
        self.assertFalse(result.ok)

    def test_new_input_command_still_rejected(self) -> None:
        result = self._inspect("", "\\subsubsection{背景}\n\\input{extraTex/other}\n", ("subsubsection",))
        self.assertFalse(result.ok)
        self.assertEqual(result.structural_hits, ["\\input"])

    def test_allowlist_accepts_backslash_prefix(self) -> None:
        result = self._inspect("", "\\subsubsection{背景}\n", ("\\subsubsection",))
        self.assertTrue(result.ok)


class PreviewCliHeadingTest(unittest.TestCase):
    def test_preview_dry_run_accepts_new_heading_with_default_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            target = project / "extraTex" / "1.1.立项依据.tex"
            target.parent.mkdir(parents=True)
            target.write_text("\\justifying\n\\NSFCBodyText\n", encoding="utf-8")
            proposal = Path(tmp) / "proposal.tex"
            proposal.write_text("\\justifying\n\\NSFCBodyText\n\n\\subsubsection{研究背景}\n正文。\n", encoding="utf-8")
            env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
            env.pop("NSFC_JUSTIFICATION_WRITER_RUNS_DIR", None)
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "run.py"), "--no-user-override", "preview",
                 "--project-root", str(project), "--proposal-file", str(proposal),
                 "--target-file", "extraTex/1.1.立项依据.tex", "--dry-run"],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("未发现结构/配置命令变化", proc.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-justification-writer/test_njw_change_guard.py`
Expected: FAIL，`TypeError: inspect_proposal() got an unexpected keyword argument 'allowed_new_headings'`；CLI 用例返回码 2。

- [ ] **Step 3: 实现 `change_guard.py`（整文件替换）**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""与 LaTeX 语法无关的预览/写入范围检查。"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence


STRUCTURE_COMMAND_RE = re.compile(
    r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|input|include|begin|end|label|newcommand|renewcommand|documentclass|usepackage)\b"
)


@dataclass(frozen=True)
class ChangeGuardResult:
    ok: bool
    changed_lines: int
    structural_hits: List[str]
    diff: str


def inspect_proposal(
    *,
    original: str,
    proposed: str,
    target_path: Path,
    project_root: Path,
    allowed_new_headings: Sequence[str] = (),
) -> ChangeGuardResult:
    """生成 diff，并提示新增/删除行是否触碰结构或配置命令。

    ``allowed_new_headings`` 列出允许出现在新增行中的标题命令（如 ``subsubsection``）。
    删除行中的结构命令一律计入 hits，所以删改已有标题仍会被拒绝。
    """
    root = Path(project_root).resolve()
    target = Path(target_path).resolve()
    target.relative_to(root)  # 越界时抛出 ValueError，由 CLI 转成安全错误
    diff_lines = list(
        difflib.unified_diff(
            (original or "").splitlines(),
            (proposed or "").splitlines(),
            fromfile=str(target),
            tofile=str(target),
            lineterm="",
        )
    )
    allowed = {"\\" + name.strip().lstrip("\\") for name in allowed_new_headings if name and name.strip()}
    hits: set[str] = set()
    changed_lines = 0
    for line in diff_lines:
        if line.startswith(("+++", "---")) or not line.startswith(("+", "-")):
            continue
        changed_lines += 1
        is_added = line.startswith("+")
        for match in STRUCTURE_COMMAND_RE.finditer(line[1:]):
            command = match.group(0)
            if is_added and command in allowed:
                continue
            hits.add(command)
    return ChangeGuardResult(
        ok=not hits,
        changed_lines=changed_lines,
        structural_hits=sorted(hits),
        diff="\n".join(diff_lines) + ("\n" if diff_lines else ""),
    )
```

- [ ] **Step 4: 在 `run.py` 的 `cmd_preview` 中传入白名单**

把 `run.py` 约第 547 行：

```python
        result = inspect_proposal(original=original, proposed=proposal, target_path=target, project_root=project_root)
```

替换为：

```python
        result = inspect_proposal(
            original=original,
            proposed=proposal,
            target_path=target,
            project_root=project_root,
            allowed_new_headings=get_seq_str(guard, "allowed_new_heading_commands"),
        )
```

（`get_seq_str` 和 `guard` 在该函数内已可用：第 28 行已导入，`guard` 在函数开头已赋值。）

- [ ] **Step 5: 在 `config.yaml` 的 `guardrails` 段末尾（`auto_retry_body_only: true` 之后）加入**

```yaml
  # 模板自带的标题命令允许在提案中新增；删改已有标题仍按结构变动拒绝。
  allowed_new_heading_commands:
    - subsubsection
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-justification-writer/test_njw_change_guard.py`
Expected: 7 passed。

再运行配置校验：`python3 skills/nsfc-justification-writer/scripts/run.py --no-user-override validate-config`
Expected: 退出码 0。

- [ ] **Step 7: 提交**

```bash
git add skills/nsfc-justification-writer/scripts/core/change_guard.py skills/nsfc-justification-writer/scripts/run.py skills/nsfc-justification-writer/config.yaml tests/nsfc-justification-writer/test_njw_change_guard.py
git commit -m "fix(nsfc-justification-writer): 允许提案新增模板标题命令

change_guard 原先把任何含 \\subsubsection 的增删行都判为结构变动，
写入空白模板时无法加标题。现在白名单内的标题命令可出现在新增行，
删改已有标题和其他结构命令仍被拒绝。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: justification-writer 的 `list_runs` 只列运行记录

**Files:**
- Modify: `skills/nsfc-justification-writer/scripts/core/versioning.py:1-30`
- Test: `tests/nsfc-justification-writer/test_njw_versioning.py`

**Interfaces:**
- Produces: `list_runs(*, runs_root: Path) -> List[RunInfo]`（行为收窄）；模块常量 `RUN_ID_RE`、`RUN_MARKER_DIRS`、`WORKSPACE_DIRS`。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-justification-writer/test_njw_versioning.py
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/nsfc-justification-writer/scripts"))

from core.versioning import list_runs  # noqa: E402


class ListRunsTest(unittest.TestCase):
    def test_skips_workspace_and_cache_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nsfc-justification-writer"
            for name in ("input", "output", "log", "cache"):
                (root / name).mkdir(parents=True)
            (root / "auto_20261009093512" / "backup").mkdir(parents=True)
            (root / "my-custom-run" / "logs").mkdir(parents=True)
            (root / "init_20261009093000").mkdir(parents=True)
            (root / "random_folder").mkdir(parents=True)
            ids = sorted(r.run_id for r in list_runs(runs_root=root))
            self.assertEqual(ids, ["auto_20261009093512", "init_20261009093000", "my-custom-run"])

    def test_missing_root_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list_runs(runs_root=Path(tmp) / "absent"), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-justification-writer/test_njw_versioning.py`
Expected: FAIL，结果中多出 `cache`、`input`、`log`、`output`、`random_folder`。

- [ ] **Step 3: 实现**

在 `versioning.py` 的 import 区加入 `import re`，并把 `list_runs` 替换为：

```python
# run_id 形如 auto_20261009093512（见 observability.make_run_id）
RUN_ID_RE = re.compile(r"^[A-Za-z][\w-]*_\d{14}$")
# 运行目录内会出现的子目录（备份、日志、信息表、报告）
RUN_MARKER_DIRS = ("backup", "logs", "inputs", "reports")
# 任务工作区约定的目录，不是运行记录
WORKSPACE_DIRS = frozenset({"input", "output", "log", "cache"})


def _is_run_dir(path: Path) -> bool:
    if not path.is_dir() or path.name in WORKSPACE_DIRS:
        return False
    if RUN_ID_RE.match(path.name):
        return True
    return any((path / marker).is_dir() for marker in RUN_MARKER_DIRS)


def list_runs(*, runs_root: Path) -> List[RunInfo]:
    runs_root = Path(runs_root).resolve()
    if not runs_root.is_dir():
        return []
    items = [RunInfo(run_id=p.name, path=p) for p in runs_root.iterdir() if _is_run_dir(p)]
    return sorted(items, key=lambda x: x.run_id, reverse=True)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: 同 Step 2。
Expected: 2 passed。

- [ ] **Step 5: 提交**

```bash
git add skills/nsfc-justification-writer/scripts/core/versioning.py tests/nsfc-justification-writer/test_njw_versioning.py
git commit -m "fix(nsfc-justification-writer): list-runs 不再把 input/output/log 当作运行记录

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: justification-writer 的 `--task-root` 与跨任务目录查找

**Files:**
- Modify: `skills/nsfc-justification-writer/scripts/core/config_loader.py:408-428`
- Modify: `skills/nsfc-justification-writer/scripts/core/versioning.py`（追加两个函数）
- Modify: `skills/nsfc-justification-writer/scripts/run.py`（import、`cmd_list_runs`、`cmd_diff`、`cmd_rollback`、`build_parser`、`main`）
- Test: `tests/nsfc-justification-writer/test_njw_task_root.py`

**Interfaces:**
- Consumes: Task 2 的 `list_runs`。
- Produces: `config_loader.RUNS_DIR_ENV = "NSFC_JUSTIFICATION_WRITER_RUNS_DIR"`；`versioning.task_runs_roots(*, search_base: Path) -> List[Path]`；`versioning.locate_runs_root(*, run_id: str, search_base: Path) -> Optional[Path]`；CLI 顶层参数 `--task-root <.bensz-api/task-*/>`（nsfc-proposal 用它调用本 skill）。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-justification-writer/test_njw_task_root.py
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/nsfc-justification-writer/scripts/run.py"
SKILL_DIR = "nsfc-justification-writer"


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
    env.pop("NSFC_JUSTIFICATION_WRITER_RUNS_DIR", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--no-user-override", *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


class TaskRootTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_task_root_fixes_runs_dir(self) -> None:
        task = self.base / ".bensz-api" / "task-20261009-1200-demo"
        proc = run_cli(self.base, "--task-root", str(task), "init", "--run-id", "init_20261009120000")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((task / SKILL_DIR / "init_20261009120000" / "inputs" / "info_form.md").is_file())

    def test_task_root_requires_task_prefix(self) -> None:
        proc = run_cli(self.base, "--task-root", str(self.base / "elsewhere"), "init")
        self.assertEqual(proc.returncode, 2)

    def test_diff_locates_run_in_earlier_task_dir(self) -> None:
        project = self.base / "proj"
        target = project / "extraTex" / "1.1.立项依据.tex"
        target.parent.mkdir(parents=True)
        target.write_text("新正文\n", encoding="utf-8")
        backup = (self.base / ".bensz-api" / "task-20261009-1159-nsfc-justification-writer" / SKILL_DIR
                  / "auto_20261009115900" / "backup" / "extraTex" / "1.1.立项依据.tex")
        backup.parent.mkdir(parents=True)
        backup.write_text("旧正文\n", encoding="utf-8")
        proc = run_cli(self.base, "diff", "--project-root", str(project), "--run-id", "auto_20261009115900")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("-旧正文", proc.stdout)
        self.assertIn("+新正文", proc.stdout)

    def test_list_runs_aggregates_task_dirs(self) -> None:
        for task, run in (("task-20261009-1100-a", "auto_20261009110000"), ("task-20261009-1130-b", "auto_20261009113000")):
            runs_root = self.base / ".bensz-api" / task / SKILL_DIR
            (runs_root / run / "backup").mkdir(parents=True)
            (runs_root / "log").mkdir(parents=True)
        proc = run_cli(self.base, "list-runs")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(lines, ["auto_20261009113000", "auto_20261009110000"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-justification-writer/test_njw_task_root.py`
Expected: FAIL。`--task-root` 未识别（argparse 退出码 2，第一个用例失败）；`diff` 找不到备份（退出码 2）；`list-runs` 输出「（暂无 runs 记录）」。

- [ ] **Step 3: 修改 `config_loader.py`**

在 `get_runs_dir` 之前加入常量，并改写两个函数：

```python
# 指定后，runs_dir 固定为该路径（run.py 的 --task-root 会设置它）
RUNS_DIR_ENV = "NSFC_JUSTIFICATION_WRITER_RUNS_DIR"


def get_runs_dir(skill_root: Path, config: Dict[str, Any]) -> Path:
    env_override = os.environ.get(RUNS_DIR_ENV)
    if env_override:
        p = Path(env_override)
        if not p.is_absolute():
            p = (Path(skill_root) / p).resolve()
        return p.resolve()
    workspace = config.get("workspace", {})
    workspace = workspace if isinstance(workspace, dict) else {}
    runs_dir = str(workspace.get("runs_dir", "") or "")
    if not runs_dir or "{yyyymmdd" in runs_dir or runs_dir.startswith("tests/_artifacts"):
        return (Path.cwd() / ".bensz-api" / f"task-{datetime.now().strftime('%Y%m%d-%H%M')}-nsfc-justification-writer" / "nsfc-justification-writer").resolve()
    return (Path(skill_root) / runs_dir).resolve()


def get_cache_dir(skill_root: Path, config: Dict[str, Any]) -> Path:
    if os.environ.get(RUNS_DIR_ENV):
        return (get_runs_dir(skill_root, config) / "cache" / "ai").resolve()
    ai = config.get("ai", {}) if isinstance(config, dict) else {}
    value = str(ai.get("cache_dir", "") or "") if isinstance(ai, dict) else ""
    if not value or "{yyyymmdd" in value or value.startswith("tests/_artifacts"):
        return (Path.cwd() / ".bensz-api" / f"task-{datetime.now().strftime('%Y%m%d-%H%M')}-nsfc-justification-writer" / "nsfc-justification-writer" / "cache" / "ai").resolve()
    return (Path(skill_root) / value).resolve()
```

- [ ] **Step 4: 在 `versioning.py` 末尾追加**

```python
SKILL_DIR_NAME = "nsfc-justification-writer"


def task_runs_roots(*, search_base: Path) -> List[Path]:
    """列出 search_base/.bensz-api/task-*/nsfc-justification-writer/，按任务目录名排序。"""
    base = Path(search_base).resolve() / ".bensz-api"
    return sorted(p.resolve() for p in base.glob(f"task-*/{SKILL_DIR_NAME}") if p.is_dir())


def locate_runs_root(*, run_id: str, search_base: Path) -> Optional[Path]:
    """在各任务目录中查找包含 run_id 的 runs_root；有多个时取任务目录名最大的一个。"""
    rid = str(run_id or "").strip()
    if not rid or rid in {".", ".."} or "/" in rid or "\\" in rid:
        return None
    matches = [root for root in task_runs_roots(search_base=search_base) if (root / rid).is_dir()]
    return matches[-1] if matches else None
```

- [ ] **Step 5: 修改 `run.py`**

5a. 第 27 行改为：

```python
from core.config_loader import RUNS_DIR_ENV, load_config, get_runs_dir, validate_config
```

第 40 行改为：

```python
from core.versioning import find_backup_for_run_v2, list_runs, locate_runs_root, rollback_from_backup, task_runs_roots, unified_diff
```

5b. 在 `cmd_list_runs` 之前加入两个辅助函数：

```python
def _runs_root_for_run(skill_root: Path, config: Dict[str, Any], run_id: str) -> Path:
    """返回包含 run_id 的 runs_root；未指定 --task-root 时到各任务目录中查找。"""
    runs_root = get_runs_dir(skill_root, config)
    if os.environ.get(RUNS_DIR_ENV) or (runs_root / run_id).is_dir():
        return runs_root
    return locate_runs_root(run_id=run_id, search_base=Path.cwd()) or runs_root


def _runs_roots_for_listing(skill_root: Path, config: Dict[str, Any]) -> list[Path]:
    current = get_runs_dir(skill_root, config)
    if os.environ.get(RUNS_DIR_ENV):
        return [current]
    roots = task_runs_roots(search_base=Path.cwd())
    return roots if current in roots else [*roots, current]
```

5c. `cmd_list_runs` 改为：

```python
def cmd_list_runs(args: argparse.Namespace) -> int:
    skill_root = Path(__file__).resolve().parent.parent
    config = _load_config_for_args(skill_root, args)
    by_id = {}
    for root in _runs_roots_for_listing(skill_root, config):
        for run in list_runs(runs_root=root):
            by_id[run.run_id] = run
    runs = sorted(by_id.values(), key=lambda r: r.run_id, reverse=True)
    if not runs:
        print("（暂无 runs 记录）")
        return 0
    for r in runs[: int(args.limit)]:
        print(r.run_id)
    return 0
```

5d. 在 `cmd_diff` 和 `cmd_rollback` 中，把 `runs_root = get_runs_dir(skill_root, config)` 一行分别替换为：

```python
    runs_root = _runs_root_for_run(skill_root, config, str(args.run_id))
```

5e. 在 `build_parser` 中，紧接 `--no-user-override` 那一行之后加入：

```python
    p.add_argument("--task-root", help="本任务的 .bensz-api/task-*/ 目录；所有子命令的 runs_dir 固定为其下的 nsfc-justification-writer/")
```

5f. `main` 中，在 `configure_logging(...)` 之后、`try:` 之前加入：

```python
    task_root = getattr(args, "task_root", None)
    if task_root:
        root = Path(task_root).expanduser().resolve()
        if not root.name.startswith("task-"):
            logger.error("❌ --task-root 必须指向 .bensz-api/task-*/ 目录：%s", root)
            return 2
        os.environ[RUNS_DIR_ENV] = str(root / "nsfc-justification-writer")
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-justification-writer/`
Expected: Task 1–3 全部通过（13 passed）。

- [ ] **Step 7: 提交**

```bash
git add skills/nsfc-justification-writer/scripts tests/nsfc-justification-writer/test_njw_task_root.py
git commit -m "fix(nsfc-justification-writer): 新增 --task-root，diff/rollback 跨任务目录查找运行记录

任务目录名原先每次调用按当前分钟生成，跨分钟的 diff/rollback 找不到前一步。
现在 --task-root 固定 runs_dir；未传入时按 run_id 在 .bensz-api/task-*/ 下查找，
不猜测「最近一次」目录。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: research-content-writer 检查脚本改为检测编号泄漏

**Files:**
- Modify: `skills/nsfc-research-content-writer/scripts/check_project_outputs.py`
- Modify: `skills/nsfc-research-content-writer/config.yaml`（删除 `subgoal_markers_min` 及其注释）
- Test: `tests/nsfc-research-content-writer/test_nrcw_checker.py`

**Interfaces:**
- Produces: `_check_minimal_content(path: Path, *, kind: str) -> list[str]`；`_read_checks_from_config(config_yaml: Path) -> list[str]`（只返回风险短语）。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-research-content-writer/test_nrcw_checker.py
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "skills/nsfc-research-content-writer/scripts/check_project_outputs.py"

CLEAN_RESEARCH = "\\justifying\n针对第一个研究目标，本项目比较瘤内模型与临床基线（实验占比 50\\%）。\n"
CLEAN_INNOVATION = "\\justifying\n与现有路线相比，本项目检验对应关系的成立条件。\n"
CLEAN_YEARLY = "第一年：建立队列。\n第二年：完成建模。\n第三年：外部验证。\n"


def make_project(base: Path, research: str = CLEAN_RESEARCH, innovation: str = CLEAN_INNOVATION, yearly: str = CLEAN_YEARLY) -> Path:
    extra = base / "proj" / "extraTex"
    extra.mkdir(parents=True)
    (extra / "2.1.研究内容.tex").write_text(research, encoding="utf-8")
    (extra / "2.2.特色与创新.tex").write_text(innovation, encoding="utf-8")
    (extra / "2.3.年度研究计划.tex").write_text(yearly, encoding="utf-8")
    return base / "proj"


def run_checker(project: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
    return subprocess.run([sys.executable, str(CHECKER), "--project-root", str(project), "--no-risk-scan"],
                          env=env, capture_output=True, text=True, timeout=60)


class CheckerTest(unittest.TestCase):
    def test_clean_body_without_subgoal_ids_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_checker(make_project(Path(tmp)))
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_leaked_subgoal_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_checker(make_project(Path(tmp), research="对应 S1 的任务是建立队列。\n"))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("S1", proc.stderr)

    def test_subgoal_id_inside_comment_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_checker(make_project(Path(tmp), research=CLEAN_RESEARCH + "% 内部规划：S1 S2 S3\n"))
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_year_header_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_checker(make_project(Path(tmp), yearly="第一年：建立队列。\n"))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("第2年", proc.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-research-content-writer/test_nrcw_checker.py`
Expected: `test_clean_body_without_subgoal_ids_passes` 和 `test_subgoal_id_inside_comment_is_ignored` FAIL（报 `not enough subgoal markers`）；`test_leaked_subgoal_id_fails` 可能 FAIL（现有逻辑反而要求 S 编号）。

- [ ] **Step 3: 修改 `check_project_outputs.py`**

3a. 删除常量 `DEFAULT_SUBGOAL_MARKERS_MIN = 3`，在 `DEFAULT_RISK_PHRASES` 之后加入：

```python
# SKILL.md 规定 S1–S4 只用于内部规划，禁止出现在 .tex 正文中
INTERNAL_SUBGOAL_ID_RE = re.compile(r"(?<![A-Za-z0-9])S\d+(?![A-Za-z0-9])")
LATEX_COMMENT_RE = re.compile(r"(?<!\\)%.*$")
```

3b. `_read_checks_from_config` 替换为：

```python
def _read_checks_from_config(config_yaml: Path) -> list[str]:
    lines = config_yaml.read_text(encoding="utf-8").splitlines()
    return extract_yaml_list_under_block(lines, "checks", "risk_phrases") or DEFAULT_RISK_PHRASES
```

3c. `_check_minimal_content` 替换为：

```python
def _strip_latex_comments(text: str) -> str:
    return "\n".join(LATEX_COMMENT_RE.sub("", line) for line in text.splitlines())


def _check_minimal_content(path: Path, *, kind: str) -> list[str]:
    text = _strip_latex_comments(path.read_text(encoding="utf-8", errors="replace"))
    problems: list[str] = []

    leaked = sorted(set(INTERNAL_SUBGOAL_ID_RE.findall(text)))
    if leaked:
        problems.append(f"{path}: internal subgoal IDs leaked into body: {', '.join(leaked)} (use natural language instead)")

    if kind == "research":
        if not text.strip():
            problems.append(f"{path}: research content is empty")
    elif kind == "innovation":
        if not text.strip():
            problems.append(f"{path}: innovation content is empty")
    elif kind == "yearly":
        year_patterns = {
            "第1年/第一年": [r"第\s*1\s*年", r"第一年"],
            "第2年/第二年": [r"第\s*2\s*年", r"第二年"],
            "第3年/第三年": [r"第\s*3\s*年", r"第三年"],
        }
        for label, patterns in year_patterns.items():
            if not any(re.search(p, text) for p in patterns):
                problems.append(f"{path}: missing yearly header ({label})")
    else:
        problems.append(f"{path}: unknown kind {kind}")

    return problems
```

3d. 在 `main` 中，把 `risk_phrases, subgoal_markers_min = _read_checks_from_config(config_yaml)` 改为 `risk_phrases = _read_checks_from_config(config_yaml)`；把 `_check_minimal_content(project_root / relpath, kind=kind, subgoal_markers_min=subgoal_markers_min)` 改为 `_check_minimal_content(project_root / relpath, kind=kind)`。

3e. 删除 `config.yaml` 中这两行：

```yaml
  # 研究内容里至少出现多少个子目标标记（默认 3）：S1/S2/S3（可多于 3）
  subgoal_markers_min: 3
```

- [ ] **Step 4: 运行测试与自检**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-research-content-writer/test_nrcw_checker.py`
Expected: 4 passed。

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 skills/nsfc-research-content-writer/scripts/validate_skill.py`
Expected: 输出与改动前相同。该脚本在 `main` 上本来就失败（`missing required directory: .../plans`：它要求 skill 目录内有 `plans/`，与上游「不得在 Skill 目录内新建 plans/」冲突），不在本次修复范围，记入 Task 20 的交付报告。

Run: `grep -rn "subgoal_markers_min" skills/nsfc-research-content-writer`
Expected: 无输出。

- [ ] **Step 5: 提交**

```bash
git add skills/nsfc-research-content-writer/scripts/check_project_outputs.py skills/nsfc-research-content-writer/config.yaml tests/nsfc-research-content-writer/test_nrcw_checker.py
git commit -m "fix(nsfc-research-content-writer): 检查脚本改为检测 S 编号泄漏

SKILL.md 禁止正文出现 S1–S4，check_project_outputs.py 却要求至少 3 个 S 编号，
两者矛盾。现在正文（注释除外）出现 S 编号即报错；删除 subgoal_markers_min。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: research-literature-search 接收 wispaper 结果（`--host-results`）

**Files:**
- Create: `skills/research-literature-search/scripts/providers/host_results.py`
- Modify: `skills/research-literature-search/scripts/search_runner.py`（`run_search` 签名与 provider 循环、CLI）
- Test: `tests/research-literature-search/test_rls_host_results.py`

**Interfaces:**
- Produces:
  - `providers.host_results.HOST_RESULTS_SCHEMA = "rls.host_results.v1"`
  - `providers.host_results.doi_from_urls(*urls: object) -> str | None`
  - `providers.host_results.adapt_wispaper(paper: Mapping[str, Any]) -> dict[str, Any]`
  - `providers.host_results.load_host_results(path: Path) -> dict[str, list[dict[str, Any]]]`（键为检索式原文，值为已适配的原始记录；文件不合法时抛 `ValueError`）
  - `run_search(..., host_results: Mapping[str, list[dict[str, Any]]] | None = None)`
  - CLI：`search_runner.py run ... --host-results <json>`
- host results 文件格式（nsfc-proposal 的 SKILL.md 让 AI 按此格式保存 wispaper 返回）：

```json
{
  "schema": "rls.host_results.v1",
  "provider": "wispaper",
  "queries": [
    {"query": "peritumoral radiomics ground-glass nodule invasiveness", "tool": "quick_search", "papers": [ {"title": "...", "authors": ["..."], "doi": null, "year": 2021, "venue": null, "url": "...", "source_url": "...", "pdf_url": null, "abstract": "...", "flags": {"perfect": false}} ]}
  ]
}
```

- [ ] **Step 1: 写失败测试**

```python
# tests/research-literature-search/test_rls_host_results.py
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/research-literature-search/scripts"
sys.path.insert(0, str(SCRIPTS))

from providers.host_results import adapt_wispaper, doi_from_urls, load_host_results  # noqa: E402
from search_runner import run_search  # noqa: E402
from validate_bundle import validate_bundle  # noqa: E402

# 2026-10-09 对肺结节题目实测的 wispaper 返回（节选、字段原样）
QUICK_PAPER = {
    "abstract": "… region to distinguish the invasiveness of pulmonary nodules, to predict … compared to peritumoral radiomics 2 mm from the nodule. …",
    "arxiv_id": None,
    "authors": ["L Wu", "C Gao", "J Ye", "J Tao", "N Wang", "P Pang", "P Xiang"],
    "citations": 40, "doi": None, "flags": {"perfect": False}, "paper_id": None, "pdf_url": None,
    "source_url": "https://link.springer.com/article/10.1007/s00330-021-07948-0",
    "title": "The value of various peritumoral radiomic features in differentiating the invasiveness of adenocarcinoma manifesting as ground-glass nodules",
    "url": "https://link.springer.com/article/10.1007/s00330-021-07948-0", "venue": None, "year": 2021,
}
DEEP_PAPER = {
    "abstract": "Background Differentiating histological invasiveness of lung adenocarcinoma that manifest as pure ground-glass nodules (pGGNs) is challenging. Purpose To investigate the value of computerized texture analysis.",
    "arxiv_id": None,
    "authors": ["Yang Yang", "Wei-Wei Wang", "Yan Ren"],
    "doi": "10.1177/0284185119826536", "flags": {"no": False, "partial": False, "perfect": True},
    "paper_id": None, "pdf_url": None,
    "source_url": "https://journals.sagepub.com/doi/abs/10.1177/0284185119826536",
    "title": "Computerized texture analysis predicts histological invasiveness within lung adenocarcinoma manifesting as pure ground-glass nodules",
    "url": "https://journals.sagepub.com/doi/abs/10.1177/0284185119826536",
    "venue": "Acta radiologica (Stockholm, Sweden : 1987)", "year": 2019,
}
TRUNCATED_PAPER = {
    "abstract": "… intratumoral and peritumoral radiomics combined with computed tomography (CT) features …",
    "authors": ["Y Wang", "D Lyu"], "doi": None, "flags": {"perfect": False}, "pdf_url": None,
    "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11388221/",
    "title": "… radiomics combined with computed tomography features for predicting the invasiveness of lung adenocarcinoma presenting as a subpleural ground-glass …",
    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11388221/", "venue": None, "year": 2024,
}
QUERIES = [
    "peritumoral radiomics ground-glass nodule invasiveness",
    "ground-glass nodule invasive adenocarcinoma deep learning CT",
    "CT reconstruction kernel radiomics feature reproducibility",
    "ground-glass nodule consolidation tumor ratio invasiveness",
    "minimally invasive adenocarcinoma CT texture analysis",
]


class DoiFromUrlsTest(unittest.TestCase):
    def test_real_wispaper_urls(self) -> None:
        self.assertEqual(doi_from_urls("https://ajronline.org/doi/abs/10.2214/ajr.24.31675"), "10.2214/ajr.24.31675")
        self.assertEqual(doi_from_urls("https://link.springer.com/article/10.1007/s00330-021-07948-0"), "10.1007/s00330-021-07948-0")
        self.assertEqual(doi_from_urls("https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2020.00838/full"), "10.3389/fonc.2020.00838")
        self.assertEqual(doi_from_urls("https://ajronline.org/doi/pdf/10.2214/AJR.24.31675"), "10.2214/ajr.24.31675")

    def test_no_doi(self) -> None:
        self.assertIsNone(doi_from_urls("https://pmc.ncbi.nlm.nih.gov/articles/PMC11388221/", None))


class AdaptWispaperTest(unittest.TestCase):
    def test_snippet_abstract_moves_to_provenance(self) -> None:
        raw = adapt_wispaper(QUICK_PAPER)
        self.assertIsNone(raw["abstract"])
        self.assertIn("abstract_snippet_only", raw["quality_warnings"])
        self.assertTrue(raw["provenance"]["host_abstract_snippet"].startswith("…"))
        self.assertEqual(raw["doi"], "10.1007/s00330-021-07948-0")

    def test_full_abstract_kept_and_relevance_recorded(self) -> None:
        raw = adapt_wispaper(DEEP_PAPER)
        self.assertTrue(raw["abstract"].startswith("Background"))
        self.assertEqual(raw["provenance"]["host_relevance"], "perfect")
        self.assertEqual(raw["doi"], "10.1177/0284185119826536")

    def test_truncated_title_flagged(self) -> None:
        raw = adapt_wispaper(TRUNCATED_PAPER)
        self.assertIn("title_truncated", raw["quality_warnings"])
        self.assertIsNone(raw["doi"])


class HostResultsRunTest(unittest.TestCase):
    def _write(self, tmp: Path, payload: dict) -> Path:
        path = tmp / "host.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _queries(self, tmp: Path) -> Path:
        path = tmp / "queries.json"
        path.write_text(json.dumps({"queries": QUERIES}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_load_rejects_wrong_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"schema": "other", "provider": "wispaper", "queries": []})
            with self.assertRaises(ValueError):
                load_host_results(path)

    def test_load_rejects_unknown_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"schema": "rls.host_results.v1", "provider": "other", "queries": []})
            with self.assertRaises(ValueError):
                load_host_results(path)

    def test_host_results_fill_mcp_slot_and_bundle_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            payload = {"schema": "rls.host_results.v1", "provider": "wispaper",
                       "queries": [{"query": QUERIES[0], "tool": "quick_search", "papers": [QUICK_PAPER, TRUNCATED_PAPER]},
                                   {"query": QUERIES[1], "tool": "deep_search", "papers": [DEEP_PAPER]}]}
            host = load_host_results(self._write(base, payload))
            calls: list[str] = []

            def fake_openalex(query: str, **_: object) -> list[dict]:
                calls.append(query)
                return []

            manifest = run_search(
                topic="GGN invasiveness", query_file=self._queries(base), output_dir=base / "bundle",
                provider_order=["mcp", "openalex"], provider_functions={"openalex": fake_openalex},
                max_results_per_query=10, host_results=host,
            )
            self.assertIn(manifest["status"], {"success", "partial_success"})
            mcp_attempts = [a for a in manifest["attempts"] if a["provider"] == "mcp"]
            self.assertEqual([a["status"] for a in mcp_attempts[:2]], ["success", "success"])
            self.assertEqual(mcp_attempts[0]["host_tool"], "wispaper")
            self.assertEqual(mcp_attempts[2]["status"], "skipped")
            self.assertIn(QUERIES[0], calls)  # 结果不足阈值时继续补充
            self.assertEqual(validate_bundle(base / "bundle"), [])
            rows = [json.loads(line) for line in (base / "bundle" / "candidates_deduped.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 3)
            dois = {r["identifiers"]["doi"] for r in rows}
            self.assertIn("10.1007/s00330-021-07948-0", dois)

    def test_without_host_results_mcp_is_skipped_as_before(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            manifest = run_search(
                topic="GGN", query_file=self._queries(base), output_dir=base / "bundle",
                provider_order=["mcp", "openalex"],
                provider_functions={"openalex": lambda q, **_: [{"title": f"paper for {q}", "year": 2020}]},
                max_results_per_query=5,
            )
            mcp = [a for a in manifest["attempts"] if a["provider"] == "mcp"]
            self.assertTrue(mcp and all(a["status"] == "skipped" and a["reason"] == "host tool required" for a in mcp))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/research-literature-search/test_rls_host_results.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'providers.host_results'`。

- [ ] **Step 3: 新建 `providers/host_results.py`**

```python
"""宿主 MCP 检索结果到 provider 原始记录的适配（当前支持 wispaper）。

AI 通过 MCP 调用 wispaper，把原始返回按 rls.host_results.v1 保存；本模块把每篇论文
转成 normalize_record 能识别的原始字段，并标出摘要片段与截断标题。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

HOST_RESULTS_SCHEMA = "rls.host_results.v1"
SUPPORTED_HOST_PROVIDERS = {"wispaper"}
DOI_IN_URL_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>?#]+", re.IGNORECASE)
DOI_URL_SUFFIXES = ("/full", "/abstract", "/epdf", "/pdf", ".pdf", "/fulltext", "/html")
ELLIPSES = ("…", "...")


def doi_from_urls(*urls: object) -> str | None:
    """从出版社链接中提取 DOI，去掉 /full、/abstract 等页面尾缀并转小写。"""
    for url in urls:
        if not isinstance(url, str):
            continue
        match = DOI_IN_URL_RE.search(url)
        if not match:
            continue
        doi = match.group(0).rstrip(".,;)").lower()
        stripped = True
        while stripped:
            stripped = False
            for suffix in DOI_URL_SUFFIXES:
                if doi.endswith(suffix):
                    doi = doi[: -len(suffix)]
                    stripped = True
        return doi
    return None


def _is_fragment(text: str) -> bool:
    text = text.strip()
    return text.startswith(ELLIPSES) or text.endswith(ELLIPSES)


def adapt_wispaper(paper: Mapping[str, Any]) -> dict[str, Any]:
    """把一篇 wispaper 论文转成 provider 原始记录。"""
    warnings: list[str] = []
    provenance: dict[str, Any] = {"host_tool": "wispaper"}
    title = str(paper.get("title") or "").strip()
    if title and _is_fragment(title):
        warnings.append("title_truncated")
    abstract = paper.get("abstract") if isinstance(paper.get("abstract"), str) else None
    if abstract and _is_fragment(abstract):
        provenance["host_abstract_snippet"] = abstract.strip()
        abstract = None
        warnings.append("abstract_snippet_only")
    flags = paper.get("flags") if isinstance(paper.get("flags"), Mapping) else {}
    if flags:
        provenance["host_relevance"] = "perfect" if flags.get("perfect") else ("partial" if flags.get("partial") else "none")
    doi = paper.get("doi") or doi_from_urls(paper.get("url"), paper.get("source_url"), paper.get("pdf_url"))
    url = paper.get("url") or paper.get("source_url")
    return {
        "id": paper.get("paper_id") or doi or url,
        "title": title,
        "authors": [a for a in (paper.get("authors") or []) if isinstance(a, str)],
        "doi": doi,
        "arxiv": paper.get("arxiv_id"),
        "year": paper.get("year"),
        "venue": paper.get("venue"),
        "url": url,
        "abstract": abstract,
        "quality_warnings": warnings,
        "provenance": provenance,
    }


def load_host_results(path: Path) -> dict[str, list[dict[str, Any]]]:
    """读取 rls.host_results.v1 文件，返回 {检索式原文: [原始记录]}。"""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"host results unreadable: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != HOST_RESULTS_SCHEMA:
        raise ValueError(f"host results schema must be {HOST_RESULTS_SCHEMA}")
    provider = payload.get("provider")
    if provider not in SUPPORTED_HOST_PROVIDERS:
        raise ValueError(f"unsupported host provider: {provider}")
    entries = payload.get("queries")
    if not isinstance(entries, list):
        raise ValueError("host results queries must be a list")
    results: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or not isinstance(entry.get("query"), str) or not entry["query"].strip():
            raise ValueError(f"host results entry {index} needs a non-empty query")
        papers = entry.get("papers")
        if not isinstance(papers, list):
            raise ValueError(f"host results entry {index} papers must be a list")
        adapted = [adapt_wispaper(p) for p in papers if isinstance(p, dict)]
        results.setdefault(entry["query"].strip(), []).extend(adapted)
    return results
```

- [ ] **Step 4: 修改 `search_runner.py`**

4a. 在两处 `from providers import search_crossref, ...` 之后各加一行：

```python
    from providers.host_results import load_host_results
```

4b. `run_search` 签名在 `preprint_profile: str = "auto",` 之后加入参数：

```python
    host_results: Mapping[str, list[dict[str, Any]]] | None = None,
```

4c. 在 provider 循环中，`for provider in order:` 的下一行（`if provider not in SUPPORTED_PROVIDERS:` 之前）插入：

```python
            if provider == "mcp" and host_results is not None:
                host_hits = host_results.get(text.strip())
                if host_hits is None:
                    item = {"provider": provider, "status": "skipped", "results": 0, "reason": "no host results for query"}
                    query_attempts.append(item)
                    attempts.append({"query_id": query_id, **item})
                    warnings.append(f"{query_id}/{provider}: skipped ({item['reason']})")
                    continue
                item = {"provider": provider, "status": "success" if host_hits else "empty", "results": len(host_hits), "host_tool": "wispaper"}
                query_attempts.append(item)
                attempts.append({"query_id": query_id, **item})
                hits.extend((provider, row) for row in host_hits)
                if len(hits) >= max(5, int(max_results_per_query * TOPUP_THRESHOLD)):
                    break
                continue
```

4d. CLI：在 `run.add_argument("--query-source", default="direct_cli")` 之后加入：

```python
    run.add_argument("--host-results", type=Path, help="rls.host_results.v1 文件：宿主经 MCP（wispaper）取得的结果，填入 mcp 检索源位置")
```

在 `if args.command == "run":` 分支开头加入：

```python
        host_results = None
        if args.host_results:
            try:
                host_results = load_host_results(args.host_results)
            except ValueError as exc:
                print(json.dumps(_failed_result(topic=args.topic, output_dir=args.output_dir, code="contract_invalid", warning=_safe_error(exc)), ensure_ascii=False, indent=2))
                return 1
```

并在该分支的 `run_search(...)` 调用末尾加上关键字参数 `host_results=host_results`。

- [ ] **Step 5: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/research-literature-search/test_rls_host_results.py`
Expected: 9 passed。

再跑现有依赖它的测试：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/research-literature-review tests/research-literature-radar tests/research-idea`
Expected: 与 `main` 上的基线相同。写计划时（2026-10-09）记录的基线：research-literature-review 3 passed，research-literature-radar 3 passed，research-idea 4 errors（本机未安装 `bensz_skill_kernel`，与本分支无关）。

- [ ] **Step 6: 提交**

```bash
git add skills/research-literature-search/scripts/providers/host_results.py skills/research-literature-search/scripts/search_runner.py tests/research-literature-search/test_rls_host_results.py
git commit -m "feat(research-literature-search): run 新增 --host-results，接收 wispaper 结果

宿主经 MCP 取得的 wispaper 结果填入预留的 mcp 检索源位置；结果不足时按原规则
用 OpenAlex 等补充。从出版社链接提取 DOI；摘要片段不当作摘要，原文存入 provenance。
不传该参数时行为不变。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## 阶段二：nsfc-proposal 脚本（Task 6–11，按顺序执行）

各模块都放在 `skills/nsfc-proposal/scripts/`，彼此用同目录 import（`python3 skills/nsfc-proposal/scripts/case.py` 运行时，脚本目录自动在 `sys.path` 首位）。测试统一这样导入：

```python
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/nsfc-proposal/scripts"))
```

### Task 6: 公共工具与 LaTeX 编译树

**Files:**
- Create: `skills/nsfc-proposal/scripts/proposal_common.py`
- Create: `skills/nsfc-proposal/scripts/latex_files.py`
- Test: `tests/nsfc-proposal/test_np_latex_files.py`

**Interfaces:**
- Produces（`proposal_common`）：`SKILL_ROOT: Path`；`class ProposalError(ValueError)`；`@dataclass(frozen=True) ProposalPaths(root, case, case_md, evidence, plan, assumptions, leads)`；`load_config() -> dict`；`resolve_project_root(path) -> Path`；`project_path(project_root: Path, relpath: str) -> Path`；`proposal_paths(project_root: Path) -> ProposalPaths`；`read_yaml(path: Path) -> dict`；`write_yaml(path: Path, data: dict) -> None`；`split_latex_comment(line: str) -> tuple[str, str]`；`append_under_heading(path: Path, heading: str, line: str) -> None`。
- Produces（`latex_files`）：`@dataclass(frozen=True) LatexTree(tex_files: list[Path], bib_files: list[Path])`；`scan_latex_tree(project_root: Path) -> LatexTree`；`normalize_doi(value: str | None) -> str | None`；`@dataclass(frozen=True) BibIndex(keys: frozenset[str], doi_keys: dict[str, str])`，属性 `dois -> frozenset[str]`；`read_bib_index(bib_files: list[Path]) -> BibIndex`；`relpath(project_root: Path, path: Path) -> str`。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-proposal/test_np_latex_files.py
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/nsfc-proposal/scripts"))

from latex_files import normalize_doi, read_bib_index, relpath, scan_latex_tree  # noqa: E402
from proposal_common import ProposalError, append_under_heading, project_path, split_latex_comment  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class SplitCommentTest(unittest.TestCase):
    def test_escaped_percent_is_not_comment(self) -> None:
        self.assertEqual(split_latex_comment("占比 50\\% 的病例 % 待补"), ("占比 50\\% 的病例 ", " 待补"))

    def test_double_backslash_then_percent_is_comment(self) -> None:
        self.assertEqual(split_latex_comment("换行\\\\% 注释"), ("换行\\\\", " 注释"))

    def test_no_comment(self) -> None:
        self.assertEqual(split_latex_comment("正文"), ("正文", ""))


class LatexTreeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        write(self.root / "main.tex",
              "\\input{extraTex/@config.tex}\n"
              "\\input{extraTex/1.1.立项依据.tex}\n"
              "% \\input{extraTex/old.tex}\n"
              "\\input{references/reference.tex}\n"
              "\\input{../../outside}\n")
        write(self.root / "extraTex" / "@config.tex", "% config\n")
        write(self.root / "extraTex" / "1.1.立项依据.tex", "正文\n")
        write(self.root / "extraTex" / "old.tex", "旧\n")
        write(self.root / "references" / "reference.tex", "\\bibliography{references/myexample}\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_follows_inputs_and_finds_bib_in_input_file(self) -> None:
        tree = scan_latex_tree(self.root)
        self.assertEqual([relpath(self.root, p) for p in tree.tex_files],
                         ["main.tex", "extraTex/@config.tex", "extraTex/1.1.立项依据.tex", "references/reference.tex"])
        self.assertEqual([relpath(self.root, p) for p in tree.bib_files], ["references/myexample.bib"])

    def test_comma_list_and_addbibresource(self) -> None:
        write(self.root / "references" / "reference.tex",
              "\\bibliography{refs/a, refs/b.bib}\n\\addbibresource[label=x]{refs/c.bib}\n")
        tree = scan_latex_tree(self.root)
        self.assertEqual([relpath(self.root, p) for p in tree.bib_files], ["refs/a.bib", "refs/b.bib", "refs/c.bib"])

    def test_missing_main_tex(self) -> None:
        (self.root / "main.tex").unlink()
        with self.assertRaises(ProposalError):
            scan_latex_tree(self.root)

    def test_real_nsfc_young_template(self) -> None:
        template = ROOT / "projects" / "NSFC_Young"
        tree = scan_latex_tree(template)
        compiled = {relpath(template, p) for p in tree.tex_files}
        self.assertIn("extraTex/1.1.立项依据.tex", compiled)
        self.assertNotIn("extraTex/4.5.生成式人工智能.tex", compiled)
        self.assertEqual([relpath(template, p) for p in tree.bib_files], ["references/myexample.bib"])


class BibIndexTest(unittest.TestCase):
    def test_keys_and_doi_spellings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bib = write(Path(tmp) / "refs.bib",
                        "@comment{ignored, text}\n"
                        "@ARTICLE{John1997,\n  DOI = {https://doi.org/10.1007/S00330-021-07948-0},\n}\n"
                        "@article{yang2019computerized,\n  doi = \"10.1177/0284185119826536\",\n}\n"
                        "@article{nodoi2020,\n  title = {No DOI},\n}\n"
                        "@article{under2021,\n  doi = {10.1000/abc\\_def},\n}")
            index = read_bib_index([bib, Path(tmp) / "absent.bib"])
            self.assertEqual(index.keys, frozenset({"John1997", "yang2019computerized", "nodoi2020", "under2021"}))
            self.assertEqual(index.doi_keys["10.1007/s00330-021-07948-0"], "John1997")
            self.assertIn("10.1177/0284185119826536", index.dois)
            self.assertIn("10.1000/abc_def", index.dois)

    def test_normalize_doi(self) -> None:
        self.assertEqual(normalize_doi("https://dx.doi.org/10.3389/FONC.2020.00838."), "10.3389/fonc.2020.00838")
        self.assertEqual(normalize_doi("doi: 10.2214/AJR.24.31675"), "10.2214/ajr.24.31675")
        self.assertIsNone(normalize_doi(""))


class ProjectPathTest(unittest.TestCase):
    def test_escape_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProposalError):
                project_path(Path(tmp), "../etc/passwd")


class AppendUnderHeadingTest(unittest.TestCase):
    def test_appends_in_order_under_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "a.md", "# 标题\n\n## 确认点状态\n\n## AI 拟定项\n")
            append_under_heading(path, "## 确认点状态", "- 第一条")
            append_under_heading(path, "## 确认点状态", "- 第二条")
            self.assertEqual(path.read_text(encoding="utf-8"),
                             "# 标题\n\n## 确认点状态\n\n- 第一条\n- 第二条\n\n## AI 拟定项\n")

    def test_creates_missing_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "a.md", "# 标题\n")
            append_under_heading(path, "## 未核实线索", "- [unverified] X")
            self.assertEqual(path.read_text(encoding="utf-8"), "# 标题\n\n## 未核实线索\n\n- [unverified] X\n")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_latex_files.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'latex_files'`。

- [ ] **Step 3: 实现 `proposal_common.py`**

```python
"""nsfc-proposal 脚本共用的路径、YAML、配置与文本工具。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_DIRNAME = "proposal"


class ProposalError(ValueError):
    """输入、路径或文件内容不合法；CLI 以退出码 2 报告。"""


@dataclass(frozen=True)
class ProposalPaths:
    root: Path
    case: Path
    case_md: Path
    evidence: Path
    plan: Path
    assumptions: Path
    leads: Path


def read_yaml(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProposalError(f"文件不存在：{path}") from exc
    except yaml.YAMLError as exc:
        raise ProposalError(f"{Path(path).name} 不是合法 YAML：{exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ProposalError(f"{Path(path).name} 顶层必须是映射")
    return data


def write_yaml(path: Path, data: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


def load_config() -> Dict[str, Any]:
    return read_yaml(SKILL_ROOT / "config.yaml")


def resolve_project_root(path: Path | str) -> Path:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ProposalError(f"project_root 不存在或不是目录：{root}")
    return root


def project_path(project_root: Path, relpath: str) -> Path:
    root = Path(project_root).resolve()
    target = (root / relpath).resolve()
    if target != root and root not in target.parents:
        raise ProposalError(f"路径越出 project_root：{relpath}")
    return target


def proposal_paths(project_root: Path) -> ProposalPaths:
    base = project_path(project_root, PROPOSAL_DIRNAME)
    return ProposalPaths(
        root=base,
        case=base / "scientific_case.yaml",
        case_md=base / "scientific_case.md",
        evidence=base / "evidence_map.yaml",
        plan=base / "section_plan.yaml",
        assumptions=base / "assumptions.md",
        leads=base / "literature_leads.md",
    )


def split_latex_comment(line: str) -> tuple[str, str]:
    """把一行 LaTeX 拆成（正文，注释）。前面有奇数个反斜杠的 % 是转义字符，不是注释。"""
    for index, char in enumerate(line):
        if char != "%":
            continue
        backslashes = 0
        j = index - 1
        while j >= 0 and line[j] == "\\":
            backslashes += 1
            j -= 1
        if backslashes % 2 == 0:
            return line[:index], line[index + 1:]
    return line, ""


def append_under_heading(path: Path, heading: str, line: str) -> None:
    """在 Markdown 文件的指定二级标题下追加一行；标题不存在时在文件末尾新建。"""
    target = Path(path)
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    if heading in lines:
        start = lines.index(heading)
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        if insert_at == start + 1:
            lines[insert_at:insert_at] = ["", line]
        else:
            lines.insert(insert_at, line)
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([heading, "", line])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: 实现 `latex_files.py`**

```python
"""沿 main.tex 的 \\input/\\include 遍历编译树，找出被编译的 .tex 与 \\bibliography 指向的 .bib。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from proposal_common import ProposalError, split_latex_comment

INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
BIB_RE = re.compile(r"\\(?:bibliography|addbibresource(?:\[[^\]]*\])?)\{([^}]+)\}")
ENTRY_START_RE = re.compile(r"@([A-Za-z]+)\s*[{(]\s*([^,\s]*)\s*,?")
DOI_FIELD_RE = re.compile(r"\bdoi\s*=\s*[{\"]\s*([^}\"]+?)\s*[}\"]", re.IGNORECASE)
NON_ENTRY_TYPES = {"comment", "string", "preamble"}


@dataclass(frozen=True)
class LatexTree:
    tex_files: list[Path]
    bib_files: list[Path]


@dataclass(frozen=True)
class BibIndex:
    keys: frozenset[str]
    doi_keys: dict[str, str] = field(default_factory=dict)

    @property
    def dois(self) -> frozenset[str]:
        return frozenset(self.doi_keys)


def _inside(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def scan_latex_tree(project_root: Path) -> LatexTree:
    root = Path(project_root).resolve()
    main = root / "main.tex"
    if not main.is_file():
        raise ProposalError(f"project_root 缺少 main.tex：{root}")
    tex_files: list[Path] = []
    bib_files: list[Path] = []
    queue = [main]
    while queue:
        tex = queue.pop(0)
        if tex in tex_files or not tex.is_file():
            continue
        tex_files.append(tex)
        for raw in tex.read_text(encoding="utf-8", errors="replace").splitlines():
            line, _ = split_latex_comment(raw)
            for match in INPUT_RE.finditer(line):
                name = match.group(1).strip()
                child = (root / (name if name.endswith(".tex") else name + ".tex")).resolve()
                if _inside(root, child):
                    queue.append(child)
            for match in BIB_RE.finditer(line):
                for name in match.group(1).split(","):
                    name = name.strip()
                    if not name:
                        continue
                    bib = (root / (name if name.endswith(".bib") else name + ".bib")).resolve()
                    if _inside(root, bib) and bib not in bib_files:
                        bib_files.append(bib)
    return LatexTree(tex_files=tex_files, bib_files=bib_files)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip().replace("\\_", "_")
    raw = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^doi:\s*", "", raw, flags=re.IGNORECASE).strip().rstrip(".,;")
    return raw.lower() or None


def read_bib_index(bib_files: list[Path]) -> BibIndex:
    keys: set[str] = set()
    doi_keys: dict[str, str] = {}
    for path in bib_files:
        if not Path(path).is_file():
            continue
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        starts = list(ENTRY_START_RE.finditer(text))
        for index, match in enumerate(starts):
            if match.group(1).lower() in NON_ENTRY_TYPES or not match.group(2):
                continue
            key = match.group(2)
            keys.add(key)
            end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
            doi_match = DOI_FIELD_RE.search(text, match.end(), end)
            doi = normalize_doi(doi_match.group(1)) if doi_match else None
            if doi:
                doi_keys.setdefault(doi, key)
    return BibIndex(keys=frozenset(keys), doi_keys=doi_keys)


def relpath(project_root: Path, path: Path) -> str:
    return Path(path).resolve().relative_to(Path(project_root).resolve()).as_posix()
```

（`DOI_FIELD_RE.search(text, pos, endpos)` 只在当前条目范围内查找。）

- [ ] **Step 5: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_latex_files.py`
Expected: 12 passed。

- [ ] **Step 6: 提交**

```bash
git add skills/nsfc-proposal/scripts/proposal_common.py skills/nsfc-proposal/scripts/latex_files.py tests/nsfc-proposal/test_np_latex_files.py
git commit -m "feat(nsfc-proposal): 新增公共工具与 LaTeX 编译树扫描

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: 配置、模板与 `case.py init`

**Files:**
- Create: `skills/nsfc-proposal/config.yaml`
- Create: `skills/nsfc-proposal/assets/scientific_case.yaml`、`assets/evidence_map.yaml`、`assets/section_plan.yaml`
- Create: `skills/nsfc-proposal/scripts/case.py`
- Test: `tests/nsfc-proposal/test_np_init.py`

**Interfaces:**
- Consumes: Task 6 全部接口。
- Produces: `case.InitResult(created: list[Path], warnings: list[str])`；`case.init_proposal(project_root: Path, *, title: str, project_type: str, sections: Sequence[str] | None = None, config: Mapping | None = None) -> InitResult`；`case.load_length_budgets(config) -> list[dict]`；`case.budget_for(file: str, budgets) -> dict | None`；`case.build_parser() -> ArgumentParser`；`case.main(argv=None) -> int`；CLI `case.py init --project-root P --title T --type TYPE [--sections A,B]`。后续 Task 8、9 向 `build_parser` 增加子命令。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-proposal/test_np_init.py
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

from case import init_proposal  # noqa: E402
from proposal_common import ProposalError, proposal_paths, read_yaml  # noqa: E402

COMPILED = ["1.1.立项依据", "2.1.研究内容", "2.2.特色与创新", "2.3.年度研究计划", "3.1.研究基础", "3.2.工作条件"]


def make_project(base: Path) -> Path:
    root = base / "proj"
    extra = root / "extraTex"
    extra.mkdir(parents=True)
    for name in COMPILED + ["4.5.生成式人工智能"]:
        (extra / f"{name}.tex").write_text("\\justifying\n\\NSFCBodyText\n", encoding="utf-8")
    (root / "references").mkdir()
    (root / "references" / "reference.tex").write_text("\\bibliography{references/myexample}\n", encoding="utf-8")
    inputs = "".join(f"\\input{{extraTex/{name}.tex}}\n" for name in COMPILED)
    (root / "main.tex").write_text(inputs + "\\input{references/reference.tex}\n", encoding="utf-8")
    return root


class InitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_project(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_creates_all_files_with_project_fields(self) -> None:
        result = init_proposal(self.root, title="肺磨玻璃结节浸润性预测", project_type="青年科学基金")
        paths = proposal_paths(self.root)
        self.assertEqual(set(result.created), {paths.case, paths.evidence, paths.plan, paths.assumptions, paths.leads})
        case = read_yaml(paths.case)
        self.assertEqual(case["project"]["title"], "肺磨玻璃结节浸润性预测")
        self.assertEqual(case["version"], 1)
        self.assertEqual(case["status"], "draft")
        self.assertIn("研究基础", case["project"]["sections"])

    def test_plan_uses_length_budgets_and_writers(self) -> None:
        init_proposal(self.root, title="T", project_type="青年科学基金")
        files = {f["file"]: f for f in read_yaml(proposal_paths(self.root).plan)["files"]}
        self.assertEqual(files["extraTex/1.1.立项依据.tex"]["length"], {"min": 8000, "max": 10000, "unit": "cjk_chars"})
        self.assertEqual(files["extraTex/1.1.立项依据.tex"]["writer"], "nsfc-justification-writer")
        self.assertIn("技术路线", files["extraTex/1.1.立项依据.tex"]["must_exclude"])
        self.assertIsNone(files["extraTex/3.2.工作条件.tex"]["length"])
        self.assertEqual(files["NSFC-ABSTRACTS.md"]["writer"], "nsfc-abstract")
        self.assertIsNone(files["extraTex/1.1.立项依据.tex"]["written_with_case_version"])

    def test_uncompiled_ai_declaration_falls_back_to_proposal_dir(self) -> None:
        result = init_proposal(self.root, title="T", project_type="青年科学基金")
        files = [f["file"] for f in read_yaml(proposal_paths(self.root).plan)["files"]]
        self.assertIn("proposal/ai_declaration.md", files)
        self.assertNotIn("extraTex/4.5.生成式人工智能.tex", files)
        self.assertTrue(any("4.5.生成式人工智能.tex" in w for w in result.warnings))
        self.assertIn("4.5.生成式人工智能.tex", proposal_paths(self.root).assumptions.read_text(encoding="utf-8"))

    def test_rerun_does_not_overwrite_or_duplicate_warnings(self) -> None:
        init_proposal(self.root, title="旧标题", project_type="青年科学基金")
        result = init_proposal(self.root, title="新标题", project_type="面上项目")
        paths = proposal_paths(self.root)
        self.assertEqual(result.created, [])
        self.assertEqual(read_yaml(paths.case)["project"]["title"], "旧标题")
        self.assertEqual(paths.assumptions.read_text(encoding="utf-8").count("4.5.生成式人工智能.tex"), 1)

    def test_section_subset(self) -> None:
        init_proposal(self.root, title="T", project_type="青年科学基金", sections=["立项依据", "摘要"])
        files = [f["file"] for f in read_yaml(proposal_paths(self.root).plan)["files"]]
        self.assertEqual(files, ["extraTex/1.1.立项依据.tex", "NSFC-ABSTRACTS.md"])

    def test_unknown_section_rejected(self) -> None:
        with self.assertRaises(ProposalError):
            init_proposal(self.root, title="T", project_type="青年科学基金", sections=["不存在的章"])

    def test_non_nsfc_project_rejected(self) -> None:
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        with self.assertRaises(ProposalError):
            init_proposal(empty, title="T", project_type="青年科学基金")


class InitCliTest(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(SCRIPTS / "case.py"), *args], env=env, capture_output=True, text=True, timeout=60)

    def test_cli_success_and_path_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            ok = self._run("init", "--project-root", str(root), "--title", "T", "--type", "青年科学基金")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("已创建", ok.stdout)
            bad = self._run("init", "--project-root", str(Path(tmp) / "absent"), "--title", "T", "--type", "青年科学基金")
            self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_init.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'case'`。

- [ ] **Step 3: 新建 `config.yaml`**

```yaml
skill_info:
  name: nsfc-proposal
  version: 0.1.0
  description: "国自然申请书正文的统一入口：先建立科学论证、证据图谱和章节分工，再调用 nsfc-* 写作 skill 分章写作，并做跨章一致性检查。"
  category: writing
  author: "Lauorie"

workspace:
  task_root: .bensz-api/task-{yyyymmdd-hhmm}-{简短描述}

confirm:
  # ask：在确认点停下等申请人回答；auto：不停，按「先继续」处理并记录
  mode: ask

literature:
  use_wispaper: true
  quick_search_top_n: 20
  deep_search_top_n: 10
  keyword_queries: {min: 5, max: 25}
  bundle_max_queries: 25
  title_similarity: 0.92
  doi_title_similarity: 0.8
  year_window: 1
  http_timeout_s: 15

consistency:
  max_fix_rounds: 2
  hidden_placeholder_words: [待补, 待核实, 待确认, 待填写, TODO]
  extra_internal_id_patterns: ['S\d+']
  placeholder_pattern: '【待补充：[^】]*】'

guardrails:
  # 本 skill 自己写入的正文文件；proposal/ 下的文件；.bib 只追加、写前备份（目标由 main.tex 解析）
  allowed_write_files:
    - extraTex/4.5.生成式人工智能.tex
  allowed_write_dirs:
    - proposal

# 篇幅预算的唯一来源；按文件名与其中 match 通配符匹配
length_budget_source: ../nsfc-length-aligner/config.yaml

sections:
  - name: 立项依据
    file: extraTex/1.1.立项依据.tex
    writer: nsfc-justification-writer
    must_exclude: [实验步骤, 技术路线, 样本量设计, 年度安排, 研究方案细节]
  - name: 研究内容
    file: extraTex/2.1.研究内容.tex
    writer: nsfc-research-content-writer
    must_exclude: [国内外研究现状的展开综述]
  - name: 特色与创新
    file: extraTex/2.2.特色与创新.tex
    writer: nsfc-research-content-writer
    must_exclude: [首次, 国际领先, 填补空白]
  - name: 年度研究计划
    file: extraTex/2.3.年度研究计划.tex
    writer: nsfc-research-content-writer
    must_exclude: [研究背景]
  - name: 研究基础
    file: extraTex/3.1.研究基础.tex
    writer: nsfc-research-foundation-writer
    must_exclude: [申请人未提供的论文、数据或预实验结果]
  - name: 工作条件
    file: extraTex/3.2.工作条件.tex
    writer: nsfc-research-foundation-writer
    must_exclude: [申请人未提供的平台或设备]
  - name: 摘要
    file: NSFC-ABSTRACTS.md
    writer: nsfc-abstract
    must_exclude: [内部编号]
  - name: 生成式人工智能使用说明
    file: extraTex/4.5.生成式人工智能.tex
    fallback_file: proposal/ai_declaration.md
    writer: nsfc-proposal
    must_exclude: [运行日志中没有记录的 AI 使用]
```

- [ ] **Step 4: 新建三个模板**

`assets/scientific_case.yaml`：

```yaml
version: 1
status: draft
project:
  type: ""
  title: ""
  sections: []
research_object:
  object: ""
  target_population: ""
  sample_source: ""
  sample_vs_target_gap: ""
  bias_handling: ""
  source: user
terms: []
importance: []
gaps: []
mainstream_routes: []
questions: []
hypothesis:
  statement: ""
  rationale: []
  predictions: []
  falsification:
    condition: ""
    metric: ""
entry_point: ""
aim: ""
tasks: []
constraints: []
feasibility: []
risks: []
```

`assets/evidence_map.yaml`：

```yaml
version: 1
claims: []
```

`assets/section_plan.yaml`：

```yaml
version: 1
files: []
```

- [ ] **Step 5: 新建 `scripts/case.py`**

```python
#!/usr/bin/env python3
"""nsfc-proposal 共享文件的命令行入口。

退出码：0 成功；1 校验未通过；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from latex_files import relpath, scan_latex_tree
from proposal_common import (
    SKILL_ROOT,
    ProposalError,
    append_under_heading,
    load_config,
    proposal_paths,
    read_yaml,
    resolve_project_root,
    write_yaml,
)

ASSUMPTIONS_TEMPLATE = "# 假设与待核实清单\n\n## 确认点状态\n\n## AI 拟定项\n\n## 待核实项\n\n## 占位清单\n"
LEADS_TEMPLATE = "# 文献线索\n\n## 检索式\n\n## 未核实线索\n"


@dataclass
class InitResult:
    created: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_length_budgets(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """读取 nsfc-length-aligner 的篇幅预算；文件缺失时返回空列表。"""
    source = config.get("length_budget_source")
    if not source:
        return []
    path = (SKILL_ROOT / str(source)).resolve()
    if not path.is_file():
        return []
    standard = read_yaml(path).get("length_standard") or {}
    unit = standard.get("unit") or "cjk_chars"
    budgets = []
    for item in standard.get("files") or []:
        if isinstance(item, Mapping) and item.get("match"):
            budgets.append({"match": str(item["match"]), "min": item.get("min"), "max": item.get("max"), "unit": unit})
    return budgets


def budget_for(file: str, budgets: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    name = Path(file).name
    for budget in budgets:
        if fnmatch.fnmatch(name, budget["match"]) and isinstance(budget["min"], int) and isinstance(budget["max"], int):
            return {"min": budget["min"], "max": budget["max"], "unit": budget["unit"]}
    return None


def _select_sections(config: Mapping[str, Any], names: Sequence[str] | None) -> list[Mapping[str, Any]]:
    sections = [s for s in config.get("sections") or [] if isinstance(s, Mapping)]
    if not names:
        return sections
    known = [str(s["name"]) for s in sections]
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ProposalError(f"未知章节：{'、'.join(unknown)}；可选：{'、'.join(known)}")
    return [s for s in sections if s["name"] in names]


def init_proposal(
    project_root: Path,
    *,
    title: str,
    project_type: str,
    sections: Sequence[str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> InitResult:
    """在 project_root/proposal/ 下建立共享文件骨架；已存在的文件不覆盖。"""
    cfg = config or load_config()
    root = resolve_project_root(project_root)
    if not (root / "extraTex").is_dir():
        raise ProposalError(f"project_root 缺少 extraTex/，不是 NSFC 正文项目：{root}")
    compiled = {relpath(root, p) for p in scan_latex_tree(root).tex_files}
    chosen = _select_sections(cfg, sections)
    budgets = load_length_budgets(cfg)
    result = InitResult()
    plan_files = []
    for section in chosen:
        file = str(section["file"])
        if file.endswith(".tex") and file not in compiled:
            fallback = section.get("fallback_file")
            if fallback:
                result.warnings.append(f"main.tex 未引用 {file}；{section['name']}改写到 {fallback}，需申请人决定放在申请书何处。")
                file = str(fallback)
            else:
                result.warnings.append(f"main.tex 未引用 {file}；该章写入后不会出现在 PDF 中。")
        plan_files.append({
            "file": file,
            "writer": section["writer"],
            "must_include": [],
            "must_exclude": list(section.get("must_exclude") or []),
            "length": budget_for(str(section["file"]), budgets),
            "placeholders": [],
            "written_with_case_version": None,
        })

    paths = proposal_paths(root)
    paths.root.mkdir(parents=True, exist_ok=True)
    if not paths.case.exists():
        case = read_yaml(SKILL_ROOT / "assets" / "scientific_case.yaml")
        case["project"] = {"type": project_type, "title": title, "sections": [str(s["name"]) for s in chosen]}
        write_yaml(paths.case, case)
        result.created.append(paths.case)
    if not paths.evidence.exists():
        write_yaml(paths.evidence, read_yaml(SKILL_ROOT / "assets" / "evidence_map.yaml"))
        result.created.append(paths.evidence)
    if not paths.plan.exists():
        plan = read_yaml(SKILL_ROOT / "assets" / "section_plan.yaml")
        plan["files"] = plan_files
        write_yaml(paths.plan, plan)
        result.created.append(paths.plan)
    for path, template in ((paths.assumptions, ASSUMPTIONS_TEMPLATE), (paths.leads, LEADS_TEMPLATE)):
        if not path.exists():
            path.write_text(template, encoding="utf-8")
            result.created.append(path)
    if paths.assumptions in result.created:
        for warning in result.warnings:
            append_under_heading(paths.assumptions, "## 待核实项", f"- {warning}")
    return result


def cmd_init(args: argparse.Namespace) -> int:
    sections = [s.strip() for s in args.sections.split(",") if s.strip()] if args.sections else None
    result = init_proposal(Path(args.project_root), title=args.title, project_type=args.project_type, sections=sections)
    for path in result.created:
        print(f"已创建：{path}")
    for warning in result.warnings:
        print(f"⚠️ {warning}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="case.py", description="nsfc-proposal 共享文件工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="在 project_root/proposal/ 下建立共享文件骨架（已存在的文件不覆盖）")
    p_init.add_argument("--project-root", required=True)
    p_init.add_argument("--title", required=True)
    p_init.add_argument("--type", dest="project_type", required=True, help="项目类型，如 青年科学基金")
    p_init.add_argument("--sections", help="逗号分隔的章节名；默认全部")
    p_init.set_defaults(func=cmd_init)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/`
Expected: Task 6、7 全部通过（20 passed）。

- [ ] **Step 7: 提交**

```bash
git add skills/nsfc-proposal/config.yaml skills/nsfc-proposal/assets skills/nsfc-proposal/scripts/case.py tests/nsfc-proposal/test_np_init.py
git commit -m "feat(nsfc-proposal): 新增配置、共享文件模板与 case.py init

篇幅预算读取 nsfc-length-aligner 的配置；main.tex 未引用 4.5 生成式人工智能文件时，
AI 使用说明改写到 proposal/ai_declaration.md 并记入待核实项。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: 三份 YAML 的校验规则与 `case.py validate`

**Files:**
- Create: `skills/nsfc-proposal/scripts/case_validate.py`
- Modify: `skills/nsfc-proposal/scripts/case.py`（新增 `cmd_validate` 与子命令）
- Test: `tests/nsfc-proposal/test_np_validate.py`

**Interfaces:**
- Consumes: Task 6 `read_bib_index`、`scan_latex_tree`；Task 7 `build_parser`。
- Produces: `case_validate.validate_case(case: Mapping, evidence: Mapping | None) -> list[str]`；`validate_evidence(evidence: Mapping, bib_keys: set[str] | None) -> list[str]`；`validate_plan(plan: Mapping, case: Mapping) -> list[str]`；`validate_all(case, evidence, plan, *, bib_keys=None) -> list[str]`（每条带 `[scientific_case]`/`[evidence_map]`/`[section_plan]` 前缀）；`case_ids(case) -> set[str]`；`claim_ids(evidence) -> set[str]`；常量 `PLAN_KEYWORDS: dict[str, str]`（字段名 → 中文名，Task 9 渲染用）。CLI `case.py validate --project-root P`。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-proposal/test_np_validate.py
from __future__ import annotations

import copy
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

from case_validate import validate_all, validate_case, validate_evidence, validate_plan  # noqa: E402
from proposal_common import write_yaml  # noqa: E402


def valid_case() -> dict:
    return {
        "version": 1, "status": "draft",
        "project": {"type": "青年科学基金", "title": "基于多模态影像深度学习的肺磨玻璃结节浸润性预测研究", "sections": ["立项依据", "研究内容", "研究基础"]},
        "research_object": {"object": "持续存在的肺磨玻璃结节", "target_population": "低剂量 CT 筛查发现 GGN 的人群",
                            "sample_source": "手术切除并有病理诊断的病例", "sample_vs_target_gap": "手术病例偏向高风险结节",
                            "bias_handling": "说明外推边界", "source": "ai_proposed"},
        "terms": [{"term": "多模态", "definition": "同一次 CT 中瘤内、瘤周、影像组学与深度特征及临床语义信息", "source": "ai_proposed"}],
        "importance": [{"text": "GGN 检出增多", "claim_ids": ["C1"]}],
        "gaps": [{"id": "G1", "text": "瘤周信息的独立贡献未量化", "claim_ids": ["C2"]}],
        "mainstream_routes": [{"name": "影像组学", "limitation": "多为单中心", "claim_ids": ["C2"]}],
        "questions": [{"id": "Q1", "text": "瘤周纹理是否提供独立于瘤内的浸润信息？", "answers_gaps": ["G1"]}],
        "hypothesis": {"statement": "瘤周多尺度纹理携带独立浸润信息", "rationale": ["浸润伴随间质反应"],
                       "predictions": ["调整大小与实性比例后仍有增量"],
                       "falsification": {"condition": "外部队列中增量无统计学意义", "metric": "AUC 差"}},
        "entry_point": "把对应关系的成立条件作为检验对象",
        "aim": "界定瘤周信息的增量与适用边界",
        "tasks": [{"id": "T1", "question": "Q1", "aim": "检验瘤周增量", "indicator": "AUC 差",
                   "baselines": ["病灶大小+实性成分比例模型"], "confounders": ["病灶大小"], "validation": "独立外部队列",
                   "subtasks": [], "depends_on": []}],
        "constraints": [],
        "feasibility": [{"kind": "preliminary", "text": "预实验结果", "source": "missing"}],
        "risks": [{"category": "technical", "risk": "外部数据不足", "mitigation": "多中心合作"},
                  {"category": "schedule", "risk": "伦理审批延迟", "mitigation": "提前申报"},
                  {"category": "resource", "risk": "标注人力不足", "mitigation": "分批标注"}],
    }


def valid_evidence() -> dict:
    return {"version": 1, "claims": [
        {"id": "C1", "text": "GGN 检出增多", "sections": ["立项依据"], "type": "background", "support": "single_verified",
         "evidence": [{"ref": "wu2021value", "role": "supporting", "basis": "full_abstract"}]},
        {"id": "C2", "text": "瘤周独立贡献未量化", "sections": ["立项依据"], "type": "gap", "support": "unsupported",
         "evidence": [{"ref": "lead:L1", "role": "supporting", "basis": "full_abstract"}]},
    ]}


def valid_plan() -> dict:
    return {"version": 1, "files": [
        {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "must_include": ["G1", "Q1", "hypothesis", "entry_point"],
         "must_exclude": ["技术路线"], "length": {"min": 8000, "max": 10000, "unit": "cjk_chars"}, "placeholders": [], "written_with_case_version": None},
        {"file": "extraTex/3.1.研究基础.tex", "writer": "nsfc-research-foundation-writer", "must_include": ["feasibility", "risks"],
         "must_exclude": [], "length": None, "placeholders": ["【待补充：预实验结果】"], "written_with_case_version": None},
    ]}


class ValidCaseTest(unittest.TestCase):
    def test_valid_files_have_no_problems(self) -> None:
        self.assertEqual(validate_all(valid_case(), valid_evidence(), valid_plan(), bib_keys={"wu2021value"}), [])


class CaseRuleTest(unittest.TestCase):
    def _errors(self, mutate) -> list[str]:
        case = valid_case()
        mutate(case)
        return validate_case(case, valid_evidence())

    def assertProblem(self, mutate, fragment: str) -> None:
        errors = self._errors(mutate)
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_question_must_end_with_question_mark(self) -> None:
        self.assertProblem(lambda c: c["questions"][0].update(text="瘤周纹理提供独立信息"), "问号")

    def test_question_must_answer_existing_gap(self) -> None:
        self.assertProblem(lambda c: c["questions"][0].update(answers_gaps=["G9"]), "G9")
        self.assertProblem(lambda c: c["questions"][0].update(answers_gaps=[]), "至少回应一个缺口")

    def test_falsification_required(self) -> None:
        self.assertProblem(lambda c: c["hypothesis"]["falsification"].update(metric=""), "falsification")

    def test_task_links(self) -> None:
        self.assertProblem(lambda c: c["tasks"][0].update(question="Q7"), "Q7")
        self.assertProblem(lambda c: c.update(tasks=[]), "没有对应的研究任务")

    def test_baselines_required(self) -> None:
        self.assertProblem(lambda c: c["tasks"][0].update(baselines=[]), "必比基线")

    def test_sample_gap_and_terms_required(self) -> None:
        self.assertProblem(lambda c: c["research_object"].update(sample_vs_target_gap=""), "sample_vs_target_gap")
        self.assertProblem(lambda c: c.update(terms=[]), "terms")

    def test_three_risks_when_writing_foundation(self) -> None:
        self.assertProblem(lambda c: c.update(risks=c["risks"][:2]), "risks 至少 3 条")
        case = valid_case()
        case["project"]["sections"] = ["立项依据"]
        case["risks"] = []
        self.assertFalse(any("risks" in e for e in validate_case(case, valid_evidence())))

    def test_claim_refs_need_evidence_map(self) -> None:
        self.assertProblem(lambda c: c["gaps"][0].update(claim_ids=["C9"]), "C9")
        self.assertTrue(any("evidence_map" in e for e in validate_case(valid_case(), None)))

    def test_wrong_types_reported_without_exception(self) -> None:
        case = valid_case()
        case["questions"] = "Q1"
        case["tasks"] = ["T1"]
        case["version"] = "2"
        errors = validate_case(case, valid_evidence())
        self.assertTrue(any("questions 必须是列表" in e for e in errors), errors)
        self.assertTrue(any("tasks[0]" in e for e in errors), errors)
        self.assertTrue(any("version" in e for e in errors), errors)


class EvidenceRuleTest(unittest.TestCase):
    def test_overclaimed_support(self) -> None:
        evidence = valid_evidence()
        evidence["claims"][0]["support"] = "multi_verified"
        self.assertTrue(any("multi_verified" in e for e in validate_evidence(evidence, {"wu2021value"})))

    def test_leads_and_snippets_do_not_count(self) -> None:
        evidence = valid_evidence()
        evidence["claims"][1]["support"] = "single_verified"
        self.assertTrue(any("C2" in e for e in validate_evidence(evidence, {"wu2021value"})))

    def test_bibkey_must_exist(self) -> None:
        self.assertTrue(any("wu2021value" in e for e in validate_evidence(valid_evidence(), set())))

    def test_applicant_material_only_for_applicant_results(self) -> None:
        evidence = valid_evidence()
        evidence["claims"][0]["support"] = "applicant_material"
        self.assertTrue(any("applicant_material" in e for e in validate_evidence(evidence, {"wu2021value"})))

    def test_duplicate_ids_and_bad_enums(self) -> None:
        evidence = valid_evidence()
        evidence["claims"][1]["id"] = "C1"
        evidence["claims"][0]["type"] = "opinion"
        errors = validate_evidence(evidence, {"wu2021value"})
        self.assertTrue(any("重复" in e for e in errors), errors)
        self.assertTrue(any("type" in e for e in errors), errors)


class PlanRuleTest(unittest.TestCase):
    def test_unknown_must_include(self) -> None:
        plan = valid_plan()
        plan["files"][0]["must_include"].append("Q9")
        self.assertTrue(any("Q9" in e for e in validate_plan(plan, valid_case())))

    def test_foundation_placeholders_cover_missing_feasibility(self) -> None:
        plan = valid_plan()
        plan["files"][1]["placeholders"] = []
        self.assertTrue(any("placeholders" in e for e in validate_plan(plan, valid_case())))

    def test_bad_length(self) -> None:
        plan = valid_plan()
        plan["files"][0]["length"] = {"min": 9000, "max": 8000}
        self.assertTrue(any("length" in e for e in validate_plan(plan, valid_case())))


class ValidateCliTest(unittest.TestCase):
    def _run(self, root: Path) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(SCRIPTS / "case.py"), "validate", "--project-root", str(root)],
                              env=env, capture_output=True, text=True, timeout=60)

    def test_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            (root / "references").mkdir(parents=True)
            (root / "main.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
            (root / "references" / "refs.bib").write_text("@article{wu2021value,\n title={X},\n}\n", encoding="utf-8")
            write_yaml(root / "proposal" / "scientific_case.yaml", valid_case())
            write_yaml(root / "proposal" / "evidence_map.yaml", valid_evidence())
            write_yaml(root / "proposal" / "section_plan.yaml", valid_plan())
            ok = self._run(root)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            broken = copy.deepcopy(valid_case())
            broken["questions"][0]["text"] = "没有问号"
            write_yaml(root / "proposal" / "scientific_case.yaml", broken)
            bad = self._run(root)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("[scientific_case]", bad.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_validate.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'case_validate'`。

- [ ] **Step 3: 实现 `case_validate.py`**

```python
"""scientific_case / evidence_map / section_plan 的确定性校验（设计文档 5.2–5.4 节）。

只做能用规则判断的检查，论证是否成立由 AI 判断。函数返回错误列表，不抛异常。
"""

from __future__ import annotations

from typing import Any, Mapping

CASE_STATUSES = {"draft", "confirmed", "bypassed"}
SOURCES = {"user", "ai_proposed"}
FEASIBILITY_KINDS = {"paper", "patent", "data", "platform", "preliminary", "team", "collaborator", "condition"}
FEASIBILITY_SOURCES = {"user_material", "missing"}
RISK_CATEGORIES = {"technical", "schedule", "resource"}
CLAIM_TYPES = {"background", "gap", "mechanism", "applicant_result"}
SUPPORT_RANK = {"unsupported": 0, "single_verified": 1, "multi_verified": 2}
SUPPORT_LEVELS = set(SUPPORT_RANK) | {"applicant_material"}
EVIDENCE_ROLES = {"supporting", "counter"}
EVIDENCE_BASES = {"fulltext", "full_abstract"}
QUESTION_ENDINGS = ("？", "?")
FOUNDATION_MARK = "研究基础"
PLAN_KEYWORDS = {
    "hypothesis": "科学假设",
    "entry_point": "切入点",
    "aim": "总体目标",
    "terms": "术语界定",
    "research_object": "研究对象",
    "importance": "重要性",
    "mainstream_routes": "主流路线",
    "feasibility": "可行性",
    "risks": "风险与应对",
    "constraints": "约束",
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _items(container: Mapping[str, Any], key: str, errors: list[str]) -> list[Mapping[str, Any]]:
    value = container.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} 必须是列表")
        return []
    items: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            items.append(item)
        else:
            errors.append(f"{key}[{index}] 必须是映射（键值对）")
    return items


def case_ids(case: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("gaps", "questions", "tasks"):
        for item in _items(case, key, []):
            if _text(item.get("id")):
                ids.add(_text(item.get("id")))
    return ids


def claim_ids(evidence: Mapping[str, Any] | None) -> set[str]:
    if not evidence:
        return set()
    return {_text(c.get("id")) for c in _items(evidence, "claims", []) if _text(c.get("id"))}


def _claim_refs(case: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("importance", "gaps", "mainstream_routes"):
        for item in _items(case, key, []):
            refs.update(_str_list(item.get("claim_ids")))
    return refs


def validate_case(case: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> list[str]:
    errors: list[str] = []
    version = case.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append("version 必须是不小于 1 的整数")
    if case.get("status") not in CASE_STATUSES:
        errors.append("status 必须是 draft、confirmed 或 bypassed")

    research_object = _mapping(case.get("research_object"))
    if not _text(research_object.get("sample_vs_target_gap")):
        errors.append("research_object.sample_vs_target_gap 不能为空；样本与目标人群无差异时写「无」")
    if research_object and research_object.get("source") not in SOURCES:
        errors.append("research_object.source 必须是 user 或 ai_proposed")

    terms = _items(case, "terms", errors)
    if not [t for t in terms if _text(t.get("term")) and _text(t.get("definition"))]:
        errors.append("terms 至少界定一个术语（term 与 definition 都要填）")
    for term in terms:
        if term.get("source") not in SOURCES:
            errors.append(f"术语「{_text(term.get('term')) or '?'}」的 source 必须是 user 或 ai_proposed")

    gap_ids = {_text(g.get("id")) for g in _items(case, "gaps", errors) if _text(g.get("id"))}

    questions = _items(case, "questions", errors)
    if not questions and not isinstance(case.get("questions"), (str, int)):
        errors.append("questions 至少一条")
    question_ids: set[str] = set()
    for question in questions:
        qid = _text(question.get("id")) or "?"
        question_ids.add(qid)
        if not _text(question.get("text")).endswith(QUESTION_ENDINGS):
            errors.append(f"科学问题 {qid} 必须是以问号结尾的疑问句")
        answers = _str_list(question.get("answers_gaps"))
        if not answers:
            errors.append(f"科学问题 {qid} 至少回应一个缺口（answers_gaps）")
        for gid in answers:
            if gid not in gap_ids:
                errors.append(f"科学问题 {qid} 引用了不存在的缺口 {gid}")

    hypothesis = _mapping(case.get("hypothesis"))
    falsification = _mapping(hypothesis.get("falsification"))
    if not _text(hypothesis.get("statement")):
        errors.append("hypothesis.statement 不能为空")
    if not (_text(falsification.get("condition")) and _text(falsification.get("metric"))):
        errors.append("hypothesis.falsification 的 condition 和 metric 都不能为空")

    covered: set[str] = set()
    for task in _items(case, "tasks", errors):
        tid = _text(task.get("id")) or "?"
        ref = _text(task.get("question"))
        if ref not in question_ids:
            errors.append(f"研究任务 {tid} 指向不存在的科学问题 {ref or '（空）'}")
        covered.add(ref)
        if not _str_list(task.get("baselines")):
            errors.append(f"研究任务 {tid} 缺少必比基线（baselines）")
    for qid in sorted(question_ids - covered - {"?"}):
        errors.append(f"科学问题 {qid} 没有对应的研究任务")

    for item in _items(case, "constraints", errors):
        if item.get("source") not in SOURCES:
            errors.append(f"约束「{_text(item.get('text')) or '?'}」的 source 必须是 user 或 ai_proposed")
    for item in _items(case, "feasibility", errors):
        label = _text(item.get("text")) or "?"
        if item.get("kind") not in FEASIBILITY_KINDS:
            errors.append(f"可行性条目「{label}」的 kind 不在允许值内")
        if item.get("source") not in FEASIBILITY_SOURCES:
            errors.append(f"可行性条目「{label}」的 source 必须是 user_material 或 missing")
    risks = _items(case, "risks", errors)
    for risk in risks:
        if risk.get("category") not in RISK_CATEGORIES:
            errors.append(f"风险「{_text(risk.get('risk')) or '?'}」的 category 必须是 technical、schedule 或 resource")
    if FOUNDATION_MARK in _str_list(_mapping(case.get("project")).get("sections")) and len(risks) < 3:
        errors.append("要写研究基础时，risks 至少 3 条")

    refs = _claim_refs(case)
    if refs and evidence is None:
        errors.append("scientific_case 引用了论断编号，但缺少 evidence_map.yaml")
    elif refs:
        for ref in sorted(refs - claim_ids(evidence)):
            errors.append(f"论断编号 {ref} 在 evidence_map.yaml 中不存在")
    return errors


def validate_evidence(evidence: Mapping[str, Any], bib_keys: set[str] | None) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for claim in _items(evidence, "claims", errors):
        cid = _text(claim.get("id")) or "?"
        if cid in seen:
            errors.append(f"论断编号 {cid} 重复")
        seen.add(cid)
        if not _text(claim.get("text")):
            errors.append(f"论断 {cid} 的 text 不能为空")
        claim_type = claim.get("type")
        if claim_type not in CLAIM_TYPES:
            errors.append(f"论断 {cid} 的 type 必须是 {'、'.join(sorted(CLAIM_TYPES))} 之一")
        support = claim.get("support")
        if support not in SUPPORT_LEVELS:
            errors.append(f"论断 {cid} 的 support 必须是 {'、'.join(sorted(SUPPORT_LEVELS))} 之一")
            continue
        entries = claim.get("evidence") or []
        if not isinstance(entries, list):
            errors.append(f"论断 {cid} 的 evidence 必须是列表")
            entries = []
        verified = 0
        for entry in entries:
            if not isinstance(entry, Mapping):
                errors.append(f"论断 {cid} 的 evidence 条目必须是映射")
                continue
            ref = _text(entry.get("ref"))
            if entry.get("role") not in EVIDENCE_ROLES:
                errors.append(f"论断 {cid} 的证据 {ref or '?'} 的 role 必须是 supporting 或 counter")
            is_lead = ref.startswith("lead:")
            if ref and not is_lead and bib_keys is not None and ref not in bib_keys:
                errors.append(f"论断 {cid} 的证据 {ref} 不在 .bib 中")
            if entry.get("role") == "supporting" and ref and not is_lead and entry.get("basis") in EVIDENCE_BASES:
                verified += 1
        if support == "applicant_material":
            if claim_type != "applicant_result":
                errors.append(f"论断 {cid}：applicant_material 只能用于 applicant_result 类论断")
            continue
        allowed = "multi_verified" if verified >= 2 else ("single_verified" if verified == 1 else "unsupported")
        if SUPPORT_RANK[support] > SUPPORT_RANK[allowed]:
            errors.append(f"论断 {cid} 记为 {support}，但已核实的支持证据只够 {allowed}")
    return errors


def validate_plan(plan: Mapping[str, Any], case: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    files = _items(plan, "files", errors)
    if not files:
        errors.append("section_plan.files 至少一条")
    ids = case_ids(case)
    missing_feasibility = [f for f in _items(case, "feasibility", []) if f.get("source") == "missing"]
    seen: set[str] = set()
    for entry in files:
        name = _text(entry.get("file")) or "?"
        if name in seen:
            errors.append(f"文件 {name} 重复出现")
        seen.add(name)
        if not _text(entry.get("writer")):
            errors.append(f"{name} 缺少 writer")
        for key in ("must_include", "must_exclude", "placeholders"):
            if not isinstance(entry.get(key, []), list):
                errors.append(f"{name} 的 {key} 必须是列表")
        for ref in _str_list(entry.get("must_include")):
            if ref not in ids and ref not in PLAN_KEYWORDS:
                errors.append(f"{name} 的 must_include 含未知编号或字段 {ref}")
        length = entry.get("length")
        if length is not None:
            low, high = _mapping(length).get("min"), _mapping(length).get("max")
            if not (isinstance(low, int) and isinstance(high, int) and 0 < low <= high):
                errors.append(f"{name} 的 length 需要满足 0 < min ≤ max 的整数")
        version = entry.get("written_with_case_version")
        if version is not None and (not isinstance(version, int) or isinstance(version, bool)):
            errors.append(f"{name} 的 written_with_case_version 必须是整数或 null")
        if FOUNDATION_MARK in name and len(_str_list(entry.get("placeholders"))) < len(missing_feasibility):
            errors.append(f"{name} 的 placeholders 少于科学论证中标为 missing 的可行性条目（{len(missing_feasibility)} 条）")
    return errors


def validate_all(
    case: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    plan: Mapping[str, Any] | None,
    *,
    bib_keys: set[str] | None = None,
) -> list[str]:
    problems = [f"[scientific_case] {e}" for e in validate_case(case, evidence)]
    if evidence is not None:
        problems += [f"[evidence_map] {e}" for e in validate_evidence(evidence, bib_keys)]
    if plan is not None:
        problems += [f"[section_plan] {e}" for e in validate_plan(plan, case)]
    return problems
```

- [ ] **Step 4: 在 `case.py` 中加入 `validate` 子命令**

import 区追加：

```python
from case_validate import validate_all
from latex_files import read_bib_index
```

（`latex_files` 已有的 import 行改为 `from latex_files import read_bib_index, relpath, scan_latex_tree`。）

在 `cmd_init` 之后加入：

```python
def _load_shared(root: Path) -> tuple[dict, dict | None, dict | None]:
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    evidence = read_yaml(paths.evidence) if paths.evidence.exists() else None
    plan = read_yaml(paths.plan) if paths.plan.exists() else None
    return case, evidence, plan


def cmd_validate(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    case, evidence, plan = _load_shared(root)
    bib = read_bib_index(scan_latex_tree(root).bib_files)
    problems = validate_all(case, evidence, plan, bib_keys=set(bib.keys))
    for problem in problems:
        print(f"✗ {problem}")
    print("✅ 校验通过" if not problems else f"共 {len(problems)} 处不通过")
    return 0 if not problems else 1
```

在 `build_parser` 的 `return parser` 之前加入：

```python
    p_validate = sub.add_parser("validate", help="校验 proposal/ 下的三份 YAML")
    p_validate.add_argument("--project-root", required=True)
    p_validate.set_defaults(func=cmd_validate)
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/`
Expected: 全部通过（Task 6–8 共 39 passed）。

- [ ] **Step 6: 提交**

```bash
git add skills/nsfc-proposal/scripts/case_validate.py skills/nsfc-proposal/scripts/case.py tests/nsfc-proposal/test_np_validate.py
git commit -m "feat(nsfc-proposal): 新增科学论证、证据图谱与章节分工的校验规则

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: 渲染确认点、生成信息表、版本与状态命令

**Files:**
- Create: `skills/nsfc-proposal/scripts/case_render.py`
- Modify: `skills/nsfc-proposal/scripts/case.py`（新增 `render`、`to-info-form`、`bump`、`status`、`mark-written`）
- Test: `tests/nsfc-proposal/test_np_render.py`

**Interfaces:**
- Consumes: Task 8 `PLAN_KEYWORDS`、`_load_shared`；Task 6 `append_under_heading`。
- Produces: `case_render.WRITERS: tuple[str, ...]`；`render_case_md(case: Mapping, evidence: Mapping | None, plan: Mapping | None) -> str`；`info_form(case: Mapping, plan: Mapping | None, writer: str) -> str`（未知 writer 抛 `ProposalError`）。CLI：
  - `case.py render --project-root P` → 写 `proposal/scientific_case.md`
  - `case.py to-info-form --project-root P --writer W --out FILE`
  - `case.py bump --project-root P` → `version` 加一、`status` 置 `draft`、重新渲染
  - `case.py status --project-root P --set confirmed|bypassed` → 写状态、在 `assumptions.md` 的「## 确认点状态」下追加一行、重新渲染
  - `case.py mark-written --project-root P --file REL` → 把该文件的 `written_with_case_version` 设为当前版本

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-proposal/test_np_render.py
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from case_render import info_form, render_case_md  # noqa: E402
from proposal_common import ProposalError, read_yaml, write_yaml  # noqa: E402
from test_np_validate import valid_case, valid_evidence, valid_plan  # noqa: E402


class RenderCaseTest(unittest.TestCase):
    def test_confirm_view_shows_key_items(self) -> None:
        md = render_case_md(valid_case(), valid_evidence(), valid_plan())
        self.assertIn("# 科学论证（第 1 版，状态：草稿）", md)
        self.assertIn("瘤周纹理是否提供独立于瘤内的浸润信息？", md)
        self.assertIn("否定条件：外部队列中增量无统计学意义", md)
        self.assertIn("判定指标：AUC 差", md)
        self.assertIn("**多模态**", md)
        self.assertIn("AI 拟定，待确认", md)
        self.assertIn("样本与目标人群的差异：手术病例偏向高风险结节", md)
        self.assertIn("| extraTex/1.1.立项依据.tex |", md)
        self.assertIn("切入点", md)  # must_include 中的字段名换成中文
        self.assertIn("单篇核实 1", md)


class InfoFormTest(unittest.TestCase):
    def test_justification_form_matches_writer_fields(self) -> None:
        form = info_form(valid_case(), valid_plan(), "nsfc-justification-writer")
        for heading in ("1. **研究对象/应用场景**", "3. **关键科学问题（疑问句，非研究目标）**",
                        "4. **核心科学假设（陈述句，预测性结果，不写验证方式）**", "5. **本项目切入点（差异化切口）**",
                        "8. **主流路线与代表工作（引用先核验）**"):
            self.assertIn(heading, form)
        self.assertIn("8000–10000", form)
        self.assertIn("技术路线", form)  # 本章不写
        self.assertNotIn("Q1", form)

    def test_content_form_lists_subgoal_triplets(self) -> None:
        form = info_form(valid_case(), valid_plan(), "nsfc-research-content-writer")
        self.assertIn("4. **子目标（3–4 个，强制可检验）**", form)
        self.assertIn("对照/基线：病灶大小+实性成分比例模型", form)
        self.assertIn("需控制的混杂：病灶大小", form)
        self.assertNotIn("T1", form)

    def test_foundation_form_marks_missing_items_as_placeholders(self) -> None:
        form = info_form(valid_case(), valid_plan(), "nsfc-research-foundation-writer")
        self.assertIn("## 4. 风险清单", form)
        self.assertIn("【待补充：预实验结果】", form)

    def test_unknown_writer(self) -> None:
        with self.assertRaises(ProposalError):
            info_form(valid_case(), valid_plan(), "nsfc-unknown")


class StateCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        (self.root / "extraTex").mkdir(parents=True)
        (self.root / "main.tex").write_text("", encoding="utf-8")
        write_yaml(self.root / "proposal" / "scientific_case.yaml", valid_case())
        write_yaml(self.root / "proposal" / "evidence_map.yaml", valid_evidence())
        write_yaml(self.root / "proposal" / "section_plan.yaml", valid_plan())
        (self.root / "proposal" / "assumptions.md").write_text("# 假设与待核实清单\n\n## 确认点状态\n\n## AI 拟定项\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(SCRIPTS / "case.py"), *args, "--project-root", str(self.root)],
                              env=env, capture_output=True, text=True, timeout=60)

    def test_render_writes_markdown(self) -> None:
        self.assertEqual(self._run("render").returncode, 0)
        self.assertTrue((self.root / "proposal" / "scientific_case.md").is_file())

    def test_bump_increments_version_and_resets_status(self) -> None:
        self._run("status", "--set", "confirmed")
        proc = self._run("bump")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        case = read_yaml(self.root / "proposal" / "scientific_case.yaml")
        self.assertEqual((case["version"], case["status"]), (2, "draft"))
        self.assertIn("第 2 版", (self.root / "proposal" / "scientific_case.md").read_text(encoding="utf-8"))

    def test_status_records_confirmation(self) -> None:
        proc = self._run("status", "--set", "bypassed")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(read_yaml(self.root / "proposal" / "scientific_case.yaml")["status"], "bypassed")
        text = (self.root / "proposal" / "assumptions.md").read_text(encoding="utf-8")
        self.assertIn("第 1 版：未确认（先继续）", text)

    def test_mark_written(self) -> None:
        self.assertEqual(self._run("mark-written", "--file", "extraTex/1.1.立项依据.tex").returncode, 0)
        files = read_yaml(self.root / "proposal" / "section_plan.yaml")["files"]
        self.assertEqual(files[0]["written_with_case_version"], 1)
        self.assertEqual(self._run("mark-written", "--file", "extraTex/9.9.不存在.tex").returncode, 2)

    def test_to_info_form_writes_file(self) -> None:
        out = Path(self.tmp.name) / "form.md"
        proc = self._run("to-info-form", "--writer", "nsfc-justification-writer", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("NSFC 写作信息表", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_render.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'case_render'`。

- [ ] **Step 3: 实现 `case_render.py`**

```python
"""把科学论证渲染成确认点 Markdown 和三个写作 skill 的信息表。

信息表的字段和标题照抄各写作 skill 的 references/info_form.md，正文中不出现内部编号。
"""

from __future__ import annotations

from typing import Any, Mapping

from case_validate import PLAN_KEYWORDS
from proposal_common import ProposalError

WRITERS = ("nsfc-justification-writer", "nsfc-research-content-writer", "nsfc-research-foundation-writer")
NONE = "（无）"
STATUS_LABELS = {"draft": "草稿", "confirmed": "已确认", "bypassed": "未确认（先继续）"}
SUPPORT_LABELS = {"multi_verified": "多篇核实", "single_verified": "单篇核实", "unsupported": "无文献支持", "applicant_material": "申请人材料"}
FEASIBILITY_GROUPS = (
    ("### 1.1 已发表/已接收论文", {"paper"}),
    ("### 1.2 专利/软件著作权/数据集/平台/原型", {"patent", "data", "platform"}),
    ("### 1.3 预实验/初步结果", {"preliminary"}),
    ("### 2.1 关键成员", {"team"}),
    ("### 2.2 合作单位", {"collaborator"}),
    ("## 3. 条件与资源", {"condition"}),
)
RISK_GROUPS = (("### 4.1 技术风险", "technical"), ("### 4.2 进度风险", "schedule"), ("### 4.3 资源风险", "resource"))


def _t(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _items(case: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = case.get(key)
    return [v for v in value if isinstance(v, Mapping)] if isinstance(value, list) else []


def _strs(value: Any) -> list[str]:
    return [v.strip() for v in value if isinstance(v, str) and v.strip()] if isinstance(value, list) else []


def _bullets(lines: list[str], indent: str = "") -> str:
    return "\n".join(f"{indent}- {line}" for line in lines) if lines else f"{indent}- {NONE}"


def _id_texts(case: Mapping[str, Any]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for key, field in (("gaps", "text"), ("questions", "text"), ("tasks", "aim")):
        for item in _items(case, key):
            if _t(item.get("id")):
                texts[_t(item["id"])] = _t(item.get(field)) or NONE
    return texts


def _describe(ref: str, ids: Mapping[str, str]) -> str:
    if ref in PLAN_KEYWORDS:
        return PLAN_KEYWORDS[ref]
    text = ids.get(ref, ref)
    return text if len(text) <= 24 else text[:24] + "…"


def _plan_entries(plan: Mapping[str, Any] | None, writer: str) -> list[Mapping[str, Any]]:
    if not plan:
        return []
    return [f for f in _items(plan, "files") if f.get("writer") == writer]


def _ai_marker(item: Mapping[str, Any]) -> str:
    return "（AI 拟定，待确认）" if item.get("source") == "ai_proposed" else ""


def _placeholder(text: str) -> str:
    return f"【待补充：{text}】"


def render_case_md(case: Mapping[str, Any], evidence: Mapping[str, Any] | None, plan: Mapping[str, Any] | None) -> str:
    ids = _id_texts(case)
    gaps = {k: v for k, v in ids.items() if any(_t(g.get("id")) == k for g in _items(case, "gaps"))}
    hypothesis = case.get("hypothesis") if isinstance(case.get("hypothesis"), Mapping) else {}
    falsification = hypothesis.get("falsification") if isinstance(hypothesis.get("falsification"), Mapping) else {}
    obj = case.get("research_object") if isinstance(case.get("research_object"), Mapping) else {}
    status = STATUS_LABELS.get(str(case.get("status")), str(case.get("status")))
    out = [f"# 科学论证（第 {case.get('version')} 版，状态：{status}）", "", "> 由 proposal/scientific_case.yaml 生成，请勿手改本文件。", ""]

    out += ["## 科学问题", ""]
    for question in _items(case, "questions"):
        answered = "；".join(gaps.get(g, g) for g in _strs(question.get("answers_gaps")))
        out.append(f"- {_t(question.get('text')) or NONE}（回应的缺口：{answered or NONE}）")
    out.append("")

    out += ["## 科学假设", "", _t(hypothesis.get("statement")) or NONE, ""]
    out.append(f"- 否定条件：{_t(falsification.get('condition')) or NONE}")
    out.append(f"- 判定指标：{_t(falsification.get('metric')) or NONE}")
    for prediction in _strs(hypothesis.get("predictions")):
        out.append(f"- 可检验的推论：{prediction}")
    out.append("")

    out += ["## 术语界定", ""]
    out.append(_bullets([f"**{_t(t.get('term'))}**：{_t(t.get('definition'))}{_ai_marker(t)}" for t in _items(case, "terms")]))
    out.append("")

    out += ["## 研究对象", ""]
    for label, key in (("研究对象", "object"), ("目标人群", "target_population"), ("样本来源", "sample_source"),
                       ("样本与目标人群的差异", "sample_vs_target_gap"), ("偏倚处理", "bias_handling")):
        out.append(f"- {label}：{_t(obj.get(key)) or NONE}")
    if obj.get("source") == "ai_proposed":
        out.append("- 以上由 AI 拟定，待确认")
    out.append("")

    out += ["## 各章分工", "", "| 文件 | 写作 skill | 必写 | 不写 | 篇幅 |", "|---|---|---|---|---|"]
    for entry in _items(plan or {}, "files"):
        include = "；".join(_describe(r, ids) for r in _strs(entry.get("must_include"))) or NONE
        exclude = "；".join(_strs(entry.get("must_exclude"))) or NONE
        length = entry.get("length") if isinstance(entry.get("length"), Mapping) else None
        size = f"{length.get('min')}–{length.get('max')} 字" if length else NONE
        out.append(f"| {entry.get('file')} | {entry.get('writer')} | {include} | {exclude} | {size} |")
    out.append("")

    ai_items = [f"术语「{_t(t.get('term'))}」" for t in _items(case, "terms") if t.get("source") == "ai_proposed"]
    if obj.get("source") == "ai_proposed":
        ai_items.insert(0, "研究对象与样本来源")
    ai_items += [f"约束「{_t(c.get('text'))}」" for c in _items(case, "constraints") if c.get("source") == "ai_proposed"]
    out += ["## AI 拟定的条目（需要你确认）", "", _bullets(ai_items), ""]

    counts = {label: 0 for label in SUPPORT_LABELS.values()}
    for claim in _items(evidence or {}, "claims"):
        label = SUPPORT_LABELS.get(str(claim.get("support")))
        if label:
            counts[label] += 1
    total = sum(counts.values())
    out += ["## 证据概况", "", f"论断 {total} 条：" + "，".join(f"{k} {v}" for k, v in counts.items()), ""]
    return "\n".join(out)


def _section_notes(plan: Mapping[str, Any] | None, writer: str) -> list[str]:
    notes = []
    for entry in _plan_entries(plan, writer):
        length = entry.get("length") if isinstance(entry.get("length"), Mapping) else None
        if length:
            notes.append(f"{entry.get('file')} 篇幅：{length.get('min')}–{length.get('max')} 字")
        exclude = _strs(entry.get("must_exclude"))
        if exclude:
            notes.append(f"{entry.get('file')} 不写：{'；'.join(exclude)}")
    notes.append("措辞强度不得超过 proposal/evidence_map.yaml 中各论断的 support；正文不得出现任何内部编号")
    return notes


def _object_line(case: Mapping[str, Any]) -> str:
    obj = case.get("research_object") if isinstance(case.get("research_object"), Mapping) else {}
    parts = [f"{label}：{_t(obj.get(key))}" for label, key in (("研究对象", "object"), ("目标人群", "target_population"),
             ("样本来源", "sample_source"), ("样本与目标人群的差异", "sample_vs_target_gap"), ("偏倚处理", "bias_handling")) if _t(obj.get(key))]
    return "；".join(parts) or NONE


def _justification_form(case: Mapping[str, Any], plan: Mapping[str, Any] | None) -> str:
    hypothesis = case.get("hypothesis") if isinstance(case.get("hypothesis"), Mapping) else {}
    falsification = hypothesis.get("falsification") if isinstance(hypothesis.get("falsification"), Mapping) else {}
    prior = [f"{_t(f.get('text'))}（申请人材料）" if f.get("source") == "user_material" else f"缺失：正文写占位 {_placeholder(_t(f.get('text')))}" for f in _items(case, "feasibility")]
    extra = [f"术语口径：{_t(t.get('term'))}——{_t(t.get('definition'))}" for t in _items(case, "terms")]
    extra.append(f"否定条件：{_t(falsification.get('condition')) or NONE}（判定指标：{_t(falsification.get('metric')) or NONE}）")
    extra += _section_notes(plan, "nsfc-justification-writer")
    lines = [
        f"# NSFC 写作信息表（nsfc-proposal 第 {case.get('version')} 版科学论证）", "",
        "## 必填",
        f"1. **研究对象/应用场景**：{_object_line(case)}",
        "2. **痛点与现有不足**：", _bullets([_t(g.get("text")) for g in _items(case, "gaps")], "   "),
        "3. **关键科学问题（疑问句，非研究目标）**：", _bullets([_t(q.get("text")) for q in _items(case, "questions")], "   "),
        f"4. **核心科学假设（陈述句，预测性结果，不写验证方式）**：{_t(hypothesis.get('statement')) or NONE}",
        "5. **本项目切入点（差异化切口）**：", _bullets([_t(case.get("entry_point"))] if _t(case.get("entry_point")) else [], "   "),
        "", "## 选填",
        "6. **拟解决技术/方法概览**：", _bullets([_t(t.get("aim")) for t in _items(case, "tasks")], "   "),
        "7. **前期基础（可核验）**：", _bullets(prior, "   "),
        "8. **主流路线与代表工作（引用先核验）**：", _bullets([f"{_t(r.get('name'))}：{_t(r.get('limitation'))}" for r in _items(case, "mainstream_routes")], "   "),
        "", "## 可选补充", _bullets(extra),
    ]
    return "\n".join(lines) + "\n"


def _content_form(case: Mapping[str, Any], plan: Mapping[str, Any] | None) -> str:
    hypothesis = case.get("hypothesis") if isinstance(case.get("hypothesis"), Mapping) else {}
    questions = {_t(q.get("id")): _t(q.get("text")) for q in _items(case, "questions")}
    tasks = _items(case, "tasks")
    aims = {_t(t.get("id")): _t(t.get("aim")) for t in tasks}
    subgoals, breakdown, validations = [], [], []
    for task in tasks:
        subgoals.append(
            f"子目标：{_t(task.get('aim')) or NONE}；对应科学问题：{questions.get(_t(task.get('question')), NONE)}；"
            f"指标：{_t(task.get('indicator')) or NONE}；对照/基线：{'、'.join(_strs(task.get('baselines'))) or NONE}；"
            f"需控制的混杂：{'、'.join(_strs(task.get('confounders'))) or NONE}；验证：{_t(task.get('validation')) or NONE}")
        deps = "、".join(aims.get(d, d) for d in _strs(task.get("depends_on")))
        breakdown.append(f"{_t(task.get('aim')) or NONE}：{'；'.join(_strs(task.get('subtasks'))) or NONE}" + (f"（依赖：{deps}）" if deps else ""))
        validations.append(f"{_t(task.get('aim')) or NONE}：{_t(task.get('validation')) or NONE}")
    routes = [f"{_t(r.get('name'))}：{_t(r.get('limitation'))}" for r in _items(case, "mainstream_routes")]
    if _t(case.get("entry_point")):
        routes.append(f"本项目切入点：{_t(case.get('entry_point'))}")
    constraints = [_t(c.get("text")) + ("（AI 拟定）" if c.get("source") == "ai_proposed" else "") for c in _items(case, "constraints")]
    risks = [f"{_t(r.get('risk'))}；应对：{_t(r.get('mitigation'))}" for r in _items(case, "risks")]
    lines = [
        f"# NSFC 写作信息表（面向（二）研究内容；nsfc-proposal 第 {case.get('version')} 版科学论证）", "",
        f"1. **研究对象/应用场景**：{_object_line(case)}",
        f"2. **核心科学问题与假说**：假说：{_t(hypothesis.get('statement')) or NONE}；科学问题：{'；'.join(questions.values()) or NONE}",
        f"3. **总体目标**：{_t(case.get('aim')) or NONE}",
        "4. **子目标（3–4 个，强制可检验）**：", _bullets(subgoals, "   "),
        f"5. **技术路线概览**：{' → '.join(a for a in aims.values() if a) or NONE}",
        "6. **关键方法与验证**：", _bullets(validations, "   "),
        "7. **年度资源约束**：", _bullets(constraints, "   "),
        "8. **任务分解**：", _bullets(breakdown, "   "),
        "9. **创新对照坐标系**：", _bullets(routes, "   "),
        "10. **三年计划的硬约束**：见第 7 项",
        "11. **关键风险与备选路线**：", _bullets(risks, "   "),
        "", "## 可选补充", _bullets(_section_notes(plan, "nsfc-research-content-writer") + ["子目标编号只用于内部规划，正文用自然语言指代"]),
    ]
    return "\n".join(lines) + "\n"


def _foundation_form(case: Mapping[str, Any], plan: Mapping[str, Any] | None) -> str:
    feasibility = _items(case, "feasibility")
    lines = [f"# NSFC 写作信息表（面向（三）研究基础；nsfc-proposal 第 {case.get('version')} 版科学论证）", "", "## 1. 前期基础（证据链素材）"]
    for heading, kinds in FEASIBILITY_GROUPS:
        if heading.startswith("### 2.1"):
            lines += ["", "## 2. 团队与分工"]
        entries = []
        for item in feasibility:
            if item.get("kind") not in kinds:
                continue
            text = _t(item.get("text"))
            entries.append(text if item.get("source") == "user_material" else f"缺失，正文写占位 {_placeholder(text)}，不得略去或编造")
        lines += ["", heading, _bullets(entries)]
    lines += ["", "## 4. 风险清单"]
    for heading, category in RISK_GROUPS:
        risks = [f"{_t(r.get('risk'))}；应对：{_t(r.get('mitigation'))}" for r in _items(case, "risks") if r.get("category") == category]
        lines += ["", heading, _bullets(risks)]
    lines += ["", "## 研究任务（可行性需逐条覆盖）", _bullets([_t(t.get("aim")) for t in _items(case, "tasks")])]
    lines += ["", "## 可选补充", _bullets(_section_notes(plan, "nsfc-research-foundation-writer"))]
    return "\n".join(lines) + "\n"


def info_form(case: Mapping[str, Any], plan: Mapping[str, Any] | None, writer: str) -> str:
    builders = {
        "nsfc-justification-writer": _justification_form,
        "nsfc-research-content-writer": _content_form,
        "nsfc-research-foundation-writer": _foundation_form,
    }
    if writer not in builders:
        raise ProposalError(f"未知写作 skill：{writer}；可选：{'、'.join(WRITERS)}")
    return builders[writer](case, plan)
```

- [ ] **Step 4: 在 `case.py` 中加入五个子命令**

import 区追加：

```python
from datetime import datetime

from case_render import WRITERS, info_form, render_case_md
```

在 `cmd_validate` 之后加入：

```python
def _render(root: Path) -> Path:
    case, evidence, plan = _load_shared(root)
    paths = proposal_paths(root)
    paths.case_md.write_text(render_case_md(case, evidence, plan), encoding="utf-8")
    return paths.case_md


def cmd_render(args: argparse.Namespace) -> int:
    print(f"已生成：{_render(resolve_project_root(args.project_root))}")
    return 0


def cmd_to_info_form(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    case, _, plan = _load_shared(root)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(info_form(case, plan, args.writer), encoding="utf-8")
    print(f"已生成：{out}")
    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    version = case.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ProposalError("scientific_case.yaml 的 version 不是整数，无法加一")
    case["version"] = version + 1
    case["status"] = "draft"
    write_yaml(paths.case, case)
    _render(root)
    print(f"科学论证升至第 {case['version']} 版")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    case["status"] = args.set
    write_yaml(paths.case, case)
    label = "已确认" if args.set == "confirmed" else "未确认（先继续）"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    append_under_heading(paths.assumptions, "## 确认点状态", f"- {stamp} 第 {case.get('version')} 版：{label}")
    _render(root)
    print(f"确认点状态：{label}")
    return 0


def cmd_mark_written(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    plan = read_yaml(paths.plan)
    for entry in plan.get("files") or []:
        if isinstance(entry, dict) and entry.get("file") == args.file:
            entry["written_with_case_version"] = case.get("version")
            write_yaml(paths.plan, plan)
            print(f"{args.file} 依据第 {case.get('version')} 版科学论证")
            return 0
    raise ProposalError(f"section_plan.yaml 中没有文件 {args.file}")
```

在 `build_parser` 的 `return parser` 之前加入：

```python
    p_render = sub.add_parser("render", help="由 scientific_case.yaml 生成 scientific_case.md")
    p_render.add_argument("--project-root", required=True)
    p_render.set_defaults(func=cmd_render)

    p_form = sub.add_parser("to-info-form", help="为某个写作 skill 生成信息表")
    p_form.add_argument("--project-root", required=True)
    p_form.add_argument("--writer", required=True, choices=list(WRITERS))
    p_form.add_argument("--out", required=True)
    p_form.set_defaults(func=cmd_to_info_form)

    p_bump = sub.add_parser("bump", help="修改科学论证后：版本加一、状态置为 draft")
    p_bump.add_argument("--project-root", required=True)
    p_bump.set_defaults(func=cmd_bump)

    p_status = sub.add_parser("status", help="记录确认点的回答")
    p_status.add_argument("--project-root", required=True)
    p_status.add_argument("--set", required=True, choices=["confirmed", "bypassed"])
    p_status.set_defaults(func=cmd_status)

    p_mark = sub.add_parser("mark-written", help="记录某章依据的科学论证版本")
    p_mark.add_argument("--project-root", required=True)
    p_mark.add_argument("--file", required=True)
    p_mark.set_defaults(func=cmd_mark_written)
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/`
Expected: 全部通过（Task 6–9 共 49 passed）。

- [ ] **Step 6: 提交**

```bash
git add skills/nsfc-proposal/scripts/case_render.py skills/nsfc-proposal/scripts/case.py tests/nsfc-proposal/test_np_render.py
git commit -m "feat(nsfc-proposal): 渲染确认点、生成三种信息表，新增版本与状态命令

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: 文献元数据补全与 `.bib` 追加（`bib_resolve.py`）

**Files:**
- Create: `skills/nsfc-proposal/scripts/bib_resolve.py`
- Test: `tests/nsfc-proposal/test_np_bib_resolve.py`

**Interfaces:**
- Consumes: Task 6 `scan_latex_tree`、`read_bib_index`、`BibIndex`、`normalize_doi`、`append_under_heading`、`proposal_paths`；Task 7 `config.yaml` 的 `literature` 段。
- Produces: `@dataclass(frozen=True) WorkMeta(title, authors: tuple[tuple[str, str], ...], journal, year, volume, issue, pages, doi, entry_type="article")`；`@dataclass Outcome(record_id, title, status, bibkey=None, doi=None, source=None, reason=None)`，`status ∈ {added, exists, unresolved}`；`Settings.from_config(config)`；`crossref_meta(item) -> WorkMeta | None`；`openalex_meta(item) -> WorkMeta | None`；`title_matches(wanted: str, candidate: str, threshold: float) -> bool`；`year_ok(wanted, found, window) -> bool`；`make_bibkey(meta, taken: set[str]) -> str`；`to_bibtex(meta, key) -> str`；`lookup(record, *, session, settings) -> tuple[WorkMeta | None, str | None, str | None]`；`resolve_records(records, *, session, settings, index) -> tuple[list[Outcome], list[str]]`；`append_entries(bib_path, entries, backup_dir) -> Path | None`；`run(project_root, records_path, task_root, *, session=None, dry_run=False) -> dict`；CLI `bib_resolve.py --project-root P --records R.jsonl --task-root T [--dry-run]`。
- 汇总 JSON 结构（stdout 与 `<task>/nsfc-proposal/output/bib_resolve.json` 相同）：`{"bib_file": str, "backup": str|null, "dry_run": bool, "counts": {"added": n, "exists": n, "unresolved": n}, "outcomes": [Outcome...]}`。

测试数据全部用虚构条目（DOI 前缀 `10.5555`，作者 Tester 等），不在测试里写任何真实论文的卷期页码。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-proposal/test_np_bib_resolve.py
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import bib_resolve  # noqa: E402
from bib_resolve import CROSSREF_WORKS, OPENALEX_WORKS, USER_AGENT, WorkMeta, make_bibkey, run, title_matches, to_bibtex  # noqa: E402

TITLE_1 = "Peritumoral texture and invasiveness of test nodules in a multicenter cohort study"
CROSSREF_ITEM_1 = {
    "DOI": "10.5555/NSFC.TEST.001", "title": [TITLE_1],
    "author": [{"family": "Tester", "given": "Alice"}, {"family": "Example", "given": "Bob"}],
    "container-title": ["Journal of Test Imaging"], "issued": {"date-parts": [[2024]]},
    "volume": "7", "issue": "2", "page": "100-110", "type": "journal-article",
}
OPENALEX_ITEM_3 = {
    "title": "Reconstruction kernels & texture stability in test scans", "doi": "https://doi.org/10.5555/nsfc.test.003",
    "publication_year": 2022, "authorships": [{"author": {"display_name": "Carol Sample"}}],
    "primary_location": {"source": {"display_name": "Test Physics Letters"}},
    "biblio": {"volume": "3", "issue": None, "first_page": "11", "last_page": "19"},
}


class FakeResponse:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status_code = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """按 URL 返回固定响应；未登记的 URL 返回 404；登记为异常时抛出。"""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict, dict]] = []

    def get(self, url: str, params: Any = None, headers: Any = None, timeout: Any = None) -> FakeResponse:
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        value = self.routes.get(url)
        if isinstance(value, Exception):
            raise value
        return value if value is not None else FakeResponse(404)


def doi_url(doi: str) -> str:
    return f"{CROSSREF_WORKS}/{doi}"


class ResolveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "proj"
        (self.root / "references").mkdir(parents=True)
        (self.root / "proposal").mkdir()
        (self.root / "main.tex").write_text("\\input{references/reference.tex}\n", encoding="utf-8")
        (self.root / "references" / "reference.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
        self.bib = self.root / "references" / "refs.bib"
        self.bib.write_text("@article{old2020,\n  title = {Old},\n}\n", encoding="utf-8")
        (self.root / "proposal" / "literature_leads.md").write_text("# 文献线索\n\n## 检索式\n\n## 未核实线索\n", encoding="utf-8")
        self.task = base / ".bensz-api" / "task-20261009-1200-test"
        self.records = base / "selected.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _records(self, *rows: dict) -> Path:
        self.records.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return self.records

    def _run(self, session: FakeSession, *rows: dict) -> dict:
        return run(self.root, self._records(*rows), self.task, session=session)

    def test_doi_record_added_with_backup(self) -> None:
        session = FakeSession({doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1})})
        summary = self._run(session, {"record_id": "r1", "title": TITLE_1, "year": 2024, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["counts"], {"added": 1, "exists": 0, "unresolved": 0})
        self.assertEqual(summary["outcomes"][0]["bibkey"], "tester2024peritumoral")
        text = self.bib.read_text(encoding="utf-8")
        self.assertIn("@article{tester2024peritumoral,", text)
        self.assertIn("author = {Tester, Alice and Example, Bob}", text)
        self.assertIn("pages = {100--110}", text)
        self.assertIn("doi = {10.5555/nsfc.test.001}", text)
        self.assertTrue(Path(summary["backup"]).is_file())
        self.assertTrue((self.task / "nsfc-proposal" / "output" / "bib_resolve.json").is_file())

    def test_existing_doi_reuses_key_without_request(self) -> None:
        self.bib.write_text("@article{mine2024,\n  doi = {https://doi.org/10.5555/NSFC.TEST.001},\n}\n", encoding="utf-8")
        before = self.bib.read_text(encoding="utf-8")
        session = FakeSession({})
        summary = self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["outcomes"][0]["status"], "exists")
        self.assertEqual(summary["outcomes"][0]["bibkey"], "mine2024")
        self.assertEqual(session.calls, [])
        self.assertEqual(self.bib.read_text(encoding="utf-8"), before)
        self.assertIsNone(summary["backup"])

    def test_truncated_title_matches_by_fragment(self) -> None:
        session = FakeSession({CROSSREF_WORKS: FakeResponse(200, {"message": {"items": [CROSSREF_ITEM_1]}})})
        summary = self._run(session, {"record_id": "r2", "title": "… texture and invasiveness of test nodules in a multicenter cohort …", "year": 2024})
        self.assertEqual(summary["outcomes"][0]["status"], "added")
        self.assertEqual(summary["outcomes"][0]["source"], "crossref")

    def test_openalex_fallback(self) -> None:
        unrelated = dict(CROSSREF_ITEM_1, title=["Something else entirely about cardiac imaging"])
        session = FakeSession({
            CROSSREF_WORKS: FakeResponse(200, {"message": {"items": [unrelated]}}),
            OPENALEX_WORKS: FakeResponse(200, {"results": [OPENALEX_ITEM_3]}),
        })
        summary = self._run(session, {"record_id": "r3", "title": "Reconstruction kernels & texture stability in test scans", "year": 2022})
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["source"]), ("added", "openalex"))
        text = self.bib.read_text(encoding="utf-8")
        self.assertIn("title = {{Reconstruction kernels \\& texture stability in test scans}}", text)
        self.assertIn("author = {Sample, Carol}", text)
        self.assertIn("doi = {10.5555/nsfc.test.003}", text)

    def test_network_failure_goes_to_leads_and_bib_untouched(self) -> None:
        before = self.bib.read_text(encoding="utf-8")
        error = requests.ConnectionError("offline")
        session = FakeSession({doi_url("10.5555/nsfc.test.001"): error, CROSSREF_WORKS: error, OPENALEX_WORKS: error})
        summary = self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["counts"]["unresolved"], 1)
        self.assertIn("ConnectionError", summary["outcomes"][0]["reason"])
        self.assertEqual(self.bib.read_text(encoding="utf-8"), before)
        self.assertIsNone(summary["backup"])
        leads = (self.root / "proposal" / "literature_leads.md").read_text(encoding="utf-8")
        self.assertIn("- [unverified] " + TITLE_1, leads)

    def test_server_error_does_not_stop_other_records(self) -> None:
        session = FakeSession({
            doi_url("10.5555/nsfc.test.009"): FakeResponse(503),
            CROSSREF_WORKS: FakeResponse(503),
            OPENALEX_WORKS: FakeResponse(503),
            doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1}),
        })
        summary = self._run(session,
                            {"record_id": "bad", "title": "Unreachable test paper title for server error", "identifiers": {"doi": "10.5555/nsfc.test.009"}},
                            {"record_id": "good", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["counts"], {"added": 1, "exists": 0, "unresolved": 1})

    def test_append_keeps_entries_separated_without_trailing_newline(self) -> None:
        self.bib.write_text("@article{old2020,\n  title = {Old},\n}", encoding="utf-8")
        session = FakeSession({doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1})})
        self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertIn("}\n\n@article{tester2024peritumoral,", self.bib.read_text(encoding="utf-8"))

    def test_doi_with_mismatched_title_is_unresolved(self) -> None:
        session = FakeSession({doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1})})
        summary = self._run(session, {"record_id": "r4", "title": "A completely different study of liver lesions in rats", "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["outcomes"][0]["status"], "unresolved")
        self.assertIn("不符", summary["outcomes"][0]["reason"])

    def test_requests_carry_no_personal_identity(self) -> None:
        session = FakeSession({CROSSREF_WORKS: FakeResponse(200, {"message": {"items": []}})})
        self._run(session, {"record_id": "r5", "title": "Some test title that will not match anything at all"})
        for _, params, headers in session.calls:
            self.assertEqual(headers.get("User-Agent"), USER_AGENT)
            self.assertNotIn("mailto", json.dumps([params, headers]))


class HelperTest(unittest.TestCase):
    def test_bibkey_collision_and_escape(self) -> None:
        meta = WorkMeta(title="The & test", authors=(("Tëster", "Ann"),), journal="J % Test", year=2024, volume=None, issue=None, pages=None, doi=None)
        taken = {"tester2024test"}
        self.assertEqual(make_bibkey(meta, taken), "tester2024testa")
        entry = to_bibtex(meta, "k")
        self.assertIn("title = {{The \\& test}}", entry)
        self.assertIn("journal = {J \\% Test}", entry)
        self.assertNotIn("doi =", entry)

    def test_title_matching(self) -> None:
        self.assertTrue(title_matches("Peritumoral texture and invasiveness", "Peritumoral Texture and Invasiveness.", 0.92))
        self.assertFalse(title_matches("Peritumoral texture and invasiveness", "Cardiac strain imaging", 0.92))
        self.assertFalse(title_matches("… short …", "Anything with short in it", 0.92))  # 片段不足 20 字符时不匹配


class CliTest(unittest.TestCase):
    def test_task_root_must_be_task_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
            records = Path(tmp) / "r.jsonl"
            records.write_text("", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(SCRIPTS / "bib_resolve.py"), "--project-root", tmp, "--records", str(records),
                                   "--task-root", str(Path(tmp) / "notatask")], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_bib_resolve.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'bib_resolve'`。

- [ ] **Step 3: 实现 `bib_resolve.py`**

```python
#!/usr/bin/env python3
"""把选作证据的文献记录补全成 .bib 条目（设计文档 6.4 节）。

输入：rls.paper.v1 记录（JSONL）。有 DOI 时查 CrossRef 并核对标题；没有 DOI 或核对失败时，
按标题查 CrossRef，再查 OpenAlex。核对成功的条目追加到 main.tex 指向的第一个 .bib
（写前备份，按 DOI 去重）；其余写入 proposal/literature_leads.md，标 [unverified]，正文不得引用。
退出码：0 完成（含未核实条目）；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.parse import quote

import requests

from latex_files import BibIndex, normalize_doi, read_bib_index, scan_latex_tree
from proposal_common import ProposalError, append_under_heading, load_config, proposal_paths, resolve_project_root

USER_AGENT = "nsfc-proposal-bib-resolve/0.1"
CROSSREF_WORKS = "https://api.crossref.org/works"
OPENALEX_WORKS = "https://api.openalex.org/works"
ELLIPSIS_RE = re.compile(r"…|\.\.\.")
MIN_FRAGMENT_CHARS = 20
STOPWORDS = frozenset({"a", "an", "the", "of", "on", "in", "for", "and", "to", "with", "by", "from", "at", "via", "is", "are"})
LATEX_SPECIALS = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_"}


class HttpSession(Protocol):
    def get(self, url: str, params: Mapping[str, Any] | None = None, headers: Mapping[str, str] | None = None,
            timeout: float | None = None) -> Any: ...


@dataclass(frozen=True)
class Settings:
    title_similarity: float = 0.92
    doi_title_similarity: float = 0.8
    year_window: int = 1
    timeout: float = 15.0

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "Settings":
        lit = config.get("literature") or {}
        return cls(
            title_similarity=float(lit.get("title_similarity", 0.92)),
            doi_title_similarity=float(lit.get("doi_title_similarity", 0.8)),
            year_window=int(lit.get("year_window", 1)),
            timeout=float(lit.get("http_timeout_s", 15)),
        )


@dataclass(frozen=True)
class WorkMeta:
    title: str
    authors: tuple[tuple[str, str], ...]
    journal: str | None
    year: int | None
    volume: str | None
    issue: str | None
    pages: str | None
    doi: str | None
    entry_type: str = "article"


@dataclass
class Outcome:
    record_id: str
    title: str
    status: str
    bibkey: str | None = None
    doi: str | None = None
    source: str | None = None
    reason: str | None = None


def _get_json(session: HttpSession, url: str, params: Mapping[str, Any] | None, timeout: float) -> Any | None:
    response = session.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    if getattr(response, "status_code", 200) == 404:
        return None
    response.raise_for_status()
    return response.json()


def _str(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None


def _crossref_year(item: Mapping[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "published"):
        block = item.get(key)
        parts = block.get("date-parts") if isinstance(block, Mapping) else None
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def crossref_meta(item: Mapping[str, Any]) -> WorkMeta | None:
    titles = item.get("title")
    title = titles[0].strip() if isinstance(titles, list) and titles and isinstance(titles[0], str) else ""
    if not title:
        return None
    authors = []
    for author in item.get("author") or []:
        if isinstance(author, Mapping) and (author.get("family") or author.get("name")):
            authors.append((str(author.get("family") or author.get("name")).strip(), str(author.get("given") or "").strip()))
    journals = item.get("container-title")
    journal = journals[0] if isinstance(journals, list) and journals else None
    kind = item.get("type")
    entry_type = "article" if kind in (None, "journal-article") else ("inproceedings" if kind == "proceedings-article" else "misc")
    return WorkMeta(title=title, authors=tuple(authors), journal=_str(journal), year=_crossref_year(item),
                    volume=_str(item.get("volume")), issue=_str(item.get("issue")), pages=_str(item.get("page")),
                    doi=normalize_doi(item.get("DOI")), entry_type=entry_type)


def openalex_meta(item: Mapping[str, Any]) -> WorkMeta | None:
    title = str(item.get("title") or item.get("display_name") or "").strip()
    if not title:
        return None
    authors = []
    for authorship in item.get("authorships") or []:
        name = str(((authorship or {}).get("author") or {}).get("display_name") or "").strip()
        if name:
            parts = name.split()
            authors.append((parts[-1], " ".join(parts[:-1])))
    source = ((item.get("primary_location") or {}).get("source") or {})
    biblio = item.get("biblio") or {}
    first, last = _str(biblio.get("first_page")), _str(biblio.get("last_page"))
    pages = f"{first}--{last}" if first and last and first != last else first
    year = item.get("publication_year") if isinstance(item.get("publication_year"), int) else None
    return WorkMeta(title=title, authors=tuple(authors), journal=_str(source.get("display_name")), year=year,
                    volume=_str(biblio.get("volume")), issue=_str(biblio.get("issue")), pages=pages,
                    doi=normalize_doi(item.get("doi")))


def _norm_title(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_matches(wanted: str, candidate: str, threshold: float) -> bool:
    """完整标题按相似度比较；含省略号的截断标题要求每个足够长的片段都出现在候选标题中。"""
    if ELLIPSIS_RE.search(wanted):
        fragments = [f for f in (_norm_title(p) for p in ELLIPSIS_RE.split(wanted)) if len(f) >= MIN_FRAGMENT_CHARS]
        target = _norm_title(candidate)
        return bool(fragments) and all(f in target for f in fragments)
    return SequenceMatcher(None, _norm_title(wanted), _norm_title(candidate)).ratio() >= threshold


def year_ok(wanted: int | None, found: int | None, window: int) -> bool:
    return wanted is None or found is None or abs(wanted - found) <= window


def _ascii(text: str) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower())


def make_bibkey(meta: WorkMeta, taken: set[str]) -> str:
    family = (_ascii(meta.authors[0][0]) if meta.authors else "") or "anon"
    first = next((w for w in (_ascii(x) for x in _norm_title(meta.title).split()) if w and w not in STOPWORDS), "untitled")
    base = f"{family}{meta.year or 'nd'}{first}"
    key, suffix = base, 0
    while key in taken:
        suffix += 1
        key = base + chr(ord("a") + suffix - 1)
    taken.add(key)
    return key


def _escape(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return "".join(LATEX_SPECIALS.get(ch, ch) for ch in text)


def to_bibtex(meta: WorkMeta, key: str) -> str:
    venue_field = {"article": "journal", "inproceedings": "booktitle"}.get(meta.entry_type, "howpublished")
    authors = " and ".join(f"{_escape(f)}, {_escape(g)}" if g else _escape(f) for f, g in meta.authors)
    pages = meta.pages.replace("-", "--") if meta.pages and "--" not in meta.pages else meta.pages
    fields = [
        ("title", "{" + _escape(meta.title) + "}"),
        ("author", authors or None),
        (venue_field, _escape(meta.journal) if meta.journal else None),
        ("year", str(meta.year) if meta.year else None),
        ("volume", meta.volume),
        ("number", meta.issue),
        ("pages", pages),
        ("doi", meta.doi),
    ]
    lines = [f"@{meta.entry_type}{{{key},"]
    lines += [f"  {name} = {{{value}}}," for name, value in fields if value]
    lines.append("}")
    return "\n".join(lines) + "\n"


def _record_fields(record: Mapping[str, Any]) -> tuple[str | None, str, int | None]:
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), Mapping) else {}
    doi = normalize_doi(identifiers.get("doi") or record.get("doi"))
    title = str(record.get("title") or "").strip()
    year = record.get("year")
    return doi, title, year if isinstance(year, int) and not isinstance(year, bool) else None


def lookup(record: Mapping[str, Any], *, session: HttpSession, settings: Settings) -> tuple[WorkMeta | None, str | None, str | None]:
    """返回 (元数据, 来源, 失败原因)；元数据为 None 时原因非空。"""
    doi, title, year = _record_fields(record)
    failures: list[str] = []
    if doi:
        try:
            data = _get_json(session, f"{CROSSREF_WORKS}/{quote(doi, safe='/')}", None, settings.timeout)
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"CrossRef DOI 查询失败（{type(exc).__name__}）")
        else:
            meta = crossref_meta((data or {}).get("message") or {}) if data else None
            if meta is None:
                failures.append("CrossRef 没有这个 DOI")
            elif title and not title_matches(title, meta.title, settings.doi_title_similarity):
                failures.append(f"DOI {doi} 对应的标题与记录不符")
            else:
                return meta, "crossref", None
    if not title:
        return None, None, "；".join(failures + ["记录没有标题"])
    query = re.sub(r"\s+", " ", ELLIPSIS_RE.sub(" ", title)).strip()
    searches: tuple[tuple[str, str, dict[str, Any], Callable[[Any], list], Callable[[Mapping[str, Any]], WorkMeta | None]], ...] = (
        ("CrossRef", CROSSREF_WORKS, {"query.bibliographic": query, "rows": 5},
         lambda d: ((d or {}).get("message") or {}).get("items") or [], crossref_meta),
        ("OpenAlex", OPENALEX_WORKS, {"search": query, "per-page": 5},
         lambda d: (d or {}).get("results") or [], openalex_meta),
    )
    for label, url, params, items_of, to_meta in searches:
        try:
            data = _get_json(session, url, params, settings.timeout)
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"{label} 标题检索失败（{type(exc).__name__}）")
            continue
        for item in items_of(data):
            meta = to_meta(item) if isinstance(item, Mapping) else None
            if meta and title_matches(title, meta.title, settings.title_similarity) and year_ok(year, meta.year, settings.year_window):
                return meta, label.lower(), None
        failures.append(f"{label} 无标题匹配的条目")
    return None, None, "；".join(failures)


def resolve_records(records: Iterable[Mapping[str, Any]], *, session: HttpSession, settings: Settings,
                    index: BibIndex) -> tuple[list[Outcome], list[str]]:
    taken = set(index.keys)
    known = dict(index.doi_keys)
    outcomes: list[Outcome] = []
    entries: list[str] = []
    for record in records:
        doi, title, _ = _record_fields(record)
        record_id = str(record.get("record_id") or title or "?")
        if doi and doi in known:
            outcomes.append(Outcome(record_id, title, "exists", bibkey=known[doi], doi=doi))
            continue
        meta, source, reason = lookup(record, session=session, settings=settings)
        if meta is None:
            outcomes.append(Outcome(record_id, title, "unresolved", reason=reason))
            continue
        if meta.doi and meta.doi in known:
            outcomes.append(Outcome(record_id, title, "exists", bibkey=known[meta.doi], doi=meta.doi, source=source))
            continue
        key = make_bibkey(meta, taken)
        entries.append(to_bibtex(meta, key))
        if meta.doi:
            known[meta.doi] = key
        outcomes.append(Outcome(record_id, title, "added", bibkey=key, doi=meta.doi, source=source))
    return outcomes, entries


def append_entries(bib_path: Path, entries: list[str], backup_dir: Path) -> Path | None:
    """追加条目；写前备份。没有条目时不碰文件。"""
    if not entries:
        return None
    backup = None
    text = ""
    if bib_path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{bib_path.name}.{datetime.now().strftime('%Y%m%d%H%M%S%f')}.bak"
        shutil.copy2(bib_path, backup)
        text = bib_path.read_text(encoding="utf-8")
    else:
        bib_path.parent.mkdir(parents=True, exist_ok=True)
    if not text:
        separator = ""
    elif text.endswith("\n\n"):
        separator = ""
    elif text.endswith("\n"):
        separator = "\n"
    else:
        separator = "\n\n"
    bib_path.write_text(text + separator + "\n".join(entries), encoding="utf-8")
    return backup


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProposalError(f"无法读取记录文件：{path}") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProposalError(f"{Path(path).name} 第 {number} 行不是合法 JSON") from exc
        if isinstance(value, dict):
            rows.append(value)
    return rows


def run(project_root: Path, records_path: Path, task_root: Path, *, session: HttpSession | None = None, dry_run: bool = False) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    task = Path(task_root).expanduser().resolve()
    if not task.name.startswith("task-"):
        raise ProposalError(f"--task-root 必须指向 .bensz-api/task-*/ 目录：{task}")
    records = _read_jsonl(records_path)
    tree = scan_latex_tree(root)
    if not tree.bib_files:
        raise ProposalError("main.tex 及其 \\input 文件中没有 \\bibliography，无法确定 .bib")
    target = tree.bib_files[0]
    outcomes, entries = resolve_records(records, session=session or requests.Session(),
                                        settings=Settings.from_config(load_config()), index=read_bib_index(tree.bib_files))
    out_dir = task / "nsfc-proposal" / "output"
    backup = None
    if not dry_run:
        backup = append_entries(target, entries, out_dir / "bib_backup")
        leads = proposal_paths(root).leads
        for outcome in outcomes:
            if outcome.status == "unresolved":
                append_under_heading(leads, "## 未核实线索", f"- [unverified] {outcome.title or outcome.record_id}；原因：{outcome.reason}；记录：{outcome.record_id}")
    summary = {
        "bib_file": str(target),
        "backup": str(backup) if backup else None,
        "dry_run": dry_run,
        "counts": {status: sum(1 for o in outcomes if o.status == status) for status in ("added", "exists", "unresolved")},
        "outcomes": [asdict(o) for o in outcomes],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bib_resolve.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bib_resolve.py", description="补全文献元数据并追加到项目 .bib")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--records", required=True, help="rls.paper.v1 JSONL：选作证据的文献记录")
    parser.add_argument("--task-root", required=True, help="本任务的 .bensz-api/task-*/ 目录")
    parser.add_argument("--dry-run", action="store_true", help="只查询与汇总，不写 .bib 和线索文件")
    args = parser.parse_args(argv)
    try:
        summary = run(Path(args.project_root), Path(args.records), Path(args.task_root), dry_run=args.dry_run)
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_bib_resolve.py`
Expected: 12 passed。

- [ ] **Step 5: 联网实测 1 次（设计文档 10.1 节）**

用 2026-10-09 实测中 `deep_search` 返回、带 DOI 的那篇论文（`10.1177/0284185119826536`）做一次真实查询，只读不写。临时文件放在本会话的 scratchpad 目录（下面的 `$L`），不用 `/tmp` 根目录：

```bash
L=/tmp/claude-1001/-home-juli-guoziran/25ac919b-131c-4b62-b3c5-71f4e1b5fe5c/scratchpad/np-live
mkdir -p $L/proj/references $L/.bensz-api/task-20261009-0000-live
printf '\\bibliography{references/refs}\n' > $L/proj/main.tex
: > $L/proj/references/refs.bib
printf '{"record_id":"live1","title":"Computerized texture analysis predicts histological invasiveness within lung adenocarcinoma manifesting as pure ground-glass nodules","year":2019,"identifiers":{"doi":"10.1177/0284185119826536"}}\n' > $L/r.jsonl
PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 skills/nsfc-proposal/scripts/bib_resolve.py --project-root $L/proj --records $L/r.jsonl --task-root $L/.bensz-api/task-20261009-0000-live --dry-run
```

Expected: `counts.added` 为 1，`source` 为 `crossref`。把输出中的作者、期刊、年份与 `https://api.crossref.org/works/10.1177/0284185119826536` 的原始返回逐项比对，结果记入本任务的验证日志。网络不可用时记为「未执行」，不得写成通过。

- [ ] **Step 6: 提交**

```bash
git add skills/nsfc-proposal/scripts/bib_resolve.py tests/nsfc-proposal/test_np_bib_resolve.py
git commit -m "feat(nsfc-proposal): 新增 bib_resolve，经 CrossRef/OpenAlex 核对后追加 .bib

有 DOI 时核对标题；无 DOI 时按标题检索，截断标题按片段匹配。只追加、写前备份、
按 DOI 去重；未核实条目写入 literature_leads.md。请求不带个人身份信息。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: 跨章一致性检查（`consistency_check.py`）

**Files:**
- Create: `skills/nsfc-proposal/scripts/consistency_check.py`
- Test: `tests/nsfc-proposal/test_np_consistency.py`

**Interfaces:**
- Consumes: Task 6 全部；Task 8 `case_ids`、`claim_ids`。
- Produces: `@dataclass(frozen=True) Finding(kind, file, line, detail)`；`@dataclass Report(errors, needs_review, placeholders)`，`to_dict() -> dict`；`check_project(project_root: Path, config: Mapping | None = None) -> Report`；CLI `consistency_check.py --project-root P [--json]`，退出码 0 无 errors、1 有 errors、2 输入错误。
- `kind` 取值：errors 中为 `hidden_placeholder`、`placeholder_unlisted`、`missing_bibkey`、`term_unused`、`stale_section`；needs_review 中为 `internal_id`、`file_not_compiled`；placeholders 中为 `placeholder`。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-proposal/test_np_consistency.py
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consistency_check import check_project  # noqa: E402
from proposal_common import write_yaml  # noqa: E402
from test_np_validate import valid_case, valid_evidence  # noqa: E402

BODY_11 = "\n".join([
    "\\justifying",
    "本项目界定的多模态影像信息\\cite{wu2021value,missing2020}。",
    "占比 50\\% 的病例接受手术。",
    "【待补充：预实验结果】",
    "【待补充：合作医院名称】",
    "% 待补文献：瘤周研究综述",
    "对应 Q1 的研究任务。",
    "采用 T1 加权序列作参照。",
]) + "\n"


def build(base: Path, *, body_11: str = BODY_11, terms: list | None = None) -> Path:
    root = base / "proj"
    (root / "extraTex").mkdir(parents=True)
    (root / "references").mkdir()
    (root / "main.tex").write_text("\\input{extraTex/1.1.立项依据.tex}\n\\input{references/reference.tex}\n", encoding="utf-8")
    (root / "references" / "reference.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
    (root / "references" / "refs.bib").write_text("@article{wu2021value,\n  title = {X},\n}\n", encoding="utf-8")
    (root / "extraTex" / "1.1.立项依据.tex").write_text(body_11, encoding="utf-8")
    (root / "extraTex" / "2.1.研究内容.tex").write_text("研究内容正文。\n", encoding="utf-8")
    case = valid_case()
    case["version"] = 2
    if terms is not None:
        case["terms"] = terms
    write_yaml(root / "proposal" / "scientific_case.yaml", case)
    write_yaml(root / "proposal" / "evidence_map.yaml", valid_evidence())
    write_yaml(root / "proposal" / "section_plan.yaml", {"version": 1, "files": [
        {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "written_with_case_version": 1},
        {"file": "extraTex/2.1.研究内容.tex", "writer": "nsfc-research-content-writer", "written_with_case_version": 2},
        {"file": "NSFC-ABSTRACTS.md", "writer": "nsfc-abstract", "written_with_case_version": None},
    ]})
    (root / "proposal" / "assumptions.md").write_text("# 假设与待核实清单\n\n## 占位清单\n\n- extraTex/1.1.立项依据.tex：【待补充：预实验结果】\n", encoding="utf-8")
    return root


class ConsistencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_errors_and_reviews(self) -> None:
        report = check_project(build(self.base))
        errors = {(f.kind, f.detail if f.kind != "hidden_placeholder" else f.line) for f in report.errors}
        self.assertEqual(errors, {
            ("missing_bibkey", "missing2020"),
            ("placeholder_unlisted", "【待补充：合作医院名称】"),
            ("hidden_placeholder", 6),
            ("stale_section", "依据第 1 版科学论证，当前为第 2 版"),
        })
        reviews = {(f.kind, f.detail) for f in report.needs_review}
        self.assertIn(("internal_id", "Q1"), reviews)
        self.assertIn(("internal_id", "T1"), reviews)
        self.assertIn(("file_not_compiled", "main.tex 未引用该文件，内容不会进入 PDF"), reviews)
        self.assertEqual(len(report.placeholders), 2)

    def test_escaped_percent_is_not_flagged(self) -> None:
        report = check_project(build(self.base, body_11="占比 50\\% 的病例 多模态。\n"))
        self.assertFalse([f for f in report.errors if f.kind == "hidden_placeholder"])

    def test_unused_term(self) -> None:
        report = check_project(build(self.base, terms=[{"term": "影像基因组", "definition": "X", "source": "user"}]))
        self.assertIn(("term_unused", "影像基因组"), {(f.kind, f.detail) for f in report.errors})

    def test_cli_exit_codes_and_json(self) -> None:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        bad_root = build(self.base)
        proc = subprocess.run([sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(bad_root), "--json"],
                              env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(json.loads(proc.stdout)["placeholders"]), 2)
        clean = build(self.base / "clean", body_11="多模态影像信息\\cite{wu2021value}。\n【待补充：预实验结果】\n")
        write_yaml(clean / "proposal" / "section_plan.yaml", {"version": 1, "files": [
            {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "written_with_case_version": 2}]})
        ok = subprocess.run([sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(clean)],
                            env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_consistency.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'consistency_check'`。

- [ ] **Step 3: 实现 `consistency_check.py`**

```python
#!/usr/bin/env python3
"""跨章确定性检查（设计文档 4.7 节）。语义一致性由 AI 判断，不在本脚本内。

errors：必须修正。needs_review：交给 AI 复核，例如疑似内部编号可能是「T1 加权」这类误报。
placeholders：正文中全部可见占位。退出码：0 无 errors；1 有 errors；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from case_validate import case_ids, claim_ids
from latex_files import read_bib_index, relpath, scan_latex_tree
from proposal_common import ProposalError, load_config, project_path, proposal_paths, read_yaml, resolve_project_root, split_latex_comment

CITE_RE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\]){0,2}\{([^}]*)\}")
DEFAULT_PLACEHOLDER = "【待补充：[^】]*】"
LABELS = {
    "hidden_placeholder": "注释中的隐藏占位",
    "placeholder_unlisted": "占位未列入 assumptions.md",
    "missing_bibkey": "引用 key 不在 .bib",
    "term_unused": "界定过的术语未在正文出现",
    "stale_section": "章节依据旧版科学论证",
    "internal_id": "疑似内部编号（请 AI 复核）",
    "file_not_compiled": "文件未被 main.tex 引用",
}


@dataclass(frozen=True)
class Finding:
    kind: str
    file: str
    line: int | None
    detail: str


@dataclass
class Report:
    errors: list[Finding] = field(default_factory=list)
    needs_review: list[Finding] = field(default_factory=list)
    placeholders: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {name: [asdict(f) for f in getattr(self, name)] for name in ("errors", "needs_review", "placeholders")}


def _id_regex(ids: Iterable[str], extra_patterns: Iterable[str]) -> re.Pattern[str] | None:
    patterns = [re.escape(i) for i in sorted(ids)] + [str(p) for p in extra_patterns]
    if not patterns:
        return None
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(patterns) + r")(?![A-Za-z0-9])")


def check_project(project_root: Path, config: Mapping[str, Any] | None = None) -> Report:
    settings = (config or load_config()).get("consistency") or {}
    hidden_words = [str(w) for w in settings.get("hidden_placeholder_words") or []]
    placeholder_re = re.compile(str(settings.get("placeholder_pattern") or DEFAULT_PLACEHOLDER))
    root = resolve_project_root(project_root)
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    evidence = read_yaml(paths.evidence) if paths.evidence.exists() else {}
    plan = read_yaml(paths.plan)
    tree = scan_latex_tree(root)
    compiled = {relpath(root, p) for p in tree.tex_files}
    bib_keys = read_bib_index(tree.bib_files).keys
    assumptions = paths.assumptions.read_text(encoding="utf-8") if paths.assumptions.exists() else ""
    id_re = _id_regex(case_ids(case) | claim_ids(evidence), settings.get("extra_internal_id_patterns") or [])
    entries = [e for e in plan.get("files") or [] if isinstance(e, Mapping) and isinstance(e.get("file"), str)]

    report = Report()
    bodies: list[str] = []
    for entry in entries:
        rel = entry["file"]
        path = project_path(root, rel)
        if not path.is_file():
            continue
        is_tex = rel.endswith(".tex")
        if is_tex and rel not in compiled:
            report.needs_review.append(Finding("file_not_compiled", rel, None, "main.tex 未引用该文件，内容不会进入 PDF"))
        for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            body, comment = split_latex_comment(raw) if is_tex else (raw, "")
            bodies.append(body)
            if comment and any(word in comment for word in hidden_words):
                report.errors.append(Finding("hidden_placeholder", rel, number, comment.strip()[:80]))
            if id_re:
                for match in id_re.finditer(body):
                    report.needs_review.append(Finding("internal_id", rel, number, match.group(0)))
            for match in placeholder_re.finditer(body):
                report.placeholders.append(Finding("placeholder", rel, number, match.group(0)))
                if match.group(0) not in assumptions:
                    report.errors.append(Finding("placeholder_unlisted", rel, number, match.group(0)))
            if is_tex:
                for match in CITE_RE.finditer(body):
                    for key in (k.strip() for k in match.group(1).split(",")):
                        if key and key not in bib_keys:
                            report.errors.append(Finding("missing_bibkey", rel, number, key))

    text = "\n".join(bodies)
    for term in case.get("terms") or []:
        name = term.get("term").strip() if isinstance(term, Mapping) and isinstance(term.get("term"), str) else ""
        if name and name not in text:
            report.errors.append(Finding("term_unused", "", None, name))
    version = case.get("version")
    for entry in entries:
        written = entry.get("written_with_case_version")
        if isinstance(written, int) and isinstance(version, int) and written < version:
            report.errors.append(Finding("stale_section", entry["file"], None, f"依据第 {written} 版科学论证，当前为第 {version} 版"))
    return report


def _print_human(report: Report) -> None:
    for title, items in (("必须修正", report.errors), ("需要复核", report.needs_review)):
        print(f"## {title}（{len(items)}）")
        for f in items:
            where = f"{f.file}:{f.line}" if f.line else (f.file or "全文")
            print(f"- [{LABELS.get(f.kind, f.kind)}] {where} {f.detail}")
    print(f"## 正文占位（{len(report.placeholders)}）")
    for f in report.placeholders:
        print(f"- {f.file}:{f.line} {f.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="consistency_check.py", description="nsfc-proposal 跨章一致性检查")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)
    try:
        report = check_project(Path(args.project_root))
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/`
Expected: 全部通过，0 failed。

- [ ] **Step 5: 提交**

```bash
git add skills/nsfc-proposal/scripts/consistency_check.py tests/nsfc-proposal/test_np_consistency.py
git commit -m "feat(nsfc-proposal): 新增跨章一致性检查

检出注释中的隐藏占位、未登记的占位、缺失的 bibkey、未出现的术语、依据旧版论证的章节；
疑似内部编号交 AI 复核，转义的 \\% 不算注释。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## 阶段三：文档与写作 skill 接入（Task 12–14）

### Task 12: nsfc-proposal 的 SKILL.md、参考文档、README、CHANGELOG

**Files:**
- Create: `skills/nsfc-proposal/SKILL.md`
- Create: `skills/nsfc-proposal/references/scientific_case_guide.md`、`evidence_wording.md`、`section_boundaries.md`、`confirm_prompt.md`
- Create: `skills/nsfc-proposal/README.md`、`skills/nsfc-proposal/CHANGELOG.md`
- Test: `tests/nsfc-proposal/test_np_skill_docs.py`

**Interfaces:**
- Consumes: Task 5 的 `--host-results` 与 `rls.host_results.v1` 格式；Task 3 的 `--task-root`；Task 7–11 的全部 CLI。
- Produces: AI 执行契约。`SKILL.md` 中 `S/...` 指本 skill 目录内路径，`SK/...` 指 skills 根目录内路径；测试据此检查引用的文件都存在。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-proposal/test_np_skill_docs.py
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "nsfc-proposal"
SKILLS = ROOT / "skills"
TEXT = (SKILL / "SKILL.md").read_text(encoding="utf-8") if (SKILL / "SKILL.md").exists() else ""
ORDER = ["## 目标", "## 流程", "### 输入", "### 执行步骤", "### 输出", "### 输出管理", "### 校验", "### 失败与恢复", "## 约束"]


def frontmatter() -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", TEXT, re.S)
    return yaml.safe_load(match.group(1)) if match else {}


class SkillDocTest(unittest.TestCase):
    def test_frontmatter(self) -> None:
        meta = frontmatter()
        self.assertEqual(meta.get("name"), "nsfc-proposal")
        self.assertEqual((meta.get("metadata") or {}).get("author"), "Lauorie")
        description = meta.get("description") or ""
        self.assertTrue(description)
        for leak in ("proposal/", ".yaml", "case.py", "--"):
            self.assertNotIn(leak, description)

    def test_section_order_and_no_control_section(self) -> None:
        headings = [line for line in TEXT.splitlines() if line.startswith(("## ", "### "))]
        positions = [headings.index(h) for h in ORDER]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("## 控制", TEXT)

    def test_common_constraints_block_is_verbatim(self) -> None:
        template = (ROOT / "docs/templates/skill-common-constraints.md").read_text(encoding="utf-8").splitlines()
        block = "\n".join(template[1:]).strip()
        self.assertIn(block, TEXT)

    def test_referenced_files_exist(self) -> None:
        local = set(re.findall(r"(?<![A-Za-z])S/((?:scripts|references|assets)/[\w.\-]+)", TEXT))
        local |= set(re.findall(r"`(references/[\w.\-]+\.md)`", TEXT))
        shared = set(re.findall(r"(?<![A-Za-z])SK/([\w\-]+/(?:scripts/[\w.\-]+|SKILL\.md))", TEXT))
        self.assertTrue(local and shared)
        for rel in sorted(local):
            self.assertTrue((SKILL / rel).is_file(), rel)
        for rel in sorted(shared):
            self.assertTrue((SKILLS / rel).is_file(), rel)

    def test_version_only_in_config(self) -> None:
        config = yaml.safe_load((SKILL / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config["skill_info"]["version"], "0.1.0")
        self.assertNotIn("0.1.0", TEXT)
        self.assertNotIn("0.1.0", (SKILL / "README.md").read_text(encoding="utf-8"))

    def test_changelog(self) -> None:
        changelog = (SKILL / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [0.1.0] - 2026-10-09", changelog)
        self.assertIn("初始化技能，实现核心功能", changelog)
        self.assertIn("本分支未写 BAC 记录，经负责人同意。", changelog)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_skill_docs.py`
Expected: FAIL（`SKILL.md` 不存在，frontmatter 为空）。

- [ ] **Step 3: 新建 `SKILL.md`**

文件内容如下。「## 约束」下的公共约束块与 `docs/templates/skill-common-constraints.md` 第 2 行至末行逐字相同（下文已照抄；若模板在执行前有变化，以模板为准重新复制）。

````markdown
---
name: nsfc-proposal
description: 当用户要写、重写或续写国家自然科学基金申请书正文的多个章节（立项依据、研究内容、研究基础等），或要求各章围绕同一套科学问题与假设、引用可核验时使用。先与申请人确定科学论证，再调用 nsfc-* 写作 skill 分章成稿并做跨章检查。⚠️ 不适用：只改某一章的措辞（用对应的 nsfc-*-writer）、只做评审或质检（用 nsfc-reviewers 或 nsfc-qc）、只写预算或选申请代码（用 nsfc-budget 或 nsfc-code）、尚未确定研究方向而要系统探索选题（先用 research-idea）。
metadata:
  author: Lauorie
---

# 国自然申请书正文总控

## 目标

把申请人的研究想法写成一份各章口径一致的国自然申请书正文。先建立一份科学论证，立项依据、研究内容、研究基础和摘要都从它出发；文献经检索并核对元数据后才能引用。

本 skill 负责：

- 建立并维护 `{project_root}/proposal/` 下的科学论证、证据图谱和章节分工；
- 检索文献，核对元数据后写入 `.bib`；
- 设一个确认点，请申请人确认科学问题与假设；
- 按固定顺序调用写作 skill，并做跨章一致性检查；
- 起草生成式人工智能使用说明。

本 skill 不负责：预算（nsfc-budget）、申请代码（nsfc-code）、模拟评审（nsfc-reviewers）、质检（nsfc-qc）、篇幅压缩（nsfc-length-aligner）、去 AI 腔（nsfc-humanization）、选题探索（research-idea）、PDF 排版。

## 流程

### 输入

- 必需：
  - `project_root`：含 `main.tex` 和 `extraTex/` 的 NSFC 正文项目，例如 `projects/NSFC_Young` 的副本。
  - 申请人的研究信息：题目或方向、研究对象、痛点、科学问题与假设的初步想法、已有材料。
- 可选：项目类型；要写的章节（默认全部）；协作方式；论文、数据、预实验结果；参考文献。
- 缺 `project_root` 时停下，请用户指定；无人值守时报错退出。
- 申请人没提供的信息不追问（确认点除外），按保守假设处理，并记入 `assumptions.md`。

### 执行步骤

下文 `S` 指本 skill 目录，`SK` 指 skills 根目录（本 skill 的上一级），`P` 指 project_root，`T` 指本任务目录。

**0. 说明与建目录**

1. 向用户逐项说明将调用的 skill 及其工作，按调用顺序：research-literature-search（检索文献）→ nsfc-justification-writer（立项依据）→ nsfc-research-content-writer（研究内容、特色与创新、年度研究计划）→ nsfc-research-foundation-writer（研究基础、工作条件）→ nsfc-abstract（摘要）。用户只要部分章节时，只列相关的 skill。
2. 宣布唯一任务目录 `T = ./.bensz-api/task-{yyyymmdd-hhmm}-{简短描述}/`，之后不更换。建立 `T/README.md`、`T/shared/` 和 `T/nsfc-proposal/{input,output,log}/`。
3. 此后每完成一步，在 `T/nsfc-proposal/log/stages.md` 追加一行：时间、步骤、AI 做了什么、产出文件、申请人是否确认。第 8 步据此起草 AI 使用说明。

**1. 材料与项目画像**

```bash
python3 S/scripts/case.py init --project-root P --title "<题目>" --type "<项目类型>" [--sections 立项依据,研究内容]
```

把命令输出中的 ⚠️ 提示转告用户，例如模板没有引用 AI 使用说明文件。

**2. 科学论证**

按 `references/scientific_case_guide.md` 填写 `P/proposal/scientific_case.yaml`。论证用到的每条论断同时写入 `P/proposal/evidence_map.yaml`，`support` 记为 `unsupported`，`evidence` 留空。然后运行：

```bash
python3 S/scripts/case.py validate --project-root P
```

不通过就改，直到通过。

**3. 文献与证据**

1. 生成 5–25 条英文关键词检索式，写入 `T/nsfc-proposal/input/keyword_queries.json`（格式 `{"queries": [...]}`），并抄入 `P/proposal/literature_leads.md` 的「## 检索式」。
2. 对每条 `gap`、`mechanism` 类论断写一个英文问句，写入 `T/nsfc-proposal/input/claim_queries_1.json`；超过 25 条时拆成 `claim_queries_2.json` 等。
3. `config.yaml` 中 `literature.use_wispaper` 为 true，且宿主有 `mcp__wis-scholar-search__quick_search` 工具时：
   - 每条关键词检索式调用 `quick_search`，`top_n` 取 `literature.quick_search_top_n`；
   - 每个论断问句调用 `deep_search`，`top_n` 取 `literature.deep_search_top_n`；
   - 把原始返回逐字存成 `rls.host_results.v1` 文件：`T/nsfc-proposal/output/wispaper/keyword_host.json`、`claims_host_1.json` 等。格式见 `SK/research-literature-search/SKILL.md`。不得改写论文字段。
4. 建检索 bundle 并校验：

```bash
python3 SK/research-literature-search/scripts/search_runner.py run --topic "<题目>" \
  --query-file T/nsfc-proposal/input/keyword_queries.json \
  --output-dir T/research-literature-search/output/keyword-bundle \
  --max-results-per-query 20 --host-results T/nsfc-proposal/output/wispaper/keyword_host.json
python3 SK/research-literature-search/scripts/search_runner.py run --topic "<题目>" \
  --query-file T/nsfc-proposal/input/claim_queries_1.json --min-queries 1 \
  --output-dir T/research-literature-search/output/claims-bundle-1 \
  --max-results-per-query 10 --no-fallback --host-results T/nsfc-proposal/output/wispaper/claims_host_1.json
python3 SK/research-literature-search/scripts/search_runner.py validate --bundle <每个 bundle 目录>
```

   没有 wispaper 时去掉 `--host-results`；论断 bundle 同时去掉 `--no-fallback`。
5. 逐条论断从各 bundle 的 `candidates_deduped.jsonl` 中挑候选证据，原样写入 `T/nsfc-proposal/output/selected.jsonl`，再补全摘要：

```bash
python3 SK/research-literature-search/scripts/search_runner.py enrich-abstracts \
  --input T/nsfc-proposal/output/selected.jsonl --output T/nsfc-proposal/output/selected_enriched.jsonl
```

6. 核对元数据并写入 `.bib`：

```bash
python3 S/scripts/bib_resolve.py --project-root P --records T/nsfc-proposal/output/selected_enriched.jsonl --task-root T
```

   只使用输出中 `added` 或 `exists` 条目的 bibkey。`unresolved` 条目已写入线索清单，正文不得引用。
7. 阅读完整摘要，按 `references/evidence_wording.md` 填写每条论断的 `evidence` 与 `support`，再运行 `case.py validate` 直到通过。

完全离线时跳过 3–6：文献类论断保持 `unsupported`，并在 `assumptions.md` 的「## 待核实项」写明「本次未检索文献」。

**4. 章节分配**

按 `references/section_boundaries.md` 填写 `P/proposal/section_plan.yaml` 各文件的 `must_include`、`must_exclude` 和 `placeholders`。`scientific_case.yaml` 中 `source: missing` 的可行性条目，逐条写进研究基础的 `placeholders`。然后：

```bash
python3 S/scripts/case.py validate --project-root P
python3 S/scripts/case.py render --project-root P
```

**5. 确认点**

按 `references/confirm_prompt.md` 展示 `P/proposal/scientific_case.md` 的要点，然后停下，等申请人回答：

| 回答 | 动作 |
|---|---|
| 同意 | `python3 S/scripts/case.py status --project-root P --set confirmed` |
| 修改：…… | 修改 YAML → `case.py bump` → `case.py validate` → 重新展示 |
| 先继续 | `python3 S/scripts/case.py status --project-root P --set bypassed` |

`confirm.mode` 为 `auto`，或用户要求「全自动」「无人值守」时，不停下，直接执行 `--set bypassed`。

**6. 分章写作**（顺序固定）

每一章都遵守四条：措辞不超过 `evidence_map.yaml` 中对应论断的 `support`；不写 `must_exclude` 中的内容；缺失的信息写成可见占位 `【待补充：……】`，并逐条列入 `assumptions.md` 的「## 占位清单」（格式：`- 文件：【待补充：……】`）；正文不出现内部编号。

1. 立项依据：

   ```bash
   python3 S/scripts/case.py to-info-form --project-root P --writer nsfc-justification-writer --out T/nsfc-proposal/output/info_form_justification.md
   ```

   按 `SK/nsfc-justification-writer/SKILL.md` 执行。它的每条 CLI 命令都加 `--task-root T`，`coach` 加 `--info-form T/nsfc-proposal/output/info_form_justification.md`。写入后运行 `python3 S/scripts/case.py mark-written --project-root P --file extraTex/1.1.立项依据.tex`。
2. 研究内容、特色与创新、年度研究计划：用 `--writer nsfc-research-content-writer` 生成信息表，按 `SK/nsfc-research-content-writer/SKILL.md` 执行。写完运行 `python3 SK/nsfc-research-content-writer/scripts/run_checks.py --project-root P`，三个文件逐一 `mark-written`。
3. 研究基础、工作条件：用 `--writer nsfc-research-foundation-writer` 生成信息表，按 `SK/nsfc-research-foundation-writer/SKILL.md` 执行，两个文件逐一 `mark-written`。
4. 摘要：按 `SK/nsfc-abstract/SKILL.md` 在 `P` 下写 `NSFC-ABSTRACTS.md`，科学问题与术语以科学论证为准，然后 `mark-written --file NSFC-ABSTRACTS.md`。

**7. 跨章一致性检查**

```bash
python3 S/scripts/consistency_check.py --project-root P
```

- 「必须修正」：回到对应的写作 skill 修改，再查；最多 `consistency.max_fix_rounds` 轮。仍不通过的写进收尾报告。
- 「需要复核」：逐条判断。确属内部编号的改成自然语言；属于误报的（如「T1 加权」）在 `T/nsfc-proposal/log/stages.md` 记下理由。
- 语义检查由 AI 完成：各章的科学问题与假设表述一致；研究内容的任务与科学问题一一对应；研究基础覆盖每个任务的可行性。

**8. 收尾**

1. 起草 AI 使用说明，写入 `section_plan.yaml` 中 writer 为 `nsfc-proposal` 的文件（`extraTex/4.5.生成式人工智能.tex` 或 `proposal/ai_declaration.md`）。只写 `stages.md` 里记录过的使用。第一行写 `【待补充：申请人核对本声明后删除此行】`，并列入占位清单。
2. 再运行一次 `consistency_check.py`。
3. 按「输出」一节的格式向用户报告。
4. 用户要求时，调用 nsfc-reviewers 或 nsfc-qc。

### 输出

- `P/proposal/`：`scientific_case.yaml`、`scientific_case.md`、`evidence_map.yaml`、`section_plan.yaml`、`assumptions.md`、`literature_leads.md`；模板没有引用 AI 使用说明文件时，还有 `ai_declaration.md`。
- `P/extraTex/` 下的各章正文，以及 `P/NSFC-ABSTRACTS.md`。
- `main.tex` 指向的 `.bib` 中新增的已核实条目。

每轮回复用这个格式：

```text
当前进度：……
我刚完成：……
下一步：……
需要你确认：……（没有就写「无」）
```

最终报告还要列出：写入的文件、占位清单、待核实项、未解决的一致性问题、建议的下一步（编译、nsfc-length-aligner、nsfc-reviewers、nsfc-qc）。

### 输出管理

- 正式交付物写在 `P` 中。过程文件只写在 `T` 中：wispaper 原始返回、检索 bundle、信息表、`.bib` 备份、`bib_resolve.json`、运行日志。
- `T` 中不保存密钥、令牌和个人身份信息；HTTP 请求不附带个人邮箱。
- 不修改 `main.tex`、`extraTex/@config.tex` 和任何 `.cls`、`.sty`；`.bib` 只追加。

### 校验

- 进入第 5 步前：`case.py validate` 通过。
- 写作期间：各写作 skill 自带的检查通过（立项依据的 Tier2、研究内容的 `run_checks.py`、摘要的 `validate_abstract.py`）。
- 收尾前：`consistency_check.py` 的「必须修正」为 0，或剩余问题已写入报告。
- 篇幅：`python3 SK/nsfc-length-aligner/scripts/check_length.py --input P`。
- 项目有编译脚本时运行它（如 `python3 P/scripts/nsfc_build.py build --project-dir P`），确认 PDF 生成。

### 失败与恢复

| 情况 | 处理 |
|---|---|
| `case.py validate` 不通过 | 不进入写作；按提示修改后重试 |
| wispaper 不可用 | 不传 `--host-results`，改用 research-literature-search 的现有检索源 |
| CrossRef 与 OpenAlex 都不可达 | 不新增 `.bib` 条目；相关论断记为 `unsupported` |
| 某个写作 skill 失败 | 保留已写章节；从 `section_plan.yaml` 中 `written_with_case_version` 为空或低于当前版本的章节继续 |
| 写完后科学论证又被修改 | `case.py bump` 后，一致性检查会列出依据旧版的章节，逐章重写 |
| 一致性检查 2 轮后仍不通过 | 停止重试，问题列入报告 |
| 编译失败 | 报告错误位置；不改动结构命令 |
| `.bib` 写入出错 | 用 `T/nsfc-proposal/output/bib_backup/` 中的备份恢复 |

## 约束

### 公共硬约束

- 任务需要落盘时，使用唯一的 `./.bensz-api/task-{yyyymmdd-hhmm}-{简短描述}/` 根目录；共享材料放入 `shared/`，Skill 专属材料放入该 Skill 的 `input/`、`output/`、`log/`。
- 正式交付物、源代码和正式计划按项目约定保存，不写入任务工作区；未经授权不覆盖、删除、迁移或远程写入。
- 项目维护变更检查 BAC 可用性并记录需求、AI 产出、工具结果、文件改动和验证摘要；BAC 只做过程审计，不替代署名、责任或合规判断。
- 不记录 API Key、访问令牌、密码、Cookie、环境/凭据文件、私有 Prompt、身份信息、本地用户名、主机名或不必要的大体积原始数据。
- 文件路径必须规范化并限制在授权项目范围内；外部 URL、子进程和网络访问遵循最小权限，防止路径遍历、SSRF 和命令注入。
- Skill 版本唯一记录在自身 `config.yaml:skill_info.version`；公开 API、协议、目录或配置变更同步文档与 `CHANGELOG.md`。
- 仅将 Skill 或 Bensz 基础设施本身的设计缺陷交给 `bensz-collect-bugs`；先脱敏写入 `~/.bensz-skills/bugs/`，当前任务不中断，只有用户明确要求才公开上报，禁止直接修改用户已安装的 Skill 源码。
<!-- End of canonical common constraints. -->

### Skill 专属约束

- 不编造文献、数据、病例数、前期成果和合作单位；申请人没提供的内容只写占位。
- 文献的作者、期刊、年份、卷期页码只取自 CrossRef 或 OpenAlex 的返回，不凭记忆填写。
- 全流程只有一个确认点；其余步骤不打断用户。
- 不调用 research-idea。需要系统探索选题时，建议用户先运行它，再把结论写进 `scientific_case.yaml`。
````

- [ ] **Step 4: 新建四份参考文档**

`references/scientific_case_guide.md`：

```markdown
# 建立科学论证

科学论证是各章共同的出发点。先把它写对，再动笔写正文。科学问题与假设的写法以 `../nsfc-justification-writer/references/scientific_question_guidelines.md` 和 `scientific_hypothesis_guidelines.md` 为准，本文不重复。

## 步骤

1. **重要性**：写清问题为什么值得做，填 `importance`。每条挂上论断编号（如 `C1`），论断同时写进 `evidence_map.yaml`。
2. **缺口**：写清已有研究缺什么，填 `gaps`（`G1`、`G2`…）。缺口要具体到「哪类研究、在什么条件下、没有回答什么」。
3. **科学问题**：先写 2–3 个候选，从国自然契合度、可行性、创新性、风险四方面比较，选定后填 `questions`；落选的候选和理由写进 `assumptions.md` 的「## AI 拟定项」。每个问题用疑问句，并在 `answers_gaps` 中写明回应哪些缺口。
4. **假设**：写一个可证伪的陈述句，填 `hypothesis`。`falsification.condition` 写「什么结果出现时假设不成立」，`metric` 写判定所用的指标。否定条件要考虑检验力：要求「每个分层都显著」通常过严，宜写成交互检验或方向一致。
5. **研究对象**：分别写研究对象、目标人群、样本来源。样本来源与目标人群不同时（例如目标是筛查发现的结节，样本却是手术病例），在 `sample_vs_target_gap` 写明差异，在 `bias_handling` 写明怎么处理或讨论。
6. **术语**：标题中的每个专业术语都在 `terms` 中界定。申请人没给定义的，标 `source: ai_proposed`。
7. **研究任务**：每个任务对应一个科学问题。`baselines` 至少列一个最简单的对照，例如只用临床或形态学指标的模型；`confounders` 列出必须控制的混杂。
8. **可行性**：只录申请人提供的材料，标 `source: user_material`；没有的标 `source: missing`，正文会留占位。
9. **AI 拟定的内容**：申请人没提供而由你补上的（研究设计、合作单位、样本来源等），一律标 `source: ai_proposed`，并写进 `assumptions.md` 的「## AI 拟定项」。

## 字段速查

| 字段 | 含义 |
|---|---|
| `research_object` | 研究对象、目标人群、样本来源、两者差异、偏倚处理 |
| `terms` | 术语与定义 |
| `importance` / `gaps` | 重要性与缺口，各挂论断编号 |
| `mainstream_routes` | 主流路线及其局限，挂论断编号 |
| `questions` | 科学问题（疑问句），回应的缺口 |
| `hypothesis` | 假设、依据、推论、否定条件与判定指标 |
| `entry_point` | 与最近工作的差别 |
| `aim` / `tasks` | 总体目标；任务的指标、必比基线、混杂、验证、子任务、依赖 |
| `constraints` | 资源、伦理、年度硬约束 |
| `feasibility` | 前期基础，逐条标来源 |
| `risks` | 风险与应对，按技术、进度、资源分类 |

## 不要做

- 不为显得重要而拔高。
- 不把工程任务包装成科学问题。
- 不把缺证据的判断写成事实。
- 不把研究方案的细节写进科学论证；方法细节属于研究内容。
```

`references/evidence_wording.md`：

```markdown
# 证据与措辞强度

## 怎样判断一条证据

- 只读完整摘要或全文。只有摘要片段（以「…」开头或结尾）的论文，不能作为支持证据。
- 每条证据写明 `role`：支持（supporting）还是反驳（counter）。找到反驳证据时照实记录，不要删掉。
- `basis` 写判断依据：`fulltext`（全文）或 `full_abstract`（完整摘要）。
- `ref` 写 bibkey；只有线索、没有进入 `.bib` 的，写 `lead:L<编号>`，它不计入已核实证据。

## 支持程度与正文写法

| support | 条件 | 正文写法 |
|---|---|---|
| `multi_verified` | 至少 2 条支持证据，`ref` 为 bibkey，`basis` 为全文或完整摘要 | 可写「多项研究表明」 |
| `single_verified` | 恰好 1 条这样的证据 | 只写「有研究报道」，不写成共识 |
| `unsupported` | 没有已核实证据 | 不写成事实；改为推测（「可能」「尚不清楚」），或删去 |
| `applicant_material` | 申请人提供的材料（只用于 `applicant_result` 类论断） | 按材料原样写，不夸大 |

`case.py validate` 会检查 `support` 是否超出证据实际能支撑的程度。

## 例句

- multi_verified：多项研究表明，瘤周区域特征可提供瘤内特征之外的信息\cite{a,b}。
- single_verified：有研究报道，重建核改变后部分纹理特征的重复性下降\cite{c}。
- unsupported：这一对应关系在不同扫描参数下是否稳定，目前尚不清楚。
- 缺材料：本课题组已完成预实验【待补充：预实验的样本量与主要结果】。
```

`references/section_boundaries.md`：

```markdown
# 各章写什么、不写什么

`config.yaml` 的 `sections[].must_exclude` 是机器可读的默认值，`case.py init` 把它写进 `section_plan.yaml`。本文解释这些边界，供填写 `must_include` 和补充 `must_exclude` 时参考。

| 章节 | 必写 | 不写 |
|---|---|---|
| 立项依据 | 重要性、缺口、科学问题、假设与否定条件、切入点、术语界定、研究对象与目标人群的差异 | 实验步骤、技术路线、样本量设计、年度安排等研究方案细节 |
| 研究内容 | 总体目标、各研究任务（指标、必比基线、混杂控制、验证方式）、技术路线 | 展开的国内外研究现状 |
| 特色与创新 | 1–3 条创新，各说明与主流路线的差别 | 「首次」「国际领先」「填补空白」等无依据的绝对化说法 |
| 年度研究计划 | 三年任务与里程碑，逐年对应研究任务 | 研究背景 |
| 研究基础 | 申请人提供的论文、数据、平台、预实验；缺失项的占位 | 申请人没有提供的论文、数据或预实验结果 |
| 工作条件 | 申请人提供的平台与设备 | 申请人没有提供的平台或设备 |
| 摘要 | 科学问题、假设、主要内容、预期意义，术语与科学论证一致 | 内部编号 |
| AI 使用说明 | 运行日志中记录过的 AI 使用 | 日志中没有记录的使用 |

立项依据写到假设与切入点为止。「怎么做」放进研究内容，立项依据只用一句话衔接。
```

`references/confirm_prompt.md`：

````markdown
# 确认点

全流程只在这里停一次。展示内容取自 `proposal/scientific_case.md`，用申请人能直接判断的语言，不出现内部编号和 YAML 字段名。

## 展示格式

```text
当前进度：科学论证已完成（第 N 版）
我刚完成：……（检索了多少文献、核实了多少条、各章怎么分工）

请确认以下内容：
1. 科学问题：……
2. 科学假设：……（否定条件：……；判定指标：……）
3. 术语界定：……
4. 研究对象：……（样本与目标人群的差异：……；处理方式：……）
5. 各章分工：立项依据写……；研究内容写……；研究基础写……
6. 我替你拟定、需要你确认的内容：……

你可以回答：同意 / 修改：（写明要改什么）/ 先继续
```

## 处理回答

- 同意：`case.py status --set confirmed`，进入写作。
- 修改：改 YAML，`case.py bump`，`case.py validate`，重新展示。可以多次修改。
- 先继续：`case.py status --set bypassed`，进入写作；收尾报告中再次列出未确认的内容。
- 无人值守（`confirm.mode: auto`，或用户要求全自动）：不展示、不停，按「先继续」处理。
````

- [ ] **Step 5: 新建 `README.md` 与 `CHANGELOG.md`**

`README.md`：

````markdown
# nsfc-proposal — 用户使用指南

## 它做什么

帮你写国家自然科学基金申请书的正文。它先和你确定科学问题与假设，再按立项依据、研究内容、研究基础、摘要的顺序成稿。各章用同一套问题、假设和术语；引用的文献都经过检索和元数据核对。

## 怎么用

在 Claude Code 或 Codex 中说：

```text
用 nsfc-proposal 帮我写国自然青年基金正文。
项目目录：projects/我的项目
题目：……
研究对象：……
痛点：……
科学问题与假设的初步想法：……
已有材料：论文 / 预实验 / 没有
```

想全程不被打断，加一句「全自动，不用停下来问我」。

## 你会得到什么

- 各章正文，写进项目的 `extraTex/`；摘要写进 `NSFC-ABSTRACTS.md`。
- `proposal/` 目录：科学论证、证据图谱、章节分工、待核实清单、文献线索。正文里缺的内容都写成 `【待补充：……】`，并列在 `proposal/assumptions.md` 里。
- 核对过的参考文献，追加到项目的 `.bib`。查不到的只进线索清单，正文不引用。

## 流程中你需要做什么

只有一次：科学论证写好后，它会请你确认科学问题、假设、术语和各章分工。你可以回答「同意」「修改：……」或「先继续」。

## 写完之后

1. 逐条处理 `proposal/assumptions.md` 里的占位和待核实项。
2. 编译 PDF，检查篇幅（nsfc-length-aligner）。
3. 需要时用 nsfc-reviewers 模拟评审，用 nsfc-qc 质检。

## 注意

- 它不会编造文献、数据或前期成果。你没提供的，它只留占位。
- 它不改 `main.tex` 和模板样式文件。
- 生成式人工智能使用说明是草稿，提交前请你核对。
````

`CHANGELOG.md`：

```markdown
# Changelog

All notable changes to this skill will be documented in this file.

The version number is the single source of truth in `config.yaml` (`skill_info.version`).

## [0.1.0] - 2026-10-09

### Added（新增）

- 初始化技能，实现核心功能：建立科学论证、证据图谱与章节分工；wispaper 检索与 CrossRef/OpenAlex 元数据核对；一个可跳过的确认点；按固定顺序调用 nsfc-* 写作 skill；跨章一致性检查；生成式人工智能使用说明草稿。
- 本分支未写 BAC 记录，经负责人同意。
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/`
Expected: 全部通过，0 failed。

- [ ] **Step 7: 提交**

```bash
git add skills/nsfc-proposal/SKILL.md skills/nsfc-proposal/references skills/nsfc-proposal/README.md skills/nsfc-proposal/CHANGELOG.md tests/nsfc-proposal/test_np_skill_docs.py
git commit -m "docs(nsfc-proposal): 新增 SKILL.md、参考文档、README 与 CHANGELOG

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: 写作 skill 与检索 skill 接入说明、版本与变更记录

**Files:**
- Modify: `skills/nsfc-justification-writer/SKILL.md`、`references/tier2_semantic_review.md`、`README.md:169-178`、`config.yaml`、`CHANGELOG.md`
- Modify: `skills/nsfc-research-content-writer/SKILL.md`、`README.md:27`、`config.yaml`、`CHANGELOG.md`
- Modify: `skills/nsfc-research-foundation-writer/SKILL.md`、`config.yaml`、`CHANGELOG.md`
- Modify: `skills/nsfc-abstract/SKILL.md`、`config.yaml`、`CHANGELOG.md`
- Modify: `skills/research-literature-search/SKILL.md`、`README.md`、`config.yaml`、`CHANGELOG.md`
- Test: `tests/nsfc-proposal/test_np_writer_integration.py`

**Interfaces:**
- Consumes: Task 1–5 的代码改动；Task 12 的 `SKILL.md`。
- Produces: 各 skill 在 `proposal/` 存在时的行为契约。

- [ ] **Step 1: 写失败测试**

```python
# tests/nsfc-proposal/test_np_writer_integration.py
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

SKILLS = Path(__file__).resolve().parents[2] / "skills"
VERSIONS = {
    "nsfc-justification-writer": "1.4.0",
    "nsfc-research-content-writer": "1.1.0",
    "nsfc-research-foundation-writer": "0.2.0",
    "nsfc-abstract": "2.1.3",
    "research-literature-search": "1.1.0",
}


def read(rel: str) -> str:
    return (SKILLS / rel).read_text(encoding="utf-8")


class IntegrationDocsTest(unittest.TestCase):
    def test_versions_and_changelogs(self) -> None:
        for skill, version in VERSIONS.items():
            config = yaml.safe_load(read(f"{skill}/config.yaml"))
            self.assertEqual(str(config["skill_info"]["version"]), version, skill)
            changelog = read(f"{skill}/CHANGELOG.md")
            self.assertIn(f"## [{version}] - 2026-10-09", changelog, skill)
            self.assertIn("本分支未写 BAC 记录，经负责人同意。", changelog, skill)

    def test_writers_describe_proposal_mode(self) -> None:
        for skill in ("nsfc-justification-writer", "nsfc-research-content-writer", "nsfc-research-foundation-writer", "nsfc-abstract"):
            text = read(f"{skill}/SKILL.md")
            self.assertIn("proposal/", text, skill)
            self.assertIn("没有 `proposal/` 时", text, skill)

    def test_justification_tier2_checks(self) -> None:
        text = read("nsfc-justification-writer/references/tier2_semantic_review.md")
        self.assertIn("## 与 nsfc-proposal 协作时的追加检查", text)
        self.assertIn("evidence_map.yaml", text)
        self.assertIn("must_exclude", text)
        self.assertIn("--task-root", read("nsfc-justification-writer/SKILL.md"))
        self.assertIn("--task-root", read("nsfc-justification-writer/README.md"))

    def test_foundation_requires_visible_placeholders(self) -> None:
        self.assertIn("【待补充：", read("nsfc-research-foundation-writer/SKILL.md"))

    def test_content_readme_no_longer_asks_for_subgoal_ids_in_body(self) -> None:
        self.assertNotIn("2.2/2.3 标注回溯到对应 Sx", read("nsfc-research-content-writer/README.md"))

    def test_search_documents_host_results(self) -> None:
        for rel in ("research-literature-search/SKILL.md", "research-literature-search/README.md"):
            self.assertIn("--host-results", read(rel), rel)
            self.assertIn("rls.host_results.v1", read(rel), rel)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_writer_integration.py`
Expected: FAIL（版本号与文档均未更新）。

- [ ] **Step 3: nsfc-justification-writer**

3a. `SKILL.md`：在「### 输入」下那一行（`按用户请求和配置文件提供必要输入；缺失信息应明确列出并停止依赖该输入的步骤。`）之后插入：

```markdown

由 nsfc-proposal 调用、且 `{project_root}/proposal/` 存在时：

- 信息表由 nsfc-proposal 生成，经 `coach --info-form <文件>` 传入，不再自行提取。
- 篇幅取 `proposal/section_plan.yaml` 中本章的 `length`，不用 `config.yaml` 的 `word_count.target`。
- Tier2 自审按 `references/tier2_semantic_review.md` 中「与 nsfc-proposal 协作时的追加检查」执行。
- 每条 CLI 命令都加 `--task-root <任务目录>`，同一任务的 `preview`、`diff`、`rollback` 写入同一目录。
- 缺失的信息写成可见占位 `【待补充：……】`，不写成 LaTeX 注释。

没有 `proposal/` 时，行为与此前相同。
```

3b. `references/tier2_semantic_review.md` 末尾追加：

```markdown

## 与 nsfc-proposal 协作时的追加检查

`{project_root}/proposal/` 存在时，Tier2 再加两项，结论归入「事实问题」：

1. **措辞强度**：涉及文献或事实的论断，逐句找到 `proposal/evidence_map.yaml` 中对应的论断，措辞不得超过其 `support` 允许的强度：`multi_verified` 可写「多项研究表明」；`single_verified` 只写「有研究报道」；`unsupported` 不写成事实；`applicant_material` 按材料原样写。
2. **章节边界**：正文不得出现 `proposal/section_plan.yaml` 中本章 `must_exclude` 列出的内容。越界段落移出本章，并在报告中写明应放到哪一章。
```

3c. `README.md` 的「## 写入后的版本管理」代码块之后追加：

```markdown

多条命令属于同一任务时，加顶层参数 `--task-root .bensz-api/task-<时间>-<描述>/`，备份与日志写入同一目录。不加时，`diff`、`rollback` 和 `list-runs` 会在 `.bensz-api/task-*/nsfc-justification-writer/` 下按 run_id 查找。
```

3d. `config.yaml`：`skill_info.version` 由 `1.3.0` 改为 `1.4.0`。

3e. `CHANGELOG.md`：在第一个已有版本标题（`## [1.0.0] - 2026-02-24`）之前插入：

```markdown
## [1.4.0] - 2026-10-09

### Fixed（修复）
- 提案可新增模板使用的标题命令（`guardrails.allowed_new_heading_commands`，默认 `subsubsection`）；删改已有标题仍被拒绝。
- `list-runs` 不再把任务工作区的 `input/output/log/cache` 当作运行记录。
- 新增顶层参数 `--task-root`；`diff`、`rollback`、`list-runs` 未指定时跨任务目录按 run_id 查找，修复跨分钟找不到前一步的问题。

### Added（新增）
- 与 nsfc-proposal 协作：读取 `proposal/` 下的信息表、篇幅与章节边界；Tier2 追加措辞强度与章节边界两项检查。
- 本分支未写 BAC 记录，经负责人同意。

```

- [ ] **Step 4: nsfc-research-content-writer**

4a. `SKILL.md`：在「### 输入」下那一行之后插入：

```markdown

由 nsfc-proposal 调用、且 `{project_root}/proposal/` 存在时：

- 信息表由 nsfc-proposal 生成并给出文件路径。子目标直接取自其中的研究任务：指标对应「指标」，对照对应「对照/基线」与「需控制的混杂」，验证对应「验证」。
- 「特色与创新」取自信息表的「创新对照坐标系」，即主流路线与本项目切入点。
- 篇幅和不写的内容以 `proposal/section_plan.yaml` 为准；措辞强度不超过 `proposal/evidence_map.yaml`。
- 缺失的信息写成可见占位 `【待补充：……】`。

没有 `proposal/` 时，行为与此前相同。
```

4b. `README.md` 第 27 行：

```text
额外要求：子目标编号 S1–S4；每个子目标必须写清 指标+对照+数据来源；2.2/2.3 标注回溯到对应 Sx
```

改为：

```text
额外要求：内部规划时子目标编号 S1–S4（编号不写入正文）；每个子目标必须写清 指标+对照+数据来源；2.2/2.3 用自然语言回溯对应的子目标
```

4c. `config.yaml`：`skill_info.version` 由 `1.0.0` 改为 `1.1.0`。

4d. `CHANGELOG.md`：在 `## [1.0.0] - 2026-02-24` 之前插入：

```markdown
## [1.1.0] - 2026-10-09

### Fixed（修复）
- `check_project_outputs.py` 原先要求正文至少出现 3 个 S 编号，与 SKILL.md「编号不得进入正文」矛盾；改为检查编号泄漏，删除 `checks.subgoal_markers_min`。README 示例 Prompt 同步修正。

### Added（新增）
- 与 nsfc-proposal 协作：子目标取自科学论证的研究任务，篇幅与章节边界取自 `proposal/section_plan.yaml`。
- 本分支未写 BAC 记录，经负责人同意。

```

- [ ] **Step 5: nsfc-research-foundation-writer**

5a. `SKILL.md`：在「### 输入」下那一行之后插入：

```markdown

由 nsfc-proposal 调用、且 `{project_root}/proposal/` 存在时：

- 信息表由 nsfc-proposal 生成并给出文件路径；前期基础、团队、条件与风险都取自其中。
- 信息表标为「缺失」的条目，在正文对应位置写成可见占位，例如 `【待补充：预实验的样本量与主要结果】`，不得略去，也不得编造。
- 研究基础要逐条覆盖信息表「研究任务」中每个任务的可行性。
- 篇幅和不写的内容以 `proposal/section_plan.yaml` 为准。

没有 `proposal/` 时，行为与此前相同。
```

5b. `config.yaml`：`skill_info.version` 由 `0.1.2` 改为 `0.2.0`。

5c. `CHANGELOG.md`：在 `## [0.1.2] - 2026-04-24` 之前插入：

```markdown
## [0.2.0] - 2026-10-09

### Added（新增）
- 与 nsfc-proposal 协作：从科学论证生成的信息表取材；缺失的前期基础写成可见占位，不再略去。
- 本分支未写 BAC 记录，经负责人同意。

```

- [ ] **Step 6: nsfc-abstract**

6a. `SKILL.md`：在「## 流程」下「### 输入」那一行之后插入：

```markdown

由 nsfc-proposal 调用、且 `{project_root}/proposal/` 存在时：信息取自 `proposal/scientific_case.yaml` 和已写成的各章，不再向用户提问；科学问题、假设与术语的表述以科学论证为准；正文不出现内部编号。

没有 `proposal/` 时，行为与此前相同。
```

6b. `config.yaml`：`skill_info.version` 由 `2.1.2` 改为 `2.1.3`。

6c. `CHANGELOG.md`：在 `## [2.1.2] - 2026-03-04` 之前插入：

```markdown
## [2.1.3] - 2026-10-09

### Changed（变更）
- 与 nsfc-proposal 协作时，信息取自科学论证与已写章节，不再向用户提问。
- 本分支未写 BAC 记录，经负责人同意。

```

- [ ] **Step 7: research-literature-search**

7a. `SKILL.md`：把「### 输入」中这一行

```markdown
- 可选：`domain`、年份/文献类型/预印本过滤、provider 顺序、每查询/总量上限、`scope_root`。
```

改为：

```markdown
- 可选：`domain`、年份/文献类型/预印本过滤、provider 顺序、每查询/总量上限、`scope_root`、`--host-results`。
- `--host-results`：宿主经 MCP（当前支持 wispaper）取得的结果，格式为 `rls.host_results.v1`：`{"schema": "rls.host_results.v1", "provider": "wispaper", "queries": [{"query": "<与查询文件中原文一致>", "tool": "quick_search", "papers": [<wispaper 原始返回的论文对象>]}]}`。它填入 `mcp` 检索源位置；结果不足时按补充规则继续用 OpenAlex 等。摘要片段（以「…」开头或结尾）不当作摘要，原文存入 `provenance.host_abstract_snippet`；DOI 为空时从出版社链接中提取。
```

并把这一句

```markdown
`mcp`/`duckduckgo` 在纯 Python runner 中记为 `skipped/host tool required`。
```

改为：

```markdown
未传 `--host-results` 时，`mcp`/`duckduckgo` 在纯 Python runner 中记为 `skipped/host tool required`；传入后，有结果的查询把 `mcp` 记为 `success` 并标注 `host_tool`。
```

7b. `README.md`：在「可用 `--provider-order ...` 设置过滤条件；...」那一段之后追加：

```markdown

已经通过 MCP 拿到 wispaper 结果时，按 `rls.host_results.v1` 格式保存，再用 `--host-results <文件>` 传入，结果会填进 `mcp` 检索源位置。格式见 SKILL.md「输入」一节。
```

7c. `config.yaml`：`skill_info.version` 由 `1.0.4` 改为 `1.1.0`（只改 `skill_info` 下的 `version`，不动 `rls.v1` 那一行）。

7d. `CHANGELOG.md`：在 `## [1.0.4] - 2026-09-15` 之前插入：

```markdown
## [1.1.0] - 2026-10-09

### Added（新增）
- `run` 新增 `--host-results`，接收宿主经 MCP 取得的 wispaper 结果（`rls.host_results.v1`），填入 `mcp` 检索源位置；从出版社链接提取 DOI；摘要片段不当作摘要。不传该参数时行为不变。
- 本分支未写 BAC 记录，经负责人同意。

```

- [ ] **Step 8: 运行测试与各 skill 自检**

```bash
PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/research-literature-search
PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 skills/nsfc-justification-writer/scripts/run.py --no-user-override validate-config
PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 skills/nsfc-research-content-writer/scripts/validate_skill.py
PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 skills/nsfc-research-foundation-writer/scripts/validate_skill.py
```

Expected: pytest 0 failed；`validate-config` 退出码 0。后两条在 `main` 上本来就失败（content-writer 要求 `plans/` 目录；foundation-writer 要求 frontmatter 含 `version` 等字段，与「版本只写在 config.yaml」冲突），输出须与改动前相同，不在本次修复范围。

- [ ] **Step 9: 提交**

```bash
git add skills/nsfc-justification-writer skills/nsfc-research-content-writer skills/nsfc-research-foundation-writer skills/nsfc-abstract skills/research-literature-search tests/nsfc-proposal/test_np_writer_integration.py
git commit -m "docs(nsfc): 写作与检索 skill 接入 nsfc-proposal，更新版本与变更记录

nsfc-justification-writer 1.4.0、nsfc-research-content-writer 1.1.0、
nsfc-research-foundation-writer 0.2.0、nsfc-abstract 2.1.3、
research-literature-search 1.1.0。没有 proposal/ 时各 skill 行为不变。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: 仓库文档、根 CHANGELOG 与设计文档同步

**Files:**
- Modify: `skills/README.md`（推荐工作流与技能列表）
- Modify: `CHANGELOG.md`（根，`[Unreleased]`）
- Modify: `docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md`
- Test: 无新测试；运行全部相关测试

**Interfaces:**
- Consumes: Task 1–13 的结果。

- [ ] **Step 1: `skills/README.md`**

把「## 推荐工作流」下的 mermaid 图替换为：

```mermaid
graph LR
    A[research-topic-extractor<br>提取综述主题] --> S[research-literature-search<br>候选文献检索]
    S --> B[research-literature-review<br>规范化文献综述]
    B --> C[research-guide-updater<br>优化项目指南]
    C --> P[nsfc-proposal<br>科学论证与分章总控]
    P --> D[nsfc系列写作 skills<br>立项依据 / 研究内容 / 研究基础 / 摘要]
    D --> F[nsfc-reviewers<br>专家评审模拟]
```

在「**第四步：标书各部分写作**」一段的列表之前加一句：

```markdown
- 推荐以 `nsfc-proposal` 为入口：它先建立科学论证、证据图谱与章节分工，再按顺序调用下列写作 skill，并做跨章一致性检查。
```

在「## 当前技能列表」中，仿照相邻 nsfc 条目的格式，新增一节 `nsfc-proposal`，写明：用途（一句话）、推荐 Prompt（照抄 `skills/nsfc-proposal/README.md` 的「怎么用」示例）、产出（`proposal/` 与各章正文）。版本号不写进此文件。

- [ ] **Step 2: 根 `CHANGELOG.md`**

在 `## [Unreleased]` 下、设计文档那一条之后追加：

```markdown
- 新增 `nsfc-proposal` 0.1.0：国自然正文统一入口，建立科学论证、证据图谱与章节分工，接入 wispaper 检索与 CrossRef/OpenAlex 元数据核对，按固定顺序调用写作 skill 并做跨章一致性检查。
- `nsfc-justification-writer` 1.4.0：允许提案新增模板标题命令；`list-runs` 不再列出工作区目录；新增 `--task-root` 并跨任务目录查找运行记录；接入 nsfc-proposal。
- `nsfc-research-content-writer` 1.1.0：检查脚本改为检测 S 编号泄漏（原规则与 SKILL.md 矛盾）；接入 nsfc-proposal。
- `nsfc-research-foundation-writer` 0.2.0、`nsfc-abstract` 2.1.3：接入 nsfc-proposal。
- `research-literature-search` 1.1.0：`run` 新增 `--host-results`，接收 wispaper 结果。
- 本分支未写 BAC 记录，经负责人同意。
```

- [ ] **Step 3: 设计文档同步四处细化**

在设计文档中做如下修改：

1. 6.2 节「`quick_search` 的摘要标为 `abstract_status: snippet`」改为：「`quick_search` 的摘要片段不作为摘要：`abstract` 置空、`abstract_status` 为 `missing`，片段原文存入 `provenance.host_abstract_snippet`，并加 `abstract_snippet_only` 警告；之后由 `enrich-abstracts` 补全。」
2. 6.4 节第 1 步改为：「**取 DOI**：用规范记录中的 DOI。wispaper 记录的 DOI 已由 research-literature-search 在导入时从链接中提取。」
3. 第 8 节标题改为「已知缺陷修复」，表格末尾加一行：「research-content-writer 检查脚本要求正文出现 S 编号 | `check_project_outputs.py` 要求至少 3 个 S 编号，SKILL.md 却禁止编号进入正文 | 改为检查编号泄漏，删除 `subgoal_markers_min`」。
4. 4.8 节第一条之后加：「模板 `main.tex` 没有引用 `extraTex/4.5.生成式人工智能.tex` 时（如 NSFC_Young），改写到 `proposal/ai_declaration.md`，并在 `assumptions.md` 记一条待核实项。」
5. 7.3 节 nsfc-abstract 一行中「版本号不变」改为「版本 2.1.2 → 2.1.3」。

- [ ] **Step 4: 运行全部相关测试**

```bash
PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/research-literature-search tests/research-literature-review tests/research-literature-radar tests/research-idea
git status --short
```

Expected: 除 research-idea 的 4 个既有 errors（未安装 `bensz_skill_kernel`）外 0 failed；`git status` 只列出本任务改动的文件，`tests/` 与 `skills/` 下没有新生成的缓存目录（`__pycache__`、`.pytest_cache`）。

- [ ] **Step 5: 提交**

```bash
git add skills/README.md CHANGELOG.md docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md
git commit -m "docs: 仓库文档与设计文档同步 nsfc-proposal 的实现

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## 阶段四：验收（Task 15–20，仓库外进行）

验收目录 `E = /home/juli/guoziran/nsfc-proposal-eval/`，不进仓库。每次运行用独立目录：

```text
E/<运行名>/
├── projects/proj/      项目副本（prepare_project.py 生成）
├── packages -> /home/juli/guoziran/ChineseResearchLaTeX/packages   软链接，供项目编译脚本找到 bensz-nsfc
└── .bensz-api/         该运行的任务目录（运行时以 E/<运行名> 为当前目录）
```

（项目自带的 `scripts/nsfc_build.py` 在 `项目目录/../../packages` 下找 `bensz-nsfc`，所以用这个布局。）

实验组 skill 路径：`/home/juli/guoziran/ChineseResearchLaTeX/skills/`（`nsfc-proposal` 分支）。对照组 skill 路径：`E/crl-main/skills/`（`main` 分支的 worktree）。

### Task 15: 验收输入、项目副本工具与对照组 worktree

**Files:**
- Create: `E/input_full.md`、`E/input_for_review.md`、`E/prepare_project.py`、`E/README.md`
- Create: `E/crl-main/`（`git worktree`）

- [ ] **Step 1: 写 `E/input_full.md`**

```markdown
# 申请人提供的信息

申请类型：国家自然科学基金青年科学基金项目
希望的协作方式：全自动初稿，过程中不要停下来问我，缺的信息先按保守假设处理并标出来
已有材料：除下面这些文字外，暂时没有论文、草稿或文献清单
本次需要：申请书正文的立项依据、研究内容、特色与创新、年度研究计划、研究基础、工作条件，以及中英文摘要；篇幅按青年基金常规要求

研究方向 / 拟申报题目：基于多模态影像深度学习的肺磨玻璃结节浸润性预测研究

关键词：肺磨玻璃结节；影像组学；深度学习；浸润性预测；外部验证

补充信息：
研究对象/应用场景：低剂量 CT 筛查发现的肺磨玻璃结节（GGN）患者。
痛点与现有不足：术前难以区分浸润前病变与浸润性腺癌，导致过度手术或延误治疗；现有影像组学模型多为单中心数据、外部验证不足、可解释性差。
关键科学问题：GGN 的瘤内与瘤周 CT 纹理异质性是否与病理浸润程度存在可量化的对应关系？这种关系在不同扫描参数下是否稳定？
核心科学假设：融合瘤内与瘤周多尺度特征的深度模型，在外部队列中区分浸润性与浸润前病变的能力优于仅用瘤内特征的模型。
前期基础：无
团队与合作单位：无
平台与设备条件：无
```

`E/input_for_review.md`：与上文相同，但删去「希望的协作方式」和「本次需要」两行（评审不应知道流程和篇幅要求）。

- [ ] **Step 2: 写 `E/prepare_project.py`**

```python
#!/usr/bin/env python3
"""复制 NSFC 模板项目，清空示例正文与示例文献，并建立 packages 软链接（验收用）。"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

BODY_FILES = ["1.1.立项依据.tex", "2.1.研究内容.tex", "2.2.特色与创新.tex", "2.3.年度研究计划.tex", "3.1.研究基础.tex", "3.2.工作条件.tex"]
HEADER = "\\justifying\n\\NSFCBodyText\n\n"
REPO = Path("/home/juli/guoziran/ChineseResearchLaTeX")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path, help="E/<运行名>")
    parser.add_argument("--source", default=REPO / "projects" / "NSFC_Young", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    dest = run_dir / "projects" / "proj"
    if dest.exists():
        raise SystemExit(f"目标已存在：{dest}")
    shutil.copytree(args.source, dest, ignore=shutil.ignore_patterns("main.pdf", ".latex-cache", ".bensz-api"))
    for name in BODY_FILES:
        (dest / "extraTex" / name).write_text(HEADER, encoding="utf-8")
    for bib in (dest / "references").glob("*.bib"):
        bib.write_text("", encoding="utf-8")
    link = run_dir / "packages"
    if not link.exists():
        link.symlink_to(REPO / "packages", target_is_directory=True)
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 确认空白副本能编译**

```bash
cd /home/juli/guoziran/nsfc-proposal-eval
python3 prepare_project.py --run-dir smoke
cd smoke/projects/proj && python3 scripts/nsfc_build.py build --project-dir . ; ls -la main.pdf
```

Expected: 生成 `main.pdf`。若因字体等环境原因失败，把错误摘要写入 `E/README.md` 的「环境」一节，后续所有「编译」检查记为「环境不支持，未执行」，不得记为通过。

- [ ] **Step 4: 建对照组 worktree**

```bash
git -C /home/juli/guoziran/ChineseResearchLaTeX worktree add /home/juli/guoziran/nsfc-proposal-eval/crl-main main
git -C /home/juli/guoziran/nsfc-proposal-eval/crl-main log --oneline -1
```

Expected: 显示 `main` 的最新提交（`3630a8c`）。

- [ ] **Step 5: 写 `E/README.md`**

内容包括：目录用途；实验组与对照组的 skill 路径；各运行目录的用途（`e2e`、`interactive`、`new-1`、`new-2`、`ctl-1`、`ctl-2`）；环境说明（Step 3 结果）。不提交到仓库。

---

### Task 16: 端到端运行（联网，无人值守）与客观检查

**Files:**
- Create: `E/e2e/`（运行产物）、`E/e2e/checks.md`、`E/e2e/citation_spotcheck.md`

- [ ] **Step 1: 准备项目**

```bash
cd /home/juli/guoziran/nsfc-proposal-eval && python3 prepare_project.py --run-dir e2e
touch /home/juli/guoziran/nsfc-proposal-eval/e2e/.start-marker
```

- [ ] **Step 2: 派一个子代理执行 nsfc-proposal**

用 Agent 工具（general-purpose），提示词：

```text
你在执行一次验收运行。工作目录：/home/juli/guoziran/nsfc-proposal-eval/e2e（所有 .bensz-api 任务目录建在这里）。
project_root：/home/juli/guoziran/nsfc-proposal-eval/e2e/projects/proj
skills 根目录：/home/juli/guoziran/ChineseResearchLaTeX/skills
读取并严格按 skills 根目录下 nsfc-proposal/SKILL.md 执行，SKILL.md 中的 S 指 nsfc-proposal 目录，SK 指 skills 根目录。
用户请求如下（原文）：
<粘贴 E/input_full.md 全文>
要求：可以联网；可以使用 wispaper MCP 检索工具；不得修改 /home/juli/guoziran/ChineseResearchLaTeX 下的任何文件；运行任何 python3 命令前先设置 PYTHONPYCACHEPREFIX=/home/juli/guoziran/nsfc-proposal-eval/e2e/.pycache，不要 cd 进 skill 目录。
完成后报告：任务目录路径；写入的文件；确认点的处理方式；bib_resolve 的 counts；consistency_check 的最终输出；遇到的问题与偏离 SKILL.md 之处。
```

- [ ] **Step 3: 运行客观检查，写入 `E/e2e/checks.md`**

```bash
R=/home/juli/guoziran/ChineseResearchLaTeX
P=/home/juli/guoziran/nsfc-proposal-eval/e2e/projects/proj
python3 $R/skills/nsfc-proposal/scripts/consistency_check.py --project-root $P --json > /home/juli/guoziran/nsfc-proposal-eval/e2e/consistency.json; echo "exit=$?"
python3 $R/skills/nsfc-proposal/scripts/case.py validate --project-root $P
python3 $R/skills/nsfc-length-aligner/scripts/check_length.py --input $P --config $R/skills/nsfc-length-aligner/config.yaml --out-dir /home/juli/guoziran/nsfc-proposal-eval/e2e/length
python3 $R/skills/nsfc-ref-alignment/scripts/run_ref_alignment.py --project-root $P --main-tex main.tex --report-dir /home/juli/guoziran/nsfc-proposal-eval/e2e/ref-alignment --prepare
(cd $P && python3 scripts/nsfc_build.py build --project-dir .) && python3 -c "import subprocess;print(subprocess.run(['pdfinfo','$P/main.pdf'],capture_output=True,text=True).stdout)"
git -C $R status --short
```

`checks.md` 用下表记录，每项写「通过 / 不通过 / 未执行」和证据：

| 检查项 | 通过标准 |
|---|---|
| 编译 | 生成 `main.pdf`，`pdfinfo` 页数 ≤ 30 |
| 篇幅 | `check_length.py` 报告各章在预算内 |
| 一致性 | `consistency.json` 的 `errors` 为空；`needs_review` 逐条有处理记录 |
| 内部编号 | 无确属内部编号的残留 |
| 占位 | 全部可见，且都列在 `proposal/assumptions.md` |
| 引用 key | 无 `missing_bibkey`；nsfc-ref-alignment 无缺失 key |
| 仓库未被改动 | `git status --short` 与运行前相同；`find $R/skills -name __pycache__ -newer /home/juli/guoziran/nsfc-proposal-eval/e2e/.start-marker` 无输出 |
| mark-written 覆盖 | `section_plan.yaml` 中每个已写入内容的文件，`written_with_case_version` 都不为空；为空说明子代理没有按 SKILL.md 第 6 步执行，记为不通过 |

- [ ] **Step 4: 引用抽查，写入 `E/e2e/citation_spotcheck.md`**

1. 从任务目录的 `nsfc-proposal/output/bib_resolve.json` 取所有 `added` 条目；用 `random.Random(20261009).sample(...)` 抽 10 条（不足 10 条时全查），记下种子。
2. 每条用 `curl -s https://api.crossref.org/works/<doi>` 取原始记录，与 `.bib` 中的标题、作者、期刊、年份、卷、期、页码逐项比对。
3. 在正文中找到引用该 key 的每一句，对照 `selected_enriched.jsonl` 中该论文的完整摘要，判断句子是否是这篇论文的内容。
4. 逐条记表：bibkey、DOI、元数据是否一致（不一致写明字段）、引用句、摘要是否支持、结论。

通过标准：0 条元数据不一致，0 条引用句与摘要不符。表头注明「由 Claude 抽查，请申请人复核」。

---

### Task 17: 交互模式、修改后失效检测与无 wispaper 降级

**Files:**
- Create: `E/interactive/`、`E/interactive/checks.md`

- [ ] **Step 1: 交互模式停在确认点**

```bash
cd /home/juli/guoziran/nsfc-proposal-eval && python3 prepare_project.py --run-dir interactive
```

派子代理，提示词与 Task 16 Step 2 相同，但：工作目录与 project_root 换成 `interactive`；用户请求中「希望的协作方式」一行改为「协作写作，科学问题定下来之前先给我看」；禁止联网检索（「本次不检索文献，按离线处理」），以节省时间。

检查（记入 `checks.md`）：子代理在确认点停下并返回确认信息；信息符合 `references/confirm_prompt.md` 的格式，不含内部编号；`proposal/scientific_case.yaml` 的 `status` 为 `draft`；`extraTex/` 下各章仍是空白（只有两行头部）。

- [ ] **Step 2: 修改，再同意**

用 SendMessage 继续该子代理，发送：「修改：删掉科学问题二」。检查：`version` 变为 2；`scientific_case.md` 重新生成，只剩一个科学问题；对应的研究任务被删除或改挂到剩下的问题上；`case.py validate` 通过；子代理再次停在确认点。

再发送：「同意。本次测试到此为止，不要继续写正文。」检查：`status` 为 `confirmed`；`assumptions.md` 的「## 确认点状态」新增一行「第 2 版：已确认」。

- [ ] **Step 3: 写完后修改科学论证，检测失效章节**

```bash
cd /home/juli/guoziran/nsfc-proposal-eval && cp -r e2e e2e-stale
R=/home/juli/guoziran/ChineseResearchLaTeX; P=/home/juli/guoziran/nsfc-proposal-eval/e2e-stale/projects/proj
python3 - "$P" <<'PY'
import sys, yaml, pathlib
root = pathlib.Path(sys.argv[1])
plan = yaml.safe_load((root / "proposal" / "section_plan.yaml").read_text(encoding="utf-8"))
written = [f for f in plan["files"] if (root / f["file"]).is_file() and len((root / f["file"]).read_text(encoding="utf-8").strip().splitlines()) > 2]
unmarked = [f["file"] for f in written if f.get("written_with_case_version") is None]
assert not unmarked, f"前置条件不满足，e2e 运行漏了 mark-written：{unmarked}"
print("已写章节数：", len(written))
path = root / "proposal" / "scientific_case.yaml"
case = yaml.safe_load(path.read_text(encoding="utf-8"))
case["hypothesis"]["statement"] += "（测试修改）"
path.write_text(yaml.safe_dump(case, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY
python3 $R/skills/nsfc-proposal/scripts/case.py bump --project-root $P
python3 $R/skills/nsfc-proposal/scripts/consistency_check.py --project-root $P | grep -c "章节依据旧版科学论证"
```

Expected: 前置检查通过并打印已写章节数；`grep -c` 的计数等于它；`consistency_check.py` 退出码为 1。前置检查失败时，这是 e2e 运行违反 SKILL.md 的发现，记入 `checks.md`，不是一致性检查的缺陷。

- [ ] **Step 4: 无 wispaper 降级**

用 e2e 任务目录中的关键词检索式，不传 `--host-results` 重跑检索：

```bash
R=/home/juli/guoziran/ChineseResearchLaTeX
T=$(ls -d /home/juli/guoziran/nsfc-proposal-eval/e2e/.bensz-api/task-* | head -1)
python3 $R/skills/research-literature-search/scripts/search_runner.py run --topic "GGN invasiveness" \
  --query-file $T/nsfc-proposal/input/keyword_queries.json --output-dir /home/juli/guoziran/nsfc-proposal-eval/fallback-bundle --max-results-per-query 20
python3 - <<'PY'
import json
m = json.load(open("/home/juli/guoziran/nsfc-proposal-eval/fallback-bundle/manifest.json", encoding="utf-8"))
print({a["provider"]: a["status"] for a in m["attempts"][:3]})
print(m["status"], m["counts"]["deduped"])
PY
```

Expected: `mcp` 为 `skipped`，`openalex` 为 `success`；`status` 为 `success` 或 `partial_success`，`deduped` > 0。离线环境下记为「未执行」。

---

### Task 18: 缺陷 D1–D7 复查

**Files:**
- Create: `E/defects.md`

对 `E/e2e/projects/proj` 逐条检查，结果写入 `E/defects.md`（每条：检查方法、证据摘录、通过/不通过）：

| 缺陷 | 检查方法 |
|---|---|
| D1 研究方案写进立项依据 | 通读 `1.1`；检索「技术路线」「样本量」「第一步」「第二步」「年度」，只允许一句衔接 |
| D2 回避「多模态」 | `1.1` 中出现「多模态」及其界定；`consistency.json` 无 `term_unused` |
| D3 人群替换不讨论偏倚 | `1.1` 或 `2.1` 同时出现筛查人群与手术样本，并讨论偏倚或外推边界 |
| D4 缺少简单基线 | `2.1` 的对照包含病灶大小或实性成分比例这类临床、形态学基线 |
| D5 前期基础无占位 | `3.1` 有可见的 `【待补充：……】`，且列在 `assumptions.md` |
| D6 自拟设计未记录 | 正文出现的、申请人没提供的设计（如「多中心」「合作医院」）都列在 `assumptions.md` 的「## AI 拟定项」 |
| D7 占位不可见 | `consistency.json` 无 `hidden_placeholder` |

- [ ] **Step 1: 逐条检查并记录**
- [ ] **Step 2: 处理不通过项**

某项不通过时：找出对应的指南（D1 → `references/section_boundaries.md`；D2、D3、D4、D6 → `references/scientific_case_guide.md`；D5、D7 → 写作 skill 的 `SKILL.md` 接入段或 `SKILL.md` 第 6 步），修改措辞使要求更明确，提交（`fix(nsfc-proposal): ...`），然后在新的运行目录（`e2e-2`）重跑 Task 16 Step 2 与本任务。最多迭代 2 轮；仍不通过的写入最终报告，不得记为通过。

---

### Task 19: 盲评对比（离线、各 2 次）

**Files:**
- Create: `E/new-1`、`E/new-2`、`E/ctl-1`、`E/ctl-2`（运行目录）
- Create: `E/normalize_full.py`、`E/blind/`（统一格式稿件、映射、评审）、`E/REPORT.md`

- [ ] **Step 1: 准备四个运行目录**

```bash
cd /home/juli/guoziran/nsfc-proposal-eval
for r in new-1 new-2 ctl-1 ctl-2; do python3 prepare_project.py --run-dir $r; done
```

- [ ] **Step 2: 并行派四个子代理（同一条消息发出）**

共同要求（写进每个提示词）：不联网；不使用任何 MCP 检索工具；不检索文献；全自动，不停下提问；用户请求为 `E/input_full.md` 全文；不得修改 `/home/juli/guoziran/ChineseResearchLaTeX` 和 `E/crl-main` 下的文件。

- `new-1`、`new-2`：工作目录与 project_root 为各自目录；按 `/home/juli/guoziran/ChineseResearchLaTeX/skills/nsfc-proposal/SKILL.md` 执行，并在提示词中原样写明：「本次运行把 config.yaml 的 literature.use_wispaper 视为 false，按 SKILL.md 第 3 步『完全离线』的路径执行，跳过 3–6。」
- `ctl-1`、`ctl-2`：工作目录与 project_root 为各自目录；依次按 `E/crl-main/skills/` 下的 `nsfc-justification-writer`、`nsfc-research-content-writer`、`nsfc-research-foundation-writer`、`nsfc-abstract` 的 `SKILL.md` 执行，每个 skill 都以 `input_full.md` 为输入，按各自 SKILL.md 正常工作（可读取项目中已写成的章节）；不使用 nsfc-proposal。

每个子代理完成后报告写入的文件与偏离之处。

- [ ] **Step 3: 写 `E/normalize_full.py`**

```python
#!/usr/bin/env python3
"""把一份项目的各章正文合成一份统一格式的 Markdown，供盲评。

复用对比实验的格式归一化函数，去掉 LaTeX 标记、统一标题与列表、统一占位写法。
用法：python3 normalize_full.py <project_root> <输出.md>
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

COMPARE = Path("/home/juli/guoziran/nsfc-compare-20261009/normalize_and_check.py")
SPEC = importlib.util.spec_from_file_location("normalize_and_check", COMPARE)
NC = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(NC)

SECTIONS = [
    ("立项依据", "extraTex/1.1.立项依据.tex"),
    ("研究内容", "extraTex/2.1.研究内容.tex"),
    ("特色与创新", "extraTex/2.2.特色与创新.tex"),
    ("年度研究计划", "extraTex/2.3.年度研究计划.tex"),
    ("研究基础", "extraTex/3.1.研究基础.tex"),
    ("工作条件", "extraTex/3.2.工作条件.tex"),
]


def demote(md: str) -> str:
    """各章内部标题整体下移一级，让「## 章名」成为唯一的二级标题。"""
    return "\n".join("#" + line if line.startswith("#") else line for line in md.splitlines())


def main() -> int:
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    parts = []
    for name, rel in SECTIONS:
        tex = (root / rel).read_text(encoding="utf-8")
        body = NC.unify_lists(NC.unify_placeholders(NC.normalize_md(NC.latex_to_md(tex))))
        parts.append(f"## {name}\n\n{demote(body)}")
    abstract = root / "NSFC-ABSTRACTS.md"
    if abstract.exists():
        parts.append("## 摘要\n\n" + demote(NC.unify_placeholders(abstract.read_text(encoding="utf-8"))))
    out.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 统一格式并随机标 A/B**

```bash
cd /home/juli/guoziran/nsfc-proposal-eval && mkdir -p blind
for r in new-1 new-2 ctl-1 ctl-2; do python3 normalize_full.py $r/projects/proj blind/$r.md; done
python3 - <<'PY'
import json, random, shutil
seed = random.SystemRandom().randrange(10**6)
rng = random.Random(seed)
mapping = {"seed": seed, "pairs": {}}
for pair, (new, ctl) in {"p1": ("new-1", "ctl-1"), "p2": ("new-2", "ctl-2")}.items():
    a, b = (new, ctl) if rng.random() < 0.5 else (ctl, new)
    mapping["pairs"][pair] = {"A": a, "B": b}
    for label, src in (("A", a), ("B", b)):
        text = open(f"blind/{src}.md", encoding="utf-8").read()
        open(f"blind/{pair}_{label}.md", "w", encoding="utf-8").write(f"# 稿件 {label}\n\n{text}")
json.dump(mapping, open("blind/mapping.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(mapping)
PY
```

检查统一格式后的稿件里没有暴露来源的痕迹（skill 名、`proposal/`）；有则补充归一化规则后重做本步。

正文中的 S 编号**不做归一化**：`main` 上的 research-content-writer 检查脚本要求正文出现 S 编号（Task 4 修复的矛盾），对照组稿件可能带有 S 编号，这正是现状的一部分。用 `grep -cE '(^|[^A-Za-z0-9])S[0-9]+([^A-Za-z0-9]|$)' blind/<运行>.md` 统计每份稿件的 S 编号数，写入报告。

- [ ] **Step 5: 盲评（每对 2 名评审，阅读顺序相反，共 4 份，可并行）**

评审提示词（每份只给 `E/input_for_review.md` 与该对的两份稿件，不给映射）：

```text
你是国家自然科学基金医学影像方向的函评专家。阅读申请人信息和两份申请书正文（稿件 A、B），按下表逐项打分（1–5 分），总分 40。
先读稿件 {先读的一份}，再读另一份。

| 维度 | 看什么 |
|---|---|
| 科学问题凝练 | 问题是否针对认知缺口，是否可回答 |
| 立项论证 | 现状与缺口是否具体、有据，是否夸大 |
| 科学假设 | 是否可证伪，否定条件是否合理 |
| 创新与切入点 | 与现有工作的差别是否清楚、可信 |
| 对申请人材料的忠实度 | 有无编造数据、成果、合作单位；缺失处是否标明 |
| 表达 | 大同行能否读懂，有无套话 |
| 可用程度 | 申请人修改多少就能提交 |
| 跨章一致性 | 各章的科学问题、假设、任务、术语是否前后一致，研究基础是否覆盖各项任务 |

输出：评分表；每个维度各引原文一句作依据；总体判断哪份更好及差距大小；每份各列 3 处最该改的地方。
```

结果存为 `E/blind/review_p1_1.md`、`review_p1_2.md`、`review_p2_1.md`、`review_p2_2.md`。

- [ ] **Step 6: 汇总，写 `E/REPORT.md`**

按 `mapping.json` 还原身份，计算实验组与对照组在 4 份评审中的总分均值与各维度均值。

通过标准：实验组的总分、「跨章一致性」「可用程度」三项均值都不低于对照组；「对申请人材料的忠实度」均值不低于对照组。

报告包含：结论；评分表；各稿件的 S 编号数；客观检查（Task 16）；D1–D7 复查（Task 18）；局限（评审由模型扮演；只有一个课题；每组 2 次；对照组继承了 `main` 上 S 编号泄漏的缺陷，盲评差距中可能含这一项，报告中单独说明它对「忠实度」「可用程度」的影响）；文件清单。写作遵守用户的风格要求：短句、少副词、不写空泛总结。

---

### Task 20: 收尾

- [ ] **Step 1: 全量测试与工作区检查**

```bash
cd /home/juli/guoziran/ChineseResearchLaTeX
PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider --continue-on-collection-errors tests/
git status --short
find skills tests -name "__pycache__" -o -name ".pytest_cache" | head
```

Expected: 除 research-idea 的 4 个既有 errors 外 0 failed（写计划时在临时副本中按本计划应用全部代码后实测：175 passed, 4 errors）。research-idea 的收集错误会中断整个运行，所以必须带 `--continue-on-collection-errors`。出现其他失败时，先在 `E/crl-main` 中复现：`main` 上同样失败的记为既有问题并写入报告，否则修复。`find` 无输出。

- [ ] **Step 2: 整个分支的代码审查**

用 superpowers:requesting-code-review，审查范围 `git diff main...nsfc-proposal`。重点：脚本的路径越界与网络请求；SKILL.md 与脚本参数是否一致；没有 `proposal/` 时写作 skill 的行为是否不变。按 superpowers:receiving-code-review 处理意见，修改后提交。

- [ ] **Step 3: 向申请人交付**

报告：分支名与提交列表；验收结论（`E/REPORT.md` 的结论与通过情况）；未通过或未执行的检查；`main` 上本来就失败的两个 `validate_skill.py`（content-writer、foundation-writer，与现行规范冲突，未修）；待申请人决定的事项（是否推送到 GitHub fork；NSFC_Young 模板未引用 `4.5.生成式人工智能.tex`，是否要在模板中修正）。不推送。

---

## 自查记录（写计划时完成）

**设计文档覆盖：**

| 设计文档章节 | 对应任务 |
|---|---|
| 4.1 材料与项目画像 | Task 7、12 |
| 4.2 科学论证 | Task 7、8、12 |
| 4.3 / 6 文献与证据 | Task 5、10、12 |
| 4.4 章节分配 | Task 7、8、12 |
| 4.5 确认点 | Task 9、12、17 |
| 4.6 分章写作 | Task 1–4、12、13 |
| 4.7 跨章一致性检查 | Task 11、12 |
| 4.8 收尾与 AI 使用说明 | Task 7（落点）、12 |
| 5 共享文件 | Task 6–9 |
| 7 改动清单 | Task 1–14 |
| 8 已知缺陷修复 | Task 1–4 |
| 9 错误处理 | Task 8、10、11（测试）、12（失败与恢复表） |
| 10.1 单元测试与回归 | Task 1–14 |
| 10.2 端到端 | Task 16、17 |
| 10.3 缺陷复查 | Task 18 |
| 10.4 盲评 | Task 19 |
| 11 实现约束 | Global Constraints；Task 12 测试 |
| 13 申请人的决定 | Global Constraints（BAC、作者） |

**类型与命名一致性：** `ProposalError`、`proposal_paths`、`scan_latex_tree`、`read_bib_index`、`BibIndex.doi_keys`、`case_ids`、`claim_ids`、`PLAN_KEYWORDS`、`info_form(case, plan, writer)`、`run(project_root, records_path, task_root, *, session, dry_run)`、`check_project(project_root, config)` 在定义处与使用处一致；CLI 参数名 `--project-root`、`--task-root`、`--writer`、`--set`、`--file`、`--host-results` 在脚本、测试与 SKILL.md 中一致。
