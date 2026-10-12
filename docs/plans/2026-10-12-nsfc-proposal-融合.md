# nsfc-proposal 融合实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 nsfc-proposal 和它调用的 6 个 skill 融合成一个自包含的 nsfc-proposal。下级 skill 的写作规则变成 `references/` 下的章节写法，确定性检查变成 `scripts/` 下的脚本，nsfc-proposal 不再读取或调用任何兄弟 skill 目录。

**Architecture:**
- **配置**：研究期限表、章节检查参数、摘要限制、篇幅预算并入 `skills/nsfc-proposal/config.yaml`。各章的条目不再记 `writer`，改记章节名 `section`；旧项目里的 `writer` 照常接受、不再使用。
- **脚本**：新增 `plan_years.py`、`literature.py`（与 `literature_records.py`）、`chapter_check.py`（与 `abstract_check.py`）、`length_check.py`。都从 `Path(__file__).resolve().parents[1] / "config.yaml"` 读配置，即 nsfc-proposal 自己的配置。只搬 nsfc-proposal 实际走到的代码路径：文献只走 wispaper 的宿主结果；补摘要只走离线路径；立项依据写作器的 AI responder、写作教练、HTML 报告、示例推荐、版本管理一律不搬。
- **文档**：`SKILL.md` 只留总控、任务类型、步骤与规则；各章写法放进 `references/justification.md`、`research_content.md`、`foundation.md`、`abstract.md`，篇幅对齐放进 `references/length.md`。规则冲突时按 nsfc-proposal 现行规则统一（只在确认点提问；缺失写占位；措辞不超过证据）。

**Tech Stack:** Python 3 标准库、PyYAML、requests；pytest（unittest 风格）。

**Spec:** `docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md`。本轮要求来自申请人 2026-10-12 的对话：「这么多 skill，能不能整合为一个啊？」「我要的不仅仅是简单的复制合并，是要融合，要非常地协调，另外我不想再看到 nsfc-proposal 里面下级还有多个 skill，你看看是弄成 reference 还是 script，开始融合吧」。Task 6 在 spec 末尾追加一节记录融合后的结构。

## 控制者替申请人做的决定（可否决）

1. **6 个独立 skill 留在仓库原位，一字不动。** research-literature-search 还被 research-idea、research-literature-review 调用；其余 5 个与上游同名。融合的标准是 nsfc-proposal 对它们零依赖，Task 7 把它们临时移走后验证。
2. **拆分规则用 AGENTS.md 原话：** 确定性工作交给脚本，语义判断留给 reference。逐个文件套用，不按「原来是脚本就搬脚本」。
3. **不搬的东西：** 立项依据写作器的 `run.py` 与 `core/`（无 AI responder 时 `coach` 只输出模板文字，见 `core/writing_coach.py` 的 `_fallback`）；两个写作器的 `run_checks.py`、`validate_skill.py`、`create_test_session.py`、`_yaml_utils.py`；摘要的 `write_abstracts_md.py`（摘要由 AI 直接写，脚本只校验）；文献检索的 Semantic Scholar、Crossref 检索 provider 与 `--provider-order`、补充检索逻辑。
4. **不做标题结构守卫。** 模板正文里的标题是示例课题的标题（如 `projects/NSFC_Young/extraTex/1.1.立项依据.tex` 的「案例概述」），整章重写时本来就要换。改为写前留副本：写某章前把原文件复制到 `T/nsfc-proposal/output/before/`，出问题时从这里恢复。
5. **新增三种任务：** 只改或润色已写好的一章、只写摘要与题目、篇幅对齐。下级 skill 原本的单独用法由这三种接住。
6. **版本 0.1.0 → 0.2.0。** 公开的命令、目录和配置都变了。

三件外部动作不在本计划内，收尾时单独问申请人：web 应用 `nsfc_web/paths.py` 改成只部署 nsfc-proposal 并重新部署；`~/.claude/skills` 重新同步并处理旧的 6 个副本；用 wispaper 与 WisImage 额度做一次完整的 fresh-3 运行。

## Global Constraints

- 分支 `nsfc-proposal`，远程 `lauorie`（git@github.com:Lauorie/guoziran.git）。各任务不推送，由控制者在终审后统一推送。
- 不新增必需的第三方依赖：只用标准库、PyYAML、requests。
- 脚本用 `Path(__file__).resolve()` 定位 skill 资产；文件读写显式 `encoding="utf-8"`。
- `skills/nsfc-proposal/` 下任何文件不得引用兄弟 skill 的路径（`../nsfc-`、`SKILL_ROOT.parent`、`SK/`、`skills/nsfc-abstract` 之类）。CHANGELOG 叙述历史时可以提到 skill 名。
- `skills/` 下除 `nsfc-proposal/` 外的目录不改。
- 仓库中不得出现本机用户目录的绝对路径和团队服务的域名。
- HTTP 请求不附带个人邮箱或身份信息（不加 mailto）。
- 国自然写作的 skill 中不得出现 OpenAlex（文档测试已钉住）；检索只用 wispaper，CrossRef 只用于核对元数据。
- `.bib` 条目文本只由脚本按检索结果写入；不手写、不手改。
- 正文占位格式固定为 `【待补充：……】`。
- 示例不得回显对比基准（中标书）的题材：创造力、具身、物化、照样制作、近红外、综合实践活动课程、课时、班级等词不进 skill 文档与测试。tracked 文件不提中标书本身，也不提范例。
- 对用户与正文一律称生图服务为 WisImage，不写模型名（`config.yaml` 中 `figures.model` 那行与它的注释原样保留）。
- 版本号只写在 `config.yaml:skill_info.version`。nsfc-proposal 改为 0.2.0，CHANGELOG 新增 `## [0.2.0] - 2026-10-12` 段，段末一行「本分支未写 BAC 记录，经负责人同意。」。根 `CHANGELOG.md` `[Unreleased]` 加一句，接在「- 第六轮终审修复：」那一行之后（没有这一行时接在最后一条 nsfc-proposal 相关行之后）、紧随其后的「- 本分支未写 BAC 记录，经负责人同意。」之前。
- 测试放 `tests/nsfc-proposal/`，unittest 风格，文件名以 `test_np_` 开头且全仓唯一。测试不联网，产物写系统临时目录。从下级 skill 测试移植来的用例，在新文件中改为调用 nsfc-proposal 的脚本；原测试文件不动。
- 测试命令（仓库根目录）：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider -W ignore::pytest.PytestConfigWarning tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/nsfc-research-foundation-writer tests/research-literature-search tests/research-literature-review tests/nsfc-ref-alignment`。基线 474 passed、31 subtests passed。
- 提交信息 `<type>(nsfc-proposal): <中文摘要>`，末尾附 `Co-Authored-By: <实际完成提交的模型> <noreply@anthropic.com>`。每次提交前测试 0 failed；`find skills tests -name __pycache__ -o -name .pytest_cache` 无输出。不要用 `python3 -I`。
- 文件规模：新脚本每个不超过 800 行，尽量在 400 行以内；超过时按职责拆成两个模块。

## Review Focus

1. **旧项目**：nsfc-try 与评测目录里的 `section_plan.yaml` 只有 `writer`、没有 `section`。`case.py validate`、`case.py brief`、`consistency_check.py` 对它们照常工作，按 `file`（含 `fallback_file`）在配置中找到章节。→ Task 1 的测试。
2. **文献池的空结果**：host 文件里有的检索式没有论文，或全部没有论文。前者状态 `partial_success`、退出码 0；后者状态 `failed`、退出码 1，不写空的候选文件以外的东西。→ Task 2 的测试。
3. **摘要格式**：中文摘要含 ASCII 双引号、直角引号或千分位逗号时报错；中文弯引号「“”」通过；标题候选少于配置条数、主要研究领域超过 25 个汉字时报错。→ Task 3 的测试。
4. **研究期限**：项目类型不在年数表中时按默认年数并给出警告；年度计划写到第 N+1 年报错；「第十年随访」这类远处叙述不报；「L5–S1」「S100β」不算内部编号。→ Task 3 的测试。
5. **篇幅报告位置**：`length_check.py` 的 `--out-dir` 必填，相对路径按当前目录解析，报告不会落进项目目录（旧脚本按 `--input` 解析，曾把报告写进申请书项目）。→ Task 4 的测试。

---

### Task 1: 配置并入、研究期限、篇幅预算与章节识别

**Files:**
- Modify: `skills/nsfc-proposal/config.yaml`
- Create: `skills/nsfc-proposal/scripts/plan_years.py`（移植自 `skills/nsfc-research-content-writer/scripts/plan_years.py`）
- Modify: `skills/nsfc-proposal/scripts/proposal_common.py`、`case.py`、`case_render.py`、`case_validate.py`、`consistency_check.py`
- Test: `tests/nsfc-proposal/test_np_plan_years.py`（新建，移植 `tests/nsfc-research-content-writer/test_nrcw_years.py` 中针对 `plan_years` 的用例）；修改 `test_np_init.py`、`test_np_render.py`、`test_np_validate.py`、`test_np_consistency.py` 中涉及 `writer`、`to-info-form`、`length_budget_source` 的地方

**Interfaces:**
- Produces（后续任务依赖）：
  - `config.yaml` 新增顶层键 `yearly_plan`、`chapter_checks`、`abstract`、`length_standard`、`length_checker`；删去 `length_budget_source`；`sections[]` 每条去掉 `writer`，加 `guide`（参考资料相对路径或缺省）与 `brief`（`立项依据`/`研究内容`/`研究基础` 或缺省）。
  - `plan_years.py`：`load_yearly_plan(config_path=None) -> YearlyPlan`、`duration_years(project_type, config_path=None) -> tuple[int, bool]`、`year_label(year) -> str`、`normalize_type(text) -> str`、常量 `CN_NUMERALS`。`DEFAULT_CONFIG` 指向 nsfc-proposal 的 `config.yaml`。
  - `proposal_common.section_for(config, entry_or_file) -> Mapping | None`：参数是 `section_plan.yaml` 的条目（Mapping）或文件相对路径（str）。条目有 `section` 时按名字找；否则按 `file` 与配置中各章的 `file`、`fallback_file` 匹配。找不到返回 None。
  - `case.py brief --project-root P --section 立项依据|研究内容|研究基础 --out FILE`，取代 `to-info-form --writer …`。
  - `section_plan.yaml` 新条目：`file`、`section`、`must_include`、`must_exclude`、`length`、`placeholders`、`written_with_case_version`。

- [ ] **Step 1: 并入配置。** 在 `config.yaml` 中：
  - `sections` 改为下列内容（`must_exclude` 照旧值）：

    ```yaml
    sections:
      - name: 立项依据
        file: extraTex/1.1.立项依据.tex
        guide: references/justification.md
        brief: 立项依据
        must_exclude: [实验步骤, 技术路线, 样本量设计, 年度安排, 研究方案细节]
      - name: 研究内容
        file: extraTex/2.1.研究内容.tex
        guide: references/research_content.md
        brief: 研究内容
        must_exclude: [国内外研究现状的展开综述]
      - name: 特色与创新
        file: extraTex/2.2.特色与创新.tex
        guide: references/research_content.md
        brief: 研究内容
        must_exclude: [首次, 国际领先, 填补空白]
      - name: 年度研究计划
        file: extraTex/2.3.年度研究计划.tex
        guide: references/research_content.md
        brief: 研究内容
        must_exclude: [研究背景]
      - name: 研究基础
        file: extraTex/3.1.研究基础.tex
        guide: references/foundation.md
        brief: 研究基础
        must_exclude: [申请人未提供的论文、数据或预实验结果]
      - name: 工作条件
        file: extraTex/3.2.工作条件.tex
        guide: references/foundation.md
        brief: 研究基础
        must_exclude: [申请人未提供的平台或设备]
      - name: 摘要
        file: NSFC-ABSTRACTS.md
        guide: references/abstract.md
        must_exclude: [内部编号]
      - name: 生成式人工智能使用说明
        file: extraTex/4.5.生成式人工智能.tex
        fallback_file: proposal/ai_declaration.md
        must_exclude: [运行日志中没有记录的 AI 使用]
    ```
  - 加 `yearly_plan`，内容照抄 `skills/nsfc-research-content-writer/config.yaml` 的同名段（含注释）。
  - 加 `chapter_checks`：

    ```yaml
    chapter_checks:
      # 绝对化措辞，只按短语匹配；单独的「首次」（如「首次随访」）是叙述先后，不报
      risk_phrases: [首次提出, 首次发现, 首次实现, 首次揭示, 首次构建, 首次建立, 国内首次, 国际首次, 世界首次, 国内首创, 领先, 填补空白, 突破性]
      # 含 S+数字、但不是内部编号的专业写法；误报时把写法加在这里
      allowed_s_tokens: ["L5-S1", "L5–S1", "S100", "S100β", "S1P", "S1 受体", "S1受体"]
      min_risks: 3   # 研究基础中研究风险的条数下限
    ```
  - 加 `abstract`：

    ```yaml
    abstract:
      zh_max_chars: 400
      en_max_chars: 4000
      content_points: {min: 3, max: 4}
      zh_recommended_sentences: 5
      title_candidates: 5
      field_max_chars: 25
      headings:
        title: "# 标题建议"
        zh: "# 中文摘要"
        en: "# English Abstract"
        field: "# 主要研究领域"
    ```
  - 加 `length_standard`，内容照抄 `skills/nsfc-length-aligner/config.yaml` 的同名段（含注释）；加 `length_checker`，内容照抄其 `checker` 段，`exclude_globs` 中去掉 `"**/.nsfc-length-aligner/**"`。
  - 删去 `length_budget_source` 一行。`skill_info.description` 改为「国自然申请书正文的统一入口：建立科学论证、证据图谱和章节分工，检索并核实文献，按各章写法成稿，检查摘要、篇幅与跨章一致性。」。版本号留到 Task 6 改。

- [ ] **Step 2: 写失败测试。** 新建 `tests/nsfc-proposal/test_np_plan_years.py`：移植 `test_nrcw_years.py` 中直接调用 `plan_years` 的用例（青年 3 年、面上 4 年、重点 5 年、未匹配时默认 3 年且 matched 为 False、全角括号与空格规范化、坏配置抛 ValueError），导入路径改为 `skills/nsfc-proposal/scripts`。再加一条：`DEFAULT_CONFIG` 的父目录是 `skills/nsfc-proposal`。修改 `test_np_init.py`：`init` 写出的每个条目有 `section`、没有 `writer`；研究内容条目的 `length` 为 `{"min": 7000, "max": 15000, "unit": "cjk_chars"}`。修改 `test_np_render.py`：原 `to-info-form` / `info_form(case, plan, writer)` 的用例改为 `brief` / `brief_text(case, plan, section, config)`，三种 `--section` 各一条；未知章节报 ProposalError。修改 `test_np_validate.py`：只有 `writer` 没有 `section` 的条目通过校验；`section` 写了配置中没有的章节名时报错「未知章节」。修改 `test_np_consistency.py`：一个只有 `writer: nsfc-justification-writer` 的旧条目和一个只有 `section: 立项依据` 的新条目都触发 `few_citations`；`section: 生成式人工智能使用说明`（或旧 `writer: nsfc-proposal`）的条目不报过程说明。

- [ ] **Step 3: 运行测试，确认失败。** `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_plan_years.py tests/nsfc-proposal/test_np_init.py tests/nsfc-proposal/test_np_render.py tests/nsfc-proposal/test_np_validate.py tests/nsfc-proposal/test_np_consistency.py`，新用例失败。

- [ ] **Step 4: 实现。**
  - `plan_years.py`：照抄原文件，模块说明改为「年数表只写在本 skill 的 config.yaml（yearly_plan 段）」，删去 importlib 加载的说明。错误信息里的 `config.yaml yearly_plan` 照旧。
  - `proposal_common.py`：加 `section_for`（见 Interfaces）。
  - `case.py`：`load_length_budgets` 改为读 `config["length_standard"]`（缺段时返回空列表）；`init_proposal` 的条目写 `"section": section["name"]`，不写 `writer`；`to-info-form` 子命令换成 `brief`（`--section` 的 choices 取配置中各章 `brief` 的去重值，顺序同配置）；`from case_render import WRITERS, info_form` 改为 `from case_render import brief_text`。
  - `case_render.py`：删去 `WRITERS`、`PLAN_YEARS_PY` 与 importlib 加载，改为 `from plan_years import duration_years`；`yearly_plan` 配置有误时的 ProposalError 文字改为「config.yaml 的 yearly_plan 配置有误：……」。`_plan_entries(plan, brief, config)` 按 `section_for(config, entry)` 的 `brief` 字段筛选条目；`_section_notes` 同步改签名。三个表单函数的标题改为 `# 立项依据写作要点（第 N 版科学论证）`、`# 研究内容写作要点（含特色与创新、年度研究计划；第 N 版科学论证）`、`# 研究基础写作要点（含工作条件；第 N 版科学论证）`；正文字段不变。`info_form` 改名 `brief_text(case, plan, section, config)`，未知 section 报「未知章节：X；可选：立项依据、研究内容、研究基础」。模块说明删去「照抄各写作 skill 的 references/info_form.md」。`render_case_md` 中章节表那一列由 `writer` 改为章节名（取 `section_for(...)["name"]`，找不到写「—」）。
  - `case_validate.py`：删去「缺少 writer」；条目有 `section` 时，名字必须是配置中的章节名，否则报「{file} 的 section 不是已知章节：X」。
  - `consistency_check.py`：删去 `JUSTIFICATION_WRITER`、`PROCESS_DESCRIBING_WRITER`；用 `section_for(config, entry)` 取章节名，`立项依据` 做引用下限检查，`生成式人工智能使用说明` 免查过程说明与空占位。

- [ ] **Step 5: 跑测试命令（Global Constraints），全部通过。** 再确认：`grep -rn "nsfc-research-content-writer\|nsfc-length-aligner\|SKILL_ROOT.parent\|length_budget_source" skills/nsfc-proposal/scripts skills/nsfc-proposal/config.yaml` 无输出。

- [ ] **Step 6: 提交。** `refactor(nsfc-proposal): 研究期限、篇幅预算并入本 skill，章节按名字识别`

---

### Task 2: 文献池（literature.py）

**Files:**
- Create: `skills/nsfc-proposal/scripts/literature_records.py`（记录规范化、宿主结果适配、去重）
- Create: `skills/nsfc-proposal/scripts/literature.py`（命令行：`pool`、`abstract-queries`、`enrich-abstracts`）
- Test: `tests/nsfc-proposal/test_np_literature_pool.py`、`tests/nsfc-proposal/test_np_literature_abstracts.py`

**移植来源**（只搬下列路径，不搬其余）：`skills/research-literature-search/scripts/` 的 `providers/host_results.py`（wispaper 适配、DOI 从链接提取、摘要片段识别）、`candidate_schema.py` 与 `normalize_papers.py`（`rls.paper.v1` 记录）、`dedupe_papers.py`（canonical 去重）、`search_runner.py` 中 `abstract_queries`、`enrich_abstracts` 的离线路径（`_reusable_abstracts`、`_needs_abstract`、`_host_match`、`_host_candidates`、`_fill_from_host`、`_strip_ellipses`）。删掉 Semantic Scholar、Crossref 检索 provider、provider 顺序与补充检索、预印本领域策略、网络请求与重试、旧 `title/year/id` 适配器。

**Interfaces:**
- Consumes：`wispaper_search.py` 写出的 `T/nsfc-proposal/output/wispaper/<名称>_host.json`（`rls.host_results.v1`）。
- Produces：
  - `python3 S/scripts/literature.py pool --task-root T --name <名称> [--name <名称> ...] [--max-per-query N] [--out <池名>]`：读 `T/nsfc-proposal/output/wispaper/<名称>_host.json`（可多个），写 `T/nsfc-proposal/output/literature/<池名>/`，池名缺省取第一个 `--name`。目录内：`candidates.jsonl`（去重后的 `rls.paper.v1` 记录，每条带 `record_id`、`title`、`authors`、`year`、`identifiers.doi`、`abstract`、`abstract_status`、`publication`、`sources`、`query_matches`、`quality_warnings`、`provenance`）、`manifest.json`（`schema: "nsfc-proposal.literature_pool.v1"`、`status`、各 host 文件的 sha256、各检索式的命中篇数、去重前后条数、`max_per_query`）。`--max-per-query` 缺省 20。退出码：0 = `success`（每条检索式都有结果）或 `partial_success`（部分检索式没有结果，manifest 列出这些检索式）；1 = `failed`（全部检索式都没有结果；仍写 manifest，候选文件为空）；2 = 参数或输入错误（host 文件不存在、schema 不对、路径在 T 之外）。
  - `python3 S/scripts/literature.py abstract-queries --input <记录.jsonl> --output <检索式.json> [--reuse <上一次补全的输出>]`：列出缺完整摘要的记录标题，格式 `{"queries": [...]}`，行为同原 `search_runner.py abstract-queries`。
  - `python3 S/scripts/literature.py enrich-abstracts --input <记录.jsonl> --output <输出.jsonl> [--host-results <host.json>] [--reuse <上一次的输出>]`：只从 host 文件与 `--reuse` 取摘要，不发任何网络请求（没有 `--offline` 开关，离线是唯一行为）。汇总写 `<输出>.summary.json`，字段 `attempted`、`filled`、`reused`，语义同原脚本。
  - 记录字段与原 `research-literature-search` 产出的 `rls.paper.v1` 一致：`bib_resolve.py` 读的 `identifiers.doi`/`doi`、`title`、`year`、`record_id`、`abstract` 产出方式不变。

- [ ] **Step 1: 写失败测试。** 移植 `tests/research-literature-search/test_rls_host_results.py`、`test_rls_host_abstracts.py`、`test_rls_enrich_abstracts.py` 中与宿主结果、离线补摘要有关的用例，改为调用 `literature.py` / `literature_records.py`；删掉依赖网络 provider 或 `--provider-order` 的用例。再加：
  - 两个 host 文件合并成一个池，同一 DOI 只留一条，`query_matches` 含两边的检索式；
  - host 文件中一条检索式 `papers` 为空 → `partial_success`、退出码 0、manifest 列出该检索式；
  - 全部为空 → `failed`、退出码 1；
  - `--task-root` 之外的 `--out` 路径（如 `../x`）→ 退出码 2；
  - 摘要片段（以「…」结尾）不当作摘要，存进 `provenance.host_abstract_snippet`；
  - `enrich-abstracts` 在 `--host-results` 缺省、只有 `--reuse` 时只沿用旧摘要；运行时 `socket.socket` 被打桩为抛异常，测试仍通过（证明不联网）。
- [ ] **Step 2: 运行，确认失败。**
- [ ] **Step 3: 实现。** 两个模块各不超过 500 行。`literature.py` 用 `proposal_common` 的路径工具解析 T；manifest 的 JSON 用 UTF-8、`sort_keys=True`、`ensure_ascii=False`。
- [ ] **Step 4: 跑测试命令，全部通过。** 确认 `grep -rni "openalex\|semantic\|provider_order\|requests" skills/nsfc-proposal/scripts/literature*.py` 无输出。
- [ ] **Step 5: 提交。** `feat(nsfc-proposal): 文献池并入本 skill，只读 wispaper 结果`

---

### Task 3: 章节检查（chapter_check.py 与 abstract_check.py）

**Files:**
- Create: `skills/nsfc-proposal/scripts/abstract_check.py`（移植自 `skills/nsfc-abstract/scripts/validate_abstract.py`）
- Create: `skills/nsfc-proposal/scripts/chapter_check.py`（移植两个 `check_project_outputs.py` 的规则）
- Test: `tests/nsfc-proposal/test_np_chapter_check.py`、`tests/nsfc-proposal/test_np_abstract_check.py`

**Interfaces:**
- Consumes：Task 1 的 `config.yaml`（`sections`、`chapter_checks`、`abstract`、`yearly_plan`）与 `plan_years.py`、`proposal_common.section_for`。
- Produces：
  - `python3 S/scripts/chapter_check.py --project-root P --section <章节名> [--section ...] [--project-type "<类型>" | --years N] [--json]`。章节名取配置 `sections[].name`；文件路径取 `P/proposal/section_plan.yaml` 中该章条目的 `file`（有 `proposal/` 时），否则取配置的 `file`。输出每条问题一行：`ERROR <文件>: <说明>` 或 `WARN <文件>: <说明>`；`--json` 时输出 `{"errors": [...], "warnings": [...]}`。退出码：0 = 无 ERROR；1 = 有 ERROR；2 = 参数错误或未知章节。研究期限优先取 `--years`，其次 `--project-type`，再次 `proposal/scientific_case.yaml` 的 `project.type`，都没有时用 `yearly_plan.default_years` 并给 WARN。
  - 各章规则：
    - 所有 `.tex` 章：文件存在且去掉注释后正文非空（ERROR）；内部编号 `S\d+`（除去 `allowed_s_tokens`，紧跟字母、数字或连字符之后的不算）（ERROR）；`risk_phrases` 命中（WARN；`特色与创新` 为 ERROR）；非标准占位写法 `[请补充：`、`[需补充：`、`[待补充：`（ERROR，提示改成「【待补充：……】」）。
    - `年度研究计划`：第 1 至第 N 年的年度标题都在（缺则 ERROR）；出现第 N+1 年（ERROR）；更远的年份不报。
    - `研究基础`：含「风险」，风险条数（按原 foundation 检查的标题与「风险一/风险1」计数）不少于 `min_risks`（ERROR）；没有「应对/预案/替代」（WARN）。
    - `工作条件`：没有「已具备/具备」或没有「尚缺/缺少/不足」（WARN）。
    - `摘要`：调用 `abstract_check.check_text(text, config)`，其 errors 记 ERROR、warnings 记 WARN。
    - `立项依据`、`研究内容`：只有通用规则。
  - `abstract_check.py`：`check_text(text: str, config: Mapping) -> dict`（键 `errors`、`warnings`、`counts`），命令行 `python3 S/scripts/abstract_check.py <文件或 -> [--json]`，退出码 0/1/2 同上。只认 Markdown 标题格式（`abstract.headings`），不认 `[ZH]` 标记。检查：四个标题齐全且顺序为标题建议、中文摘要、English Abstract、主要研究领域；中文摘要字符数（连续空白折叠为一个空格后计数，含标点）≤ `zh_max_chars`；英文 ≤ `en_max_chars`；中文摘要不含 ASCII 双引号 `"`、全角引号 `＂`、直角引号 `「」『』`、单引号 `'`、`'`、`'`（只允许 U+201C、U+201D）；中文摘要不含千分位逗号（如 `1,000`、`1，000`）；中文摘要不含 Markdown 标记 `**`、`__`、行首 `#`；标题建议含「推荐标题：」「Recommended Title:」两行，编号候选不少于 `title_candidates` 条且每条含「理由」与「EN:」；主要研究领域为一句、汉字数 ≤ `field_max_chars`；中文摘要正文末行与 `# English Abstract` 之间没有空行（WARN）。

- [ ] **Step 1: 写失败测试。** 移植 `tests/nsfc-research-content-writer/test_nrcw_checker.py`、`test_nrcw_years.py`（检查器部分）、`tests/nsfc-research-foundation-writer/test_nrfw_risk_count.py`、`test_nrfw_placeholder_style.py` 的用例到 `test_np_chapter_check.py`，改为调用 `chapter_check.py`。加：项目类型「面上项目」写到第五年报 ERROR；「第十年随访」不报；`L5–S1`、`S100β` 不报；`--section 不存在` 退出码 2；只有 `writer` 的旧 `section_plan.yaml` 也能找到文件。`test_np_abstract_check.py` 覆盖 Review Focus 第 3 条的每一项，各一正一反；再加一个完整合格的样例文件通过。
- [ ] **Step 2: 运行，确认失败。**
- [ ] **Step 3: 实现。** 两个模块各不超过 500 行；YAML 读取走 `proposal_common`，不搬 `_yaml_utils.py`。
- [ ] **Step 4: 跑测试命令，全部通过。**
- [ ] **Step 5: 提交。** `feat(nsfc-proposal): 各章检查与摘要校验并入本 skill`

---

### Task 4: 篇幅检查（length_check.py）

**Files:**
- Create: `skills/nsfc-proposal/scripts/length_check.py`（移植自 `skills/nsfc-length-aligner/scripts/check_length.py`）
- Create: `skills/nsfc-proposal/assets/length_report_template.md`（照抄 `skills/nsfc-length-aligner/templates/LENGTH_REPORT_TEMPLATE.md`）
- Test: `tests/nsfc-proposal/test_np_length_check.py`

**Interfaces:**
- Consumes：Task 1 的 `length_standard`、`length_checker`。
- Produces：`python3 S/scripts/length_check.py --input P --out-dir <目录> [--pdf <PDF>]`。`--out-dir` 必填；相对路径按当前工作目录解析（不按 `--input`）。写 `<目录>/length_report.md` 与 `length_report.json`，控制台摘要格式同原脚本。没有 `--config` 参数：配置固定取 nsfc-proposal 的 `config.yaml`。退出码同原脚本。

- [ ] **Step 1: 写失败测试。** 在临时目录建一个最小项目（`main.tex` `\input` 两个 `extraTex` 文件，一个被注释掉）：报告只统计未注释的文件；立项依据字数低于 4500 时 JSON 中该文件为偏短；`--out-dir rel/out` 从另一个当前目录运行时，报告写在当前目录下的 `rel/out`，项目目录里没有 `length_report.*`；缺 `--out-dir` 时 argparse 报错。
- [ ] **Step 2: 运行，确认失败。**
- [ ] **Step 3: 实现。** 照搬原脚本逻辑，改三处：配置读 `length_standard` 与 `length_checker`；删去 `--config`、`output_settings`、按 `--input` 解析相对 `--out-dir` 的逻辑；模板读 `assets/length_report_template.md`。原脚本约 800 行，搬后超过 800 行时把 LaTeX 解析部分拆到 `length_tex.py`。
- [ ] **Step 4: 跑测试命令，全部通过。**
- [ ] **Step 5: 提交。** `feat(nsfc-proposal): 篇幅检查并入本 skill`

---

### Task 5: 各章写法（references）

由控制者执笔：这一步是融合的核心，五份文件要与 Task 6 的 SKILL.md 同一口径。完成后照常派审查。

**Files:**
- Create: `skills/nsfc-proposal/references/justification.md`、`research_content.md`、`foundation.md`、`abstract.md`、`length.md`
- Modify: `skills/nsfc-proposal/references/section_boundaries.md`（只留各章分工表与总述；「立项依据的结构」「研究内容的小标题」「研究内容的对照、基线与样本量」三节移入对应写法文件，文字不改）

**写法文件的统一结构：** `# <章名>的写法` → 「## 写什么」（必写与不写，与 `section_boundaries.md` 的表一致）→ 「## 怎么写」（结构、句式、示例）→ 「## 写完自查」（语义自查清单；确定性部分写明由哪条命令检查）。不写「输入」「信息不全时先提问」「preview/apply」「output_mode」等下级 skill 的单独用法；遇到缺失一律按 SKILL.md 规则 3 写占位。

**来源与取舍：**
- `justification.md`：取自立项依据写作器的 SKILL.md 第 1–6 条、`references/` 中科学问题、科学假设、理论创新、方法学术语、措辞边界、专业可读性、Tier2 审查（含「与 nsfc-proposal 协作时的追加检查」两项，改为常规自查）、`assets/templates/phrase_patterns.md`；`section_boundaries.md` 的「立项依据的结构」。统一为一套结构：重要性 → 国内外现状（按主题分条，小节标题写判断）→ 缺口 → 科学问题与假设（与科学论证逐字一致）→ 科学技术价值（`\subsubsection` 单列）→ 切入点。删去「默认理论创新导向」这一风格开关，保留其实质（问题驱动、方法不撑主线）。Tier2 审查改为「写完自查」的一部分，输出不再要求单独的 Markdown 报告，自查结论记入 `stages.md`。
- `research_content.md`：取自研究内容写作器 SKILL.md 第 2–7 条、「两阶段工作模式」「专家写作的核心特征」，`references/` 的子目标三件套、验证口径菜单、创新点相对坐标、年度计划模板、反模式、术语口径表；`section_boundaries.md` 的「研究内容的小标题」「研究内容的对照、基线与样本量」。子目标即科学论证的研究任务，个数以科学论证为准，不另定 3–4 个；篇幅以 `section_plan.yaml` 为准，删去「12–15 页」等与篇幅预算不一致的数字；`S1–S4` 只用于内部规划，由 `chapter_check.py` 拦截。
- `foundation.md`：取自研究基础写作器 SKILL.md 第 2–5 条与 Q1–Q5 中仍适用的部分、`references/dod_checklist.md`、`example_output.md`（示例中的 `XXX`、`[期刊名]` 一律改为 `【待补充：……】` 写法）。
- `abstract.md`：取自摘要 skill 的五句式、篇幅比例、压缩优先级、输出格式与 `references/title-rules.md`。超限压缩最多 3 轮，仍超限时保留当前版本、记入 `stages.md` 与报告（不问用户）。引号规则写成「只用中文弯引号“”」。数字限制写成「见 `config.yaml` 的 `abstract` 段」。
- `length.md`：取自篇幅对齐 skill 的「解读差距」「扩写/压缩」「复检闭环」与两个 references；命令改为 `length_check.py`；预算以 `config.yaml` 的 `length_standard` 为准；加一句「证据不足时篇幅下限只作提示，不用推测凑字（规则 6）」。

- [ ] **Step 1: 起草五份写法文件与 `section_boundaries.md` 的改动。**
- [ ] **Step 2: 自查**：每份文件里的数字、命令、文件名与 `config.yaml`、脚本参数一致；没有「询问用户」「请用户」「先提问」；没有兄弟 skill 名；没有中标书题材词；`grep -n "XXX\|\[请补充\|\[需补充" references/*.md` 只在「不要这样写」的反例里出现。
- [ ] **Step 3: 提交。** `docs(nsfc-proposal): 各章写法并入 references`

---

### Task 6: SKILL.md、README、CHANGELOG、版本与文档测试

由控制者执笔，完成后派审查。

**Files:**
- Modify: `skills/nsfc-proposal/SKILL.md`、`README.md`、`CHANGELOG.md`、`config.yaml`（版本）
- Modify: `tests/nsfc-proposal/test_np_skill_docs.py`
- Modify: 根 `CHANGELOG.md`；`docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md`（末尾追加「## 2026-10-12 融合」一节）

**SKILL.md 要求：**
- frontmatter 的 description 只写触发条件，覆盖：写、重写、续写国自然申请书正文的一章或多章（立项依据、研究内容、特色与创新、年度研究计划、研究基础、工作条件与风险应对）；修改或润色已写好的某一章；写中英文摘要与题目；检查或调整篇幅；为申请书检索并核实文献。不适用：预算、申请代码、模拟评审、质检、去 AI 腔、尚未确定方向的选题探索、与申请书无关的翻译或文献综述。不出现 `proposal/`、`.yaml`、`case.py`、`--`。
- 节序不变（`## 目标`、`## 流程`、`### 输入`、`### 执行步骤`、`### 输出`、`### 输出管理`、`### 校验`、`### 失败与恢复`、`## 约束`）。`## 目标` 下加「任务类型」表：写整份或多章（默认，第 0–8 步）、只改一章、只写摘要与题目、篇幅对齐，各写明走哪几步、读哪份写法。
- 删去 `SK` 变量与所有 `SK/...` 路径；第 0 步不再列「将调用的 skill」，改为说明将做哪几件事（检索文献、写哪几章、出图、检查）。
- 第 3 步：`search_runner.py run/validate` 换成 `literature.py pool`；`abstract-queries`、`enrich-abstracts` 换成 `literature.py` 同名子命令（去掉 `--offline`）；manifest `failed` 的去向改为 `pool` 退出码 1。
- 第 6 步：每章统一一个循环——`case.py brief`（立项依据、研究内容、研究基础三组）→ 读该章写法 → 把原文件复制到 `T/nsfc-proposal/output/before/` → 写入 → `chapter_check.py` → `case.py mark-written`。删去 `run.py` 的 `--task-root` 说明、`coach`、`check_project_outputs.py`、`run_checks.py` 的说明、`allowed_s_tokens` 改写兄弟 skill 配置的说明（改为本 skill 的 `chapter_checks.allowed_s_tokens`）。规则 7 改为：「各章写法中没有提问环节；遇到缺失按规则 3 处理。整个流程只有第 5 步向用户提问。」6.1、6.2 中「作为额外几行追加到信息表末尾」的结构要求，已写进写法文件的，删去追加的说法，只写「按 `references/justification.md` 写」等。
- 「校验」节：写作期间的检查改为 `chapter_check.py` 与 `abstract_check.py`；篇幅命令改为 `python3 S/scripts/length_check.py --input P --out-dir T/nsfc-length/output`，删去「这里 T 写绝对路径」那句。第 8 步建议的下一步删去 nsfc-length-aligner，改为「篇幅对齐（本 skill）」；nsfc-reviewers、nsfc-qc 保留。
- 九条规则、失败恢复表、各脚本退出码约定、第 1、2、4、5、7、8 步的现有内容保留；只改涉及兄弟 skill 的句子。失败恢复表把「某个写作 skill 失败」改为「某一章写作中断」，并加 `literature.py pool` 退出码 1 一行。
- 公共硬约束块逐字保留。

**其他：**
- `README.md`：说明融合后的结构（scripts、references 各管什么）与四种任务；删去对兄弟 skill 的依赖说明。
- `CHANGELOG.md`：新增 `## [0.2.0] - 2026-10-12`，分「新增」「变更」「移除」写清：新增四个脚本与五份写法；`to-info-form` 改为 `brief`；`section_plan.yaml` 条目由 `writer` 改为 `section`（旧条目仍可读）；不再读取兄弟 skill；段末 BAC 行。
- `config.yaml`：`skill_info.version` 改为 `0.2.0`。
- `test_np_skill_docs.py`：`test_referenced_files_exist` 改为断言 SKILL.md 中没有 `SK/`，`S/...` 与 `references/...` 引用都存在；`test_version_only_in_config` 改为 0.2.0；`test_changelog` 改为断言 `## [0.2.0] - 2026-10-12` 与 `## [0.1.0] - 2026-10-09` 都在；`RoundThreeDocsTest.test_motor_matched_control_rule`、`RoundFiveWritingDocsTest.test_subheadings_follow_each_study_type` 改读 `references/research_content.md`；`RoundFiveRetrievalDocsTest.test_bundles_are_wispaper_only` 改为断言 SKILL.md 含 `literature.py pool`、不含 `--provider-order`、`search_runner.py`；`test_abstracts_come_from_wispaper_offline` 改为断言含 `literature.py abstract-queries`、`literature.py enrich-abstracts`、`--name abstracts_1 --tool quick_search`。新增：`skills/nsfc-proposal/` 下除 `CHANGELOG.md` 外的文件不含兄弟 skill 目录名作为路径（`nsfc-justification-writer`、`nsfc-research-content-writer`、`nsfc-research-foundation-writer`、`nsfc-abstract`、`nsfc-length-aligner`、`research-literature-search`）；description 覆盖「摘要」「篇幅」「润色」三个触发词。

- [ ] **Step 1: 改文档测试，确认失败。**
- [ ] **Step 2: 改写 SKILL.md、README、CHANGELOG、config 版本、spec、根 CHANGELOG。**
- [ ] **Step 3: 跑测试命令，全部通过。**
- [ ] **Step 4: 提交。** `docs(nsfc-proposal): SKILL.md 改为自包含流程，版本 0.2.0`

---

### Task 7: 对照清单与隔离验证

**Files:**
- Create: `.superpowers/sdd/<本计划工作区>/fusion-checklist.md`（不提交）

- [ ] **Step 1: 对照清单。** 逐条列出旧 SKILL.md（`git show 8412a74:skills/nsfc-proposal/SKILL.md`）的九条规则、失败恢复表每一行、每个脚本的退出码约定，以及 6 个下级 skill SKILL.md 中被 nsfc-proposal 用到的每条要求，各标出在新文件中的位置（文件与小节）或「有意删去」及理由。未覆盖的条目补回对应文件，单独提交 `docs(nsfc-proposal): 补回融合时遗漏的规则`。
- [ ] **Step 2: 隔离验证。** 把 `skills/` 下 6 个下级 skill 目录临时移到系统临时目录，然后：跑测试命令中 `tests/nsfc-proposal`；在临时副本 `projects/NSFC_Young` 上依次运行 `case.py init`、`case.py validate`、`case.py render`、`case.py brief`（三组）、`chapter_check.py`（各章，允许 ERROR，不允许崩溃或「找不到」类错误）、`abstract_check.py -`（喂一份合格样例）、`length_check.py`、`literature.py pool`（喂一份夹具 host 文件）。全部完成后把 6 个目录移回原位，`git status` 确认没有变化。
- [ ] **Step 3: 记录结果。** 在 ledger 中写明清单条目数、补回条数、隔离验证每条命令的退出码。

---

## 执行后（不在任务内）

终审通过后由控制者推送到 `lauorie`，然后向申请人报告，并逐项询问：

1. web 应用是否改为只部署 nsfc-proposal 并重新部署（会重启服务，部署时页面停几分钟）；
2. 本机 `~/.claude/skills` 是否同步新版 nsfc-proposal，旧的 6 个副本删去还是保留；
3. 是否用 wispaper 与 WisImage 额度做一次完整的 fresh-3 运行验证融合版（可关闭出图以省额度）。
