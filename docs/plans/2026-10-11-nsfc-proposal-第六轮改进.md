# nsfc-proposal 第六轮改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修掉 fresh-2 验证运行暴露的六条问题：bib_resolve 把试验注册条目当成论文写进 `.bib`；书章与学位论文条目的类型和年份；研究基础写作 skill 的占位写法；立项依据写作 skill 的字数目标；只用 wispaper 时 manifest 的 fallback 标注；设计图的图标数量自检；research-literature-review 更新日志的一句不准确的话。

**Architecture:**
- **bib_resolve**：认 CrossRef 的条目类型。标题检索跳过非出版物（dataset 等）；DOI 查询得到非出版物时记为未核实；`dissertation` 写成学位论文条目；带书名与页码的 `other` 写成书章；年份缺失时取 `approved`。
- **nsfc-justification-writer**：`wordcount` 可读信息表，配置的默认目标对齐 nsfc-length-aligner 的立项依据预算。
- **其余**：都是一处小改动加一条测试。

**Tech Stack:** Python 3 标准库、PyYAML、requests；pytest（unittest 风格）。

**Spec:** `docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md`。本轮要求来自申请人 2026-10-11 在对话中的决定：「第六轮做吧，候选都改」。候选见评测目录 `funded-comparison.md`「fresh-2 暴露的问题（第六轮候选）」第 1–6 条。

依据（评测目录，未提交）：
- fresh-2 中一篇论文（Understanding soft commitment: Evidence from a field experiment on recycling）按标题匹配到 CrossRef 的 AEA 试验注册条目 `10.1257/rct.7758`。该条目 CrossRef 类型为 `dataset`，题名几乎相同，被写成 `@misc`。
- 一章书（`10.1002/9781119241072.ch24`）的 CrossRef 类型为 `other`，带 `container-title`（书名）、`page`、`publisher`，被写成 `@misc` 并把书名放进 `howpublished`。
- 一篇学位论文（`10.31390/gradschool_theses.5790`）的类型为 `dissertation`：`issued` 为 `[[null]]`，`approved` 为 2023-05-02，`degree` 为 `["Master of Science (MS)"]`，`institution` 为 `[{"name": "Louisiana State University and Agricultural and Mechanical College"}]`。条目没有年份，键成了 `rivettendreducing`。
- nsfc-justification-writer 的 `wordcount` 不读信息表时按 `config.yaml` 的 `word_count.target: 9000`、`tolerance: 800` 判定，提示扩写；第四轮已把立项依据预算改为 4500–10000（`skills/nsfc-length-aligner/config.yaml`）。
- nsfc-research-foundation-writer 的 SKILL.md 用 `[需补充：XXX]`、`[请补充：XXX]` 举例，`check_project_outputs.py` 也只认这种写法；nsfc-proposal 的一致性检查只认 `【待补充：……】`。
- `run --provider-order mcp` 的 manifest 写 `provider_policy.fallback_enabled: true`，实际不可能补充。
- fresh-2 的研究一设计图把实物卡片格画成 3 个分类箱（本市为四分类），自检清单没有数量一项。
- research-literature-review 的 CHANGELOG `[Unreleased]` 第 12 行说「记录内容不变」。实际上没有 DOI 的 OpenAlex 记录不再带 `openalex_id`，`record_id` 改为按标题生成。

## Global Constraints

- 分支 `nsfc-proposal`，远程 `lauorie`（git@github.com:Lauorie/guoziran.git）。各任务不推送，由控制者在终审后统一推送。
- 不新增必需的第三方依赖：只用标准库、PyYAML、requests。
- 脚本用 `Path(__file__).resolve()` 定位 skill 资产；文件读写显式 `encoding="utf-8"`。
- 仓库中不得出现本机用户目录的绝对路径和团队服务的域名。
- HTTP 请求不附带个人邮箱或身份信息（不加 mailto）。
- 国自然写作的 skill 与 research-literature-search 中不得出现 OpenAlex（文档测试已钉住）；检索只用 wispaper，CrossRef 只用于核对元数据。
- `.bib` 条目文本只由脚本按检索结果写入；不手写、不手改。
- 正文占位格式固定为 `【待补充：……】`。
- 示例不得回显对比基准（中标书）的题材：创造力、具身、物化、照样制作、近红外、综合实践活动课程、课时、班级等词不进 skill 文档与测试。tracked 文件不提中标书本身。
- 版本号不改动：nsfc-proposal 0.1.0、research-literature-search 1.1.0、nsfc-justification-writer 1.4.0、nsfc-research-foundation-writer 0.2.0；research-literature-review 记入 `[Unreleased]`。各 skill CHANGELOG 的新行放在该版本段落中，BAC 行仍在段落最后。根 `CHANGELOG.md` `[Unreleased]`：每项一句，依任务顺序接在「- 第五轮终审修复：」那一行之后、紧随其后的「- 本分支未写 BAC 记录，经负责人同意。」之前。
- 测试放 `tests/<skill名>/`，unittest 风格，文件名全仓唯一（带 skill 缩写前缀）。测试不联网，产物写系统临时目录。测试命令（仓库根目录）：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider -W ignore::pytest.PytestConfigWarning tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/nsfc-research-foundation-writer tests/research-literature-search tests/research-literature-review tests/nsfc-ref-alignment`。基线 452 passed、22 subtests passed。`skills/research-literature-review/tests` 保持 2 个既有失败，不新增。
- 新测试目录或新测试文件若被 `.gitignore` 忽略，照现有写法加白名单（见 `.gitignore` 中 `tests/nsfc-proposal` 的三行）。
- 提交信息 `<type>(<skill>): <中文摘要>`，末尾附 `Co-Authored-By: <实际完成提交的模型> <noreply@anthropic.com>`。每次提交前测试 0 failed；`find skills tests -name __pycache__ -o -name .pytest_cache` 无输出。不要用 `python3 -I`。
- 改文档一律按原文精确替换，断言命中次数；不重打中文引号，不改未要求改动的行。
- 文档风格：短句，少副词，不写宣传用语。
- 不改系统级 skill，不碰网页版（`nsfc-skill-web`）。

## Review Focus

1. CrossRef 按标题返回多条，第一条是题名几乎相同的 `dataset`，第二条是论文本身（`journal-article`）：取论文，不取 dataset（Task 1 测试）。
2. 已写进 `.bib` 的 dataset 条目（旧版写入）走 `bib_refresh.py`：`crossref_by_doi` 把它记为失败，不重写条目，提示走 drop 流程（Task 1 测试）。
3. `dissertation` 的 `degree` 为空或不含硕士字样：写成 `@phdthesis`；`institution` 为空时 `school` 取 `publisher`；`approved` 也为空时没有年份，不报错（Task 1 测试）。
4. `wordcount` 给了 `--info-form`，而信息表里没有字数说明：退回配置默认值，`source` 为 `config_default`（Task 2 测试）。
5. `run` 的 `--provider-order` 为 `mcp,semantic_scholar`：manifest 的 `fallback_enabled` 仍按 `--no-fallback` 是否给出记为真或假，只有全是 `mcp` 时记为假（Task 4 测试）。

---

### Task 1: bib_resolve 认 CrossRef 的条目类型

**Files:**
- Modify: `skills/nsfc-proposal/scripts/bib_resolve.py`
- Modify: `skills/nsfc-proposal/SKILL.md`（「失败与恢复」表加一行）
- Modify: `tests/nsfc-proposal/test_np_bib_resolve.py`
- Modify: `skills/nsfc-proposal/CHANGELOG.md`（0.1.0 `### Changed（变更）` 末尾，BAC 行之前）、根 `CHANGELOG.md`

**Interfaces:**
- Produces:
  - `NON_PUBLICATION_TYPES: frozenset[str]`
  - `WorkMeta.kind: str | None = None`（CrossRef 的 `type` 原值）
  - `crossref_by_doi` 对非出版物返回 `(None, "DOI <doi> 在 CrossRef 中是非出版物条目（类型 <type>），不作为文献")`；`bib_refresh.py` 经它自动得到同样的失败原因。
  - 新的条目类型 `phdthesis`、`mastersthesis`，用 `school` 字段。

- [ ] **Step 1: 写失败的测试**（`tests/nsfc-proposal/test_np_bib_resolve.py`；`ResolveTest` 与 `HelperTest` 中加）

```python
DATASET_ITEM = {
    "DOI": "10.5555/NSFC.TEST.REG1", "type": "dataset",
    "title": ["Unraveling Test Commitment: Evidence from a Field Experiment on Sorting"],
    "author": [{"family": "Tester", "given": "Alice"}], "publisher": "Test Registry",
    "container-title": ["Test Randomized Trials"], "issued": {"date-parts": [[2021, 7, 19]]},
}
PAPER_ITEM = dict(DATASET_ITEM, DOI="10.5555/NSFC.TEST.PAP1", type="journal-article",
                  title=["Unraveling Test Commitment: Evidence from a Field Experiment on Sorting"],
                  **{"container-title": ["Journal of Test Economics"]})

    # in ResolveTest
    def test_title_search_skips_dataset_and_takes_paper(self) -> None:
        session = FakeSession({CROSSREF_WORKS: FakeResponse(200, {"message": {"items": [DATASET_ITEM, PAPER_ITEM]}})})
        summary = self._run(session, {"record_id": "r9", "title": PAPER_ITEM["title"][0], "year": 2021})
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["doi"]), ("added", "10.5555/nsfc.test.pap1"))

    def test_title_search_with_only_dataset_is_unresolved(self) -> None:
        session = FakeSession({CROSSREF_WORKS: FakeResponse(200, {"message": {"items": [DATASET_ITEM]}})})
        summary = self._run(session, {"record_id": "r9", "title": DATASET_ITEM["title"][0], "year": 2021})
        outcome = summary["outcomes"][0]
        self.assertEqual(outcome["status"], "unresolved")
        self.assertIn("非出版物", outcome["reason"])
        self.assertNotIn("Unraveling", self.bib.read_text(encoding="utf-8"))

    def test_doi_pointing_to_dataset_is_unresolved(self) -> None:
        session = FakeSession({doi_url("10.5555/nsfc.test.reg1"): FakeResponse(200, {"message": DATASET_ITEM}),
                               CROSSREF_WORKS: FakeResponse(200, {"message": {"items": [DATASET_ITEM]}})})
        summary = self._run(session, {"record_id": "r9", "title": DATASET_ITEM["title"][0], "identifiers": {"doi": "10.5555/nsfc.test.reg1"}})
        self.assertEqual(summary["outcomes"][0]["status"], "unresolved")
        self.assertIn("类型 dataset", summary["outcomes"][0]["reason"])

    # in HelperTest
    def test_dissertation_becomes_thesis_with_school_and_approved_year(self) -> None:
        item = {"type": "dissertation", "title": ["Reducing Test Contamination Using an Information Nudge"],
                "author": [{"family": "Sample", "given": "Mimi"}], "publisher": "Test University Libraries",
                "degree": ["Master of Science (MS)"], "institution": [{"name": "Test State University"}],
                "issued": {"date-parts": [[None]]}, "approved": {"date-parts": [[2023, 5, 2]]}, "DOI": "10.5555/nsfc.test.th1"}
        meta = crossref_meta(item)
        self.assertEqual((meta.entry_type, meta.year, meta.publisher), ("mastersthesis", 2023, "Test State University"))
        entry = to_bibtex(meta, "sample2023reducing")
        self.assertIn("@mastersthesis{sample2023reducing,", entry)
        self.assertIn("school = {Test State University}", entry)
        self.assertNotIn("publisher", entry)
        self.assertNotIn("howpublished", entry)
        phd = crossref_meta(dict(item, degree=[], institution=[]))
        self.assertEqual((phd.entry_type, phd.publisher), ("phdthesis", "Test University Libraries"))
        self.assertIsNone(crossref_meta(dict(item, approved=None)).year)

    def test_other_with_book_and_pages_becomes_incollection(self) -> None:
        item = {"type": "other", "title": ["Yesterday's Test Habits"], "container-title": ["Test Psychology"],
                "page": "238-250", "publisher": "Test Press", "issued": {"date-parts": [[2018, 11]]},
                "author": [{"family": "Tester", "given": "Alice"}], "DOI": "10.5555/nsfc.test.ch24"}
        meta = crossref_meta(item)
        self.assertEqual(meta.entry_type, "incollection")
        entry = to_bibtex(meta, "tester2018yesterday")
        self.assertIn("booktitle = {Test Psychology}", entry)
        self.assertIn("publisher = {Test Press}", entry)
        self.assertNotIn("howpublished", entry)
        self.assertEqual(crossref_meta(dict(item, page=None)).entry_type, "misc")
```

（`DATASET_ITEM`、`PAPER_ITEM` 放在模块顶部常量区；方法放进对应的类。）在 `tests/nsfc-proposal/test_np_bib_refresh.py` 加一个测试：台账 DOI 指向的 CrossRef 条目类型为 `dataset` 时，`refresh` 记为 failed，原因含「非出版物」，`.bib` 与台账都不动（照该文件现有测试的写法构造路由）。运行这两个文件：新测试失败（红）。

- [ ] **Step 2: 实现**（`bib_resolve.py`）

```python
NON_PUBLICATION_TYPES = frozenset({
    "dataset", "database", "component", "peer-review", "grant", "journal", "journal-issue", "journal-volume",
    "proceedings", "proceedings-series", "book-series", "book-set", "report-series", "standard-series",
})
```

- `WorkMeta` 加 `kind: str | None = None`（放在最后，保持已有构造调用可用）。
- `_crossref_year` 的键序列末尾加 `"approved"`。
- `crossref_meta`：
  - `kind = item.get("type")`。
  - `dissertation`：`degree` 文本（列表拼接）含 `master`（不区分大小写）、`硕士`、`(MS)`、`(MA)` 时为 `mastersthesis`，否则 `phdthesis`。`publisher` 取 `institution[0].name`，没有时取 `publisher`。
  - `other`：有 `container-title` 且有 `page` 时为 `incollection`，否则 `misc`。
  - 其余类型照旧查 `CROSSREF_TYPES`。
  - 返回的 `WorkMeta` 带 `kind`。
- `to_bibtex`：
  - `phdthesis`、`mastersthesis` 没有 venue 字段；
  - 学位论文把 `publisher` 写成 `school = {…}`，不写 `publisher`；
  - 其他类型照旧。
- `crossref_by_doi`：取得 `meta` 后、比标题之前，`meta.kind in NON_PUBLICATION_TYPES` 时返回 `(None, f"DOI {doi} 在 CrossRef 中是非出版物条目（类型 {meta.kind}），不作为文献")`。
- `lookup` 的标题检索循环：类型在 `NON_PUBLICATION_TYPES` 中的条目跳过，不参与匹配。被跳过的条目若标题与年份都相符，记下它的类型。循环结束仍无匹配时：
  - 有这样的条目：失败原因写「CrossRef 标题相符的只有非出版物条目（类型 <type>，如试验注册、数据集），不作为文献」；
  - 没有：照旧写「CrossRef 无标题匹配的条目」。

- [ ] **Step 3: SKILL.md「失败与恢复」表**

在「| CrossRef 不可达 |」那一行之后加一行（整行，用精确插入）：

`| `bib_resolve` 未核实，原因含「非出版物条目」（试验注册、数据集等） | 不引用该条。要引用这项研究，按论文题名用 wispaper 检索它正式发表的版本，挑入 `selected.jsonl` 后只对这条记录重跑 `bib_resolve`；找不到时相关论断保持 `unsupported`，在 `stages.md` 记下。已写进 `.bib` 的这类条目（旧版写入）按规则 8 的 drop 流程处理，`bib_refresh.py` 会报同样的原因 |`

- [ ] **Step 4: 测试转绿**，全套 0 failed（报告增减明细）。

- [ ] **Step 5: CHANGELOG 与提交**
- `skills/nsfc-proposal/CHANGELOG.md`：「- `bib_resolve` 认 CrossRef 条目类型：标题检索跳过试验注册、数据集等非出版物，DOI 指向这类条目时记为未核实；学位论文写成 `@phdthesis`/`@mastersthesis`（`school`，年份缺失时取 `approved`）；带书名与页码的 `other` 写成书章。」
- 根 `CHANGELOG.md`：「- `nsfc-proposal` 0.1.0：`bib_resolve` 不再把试验注册、数据集当作文献；学位论文与书章条目类型更正。」
- 提交：`fix(nsfc-proposal): bib_resolve 认 CrossRef 条目类型，跳过试验注册与数据集`。

---

### Task 2: nsfc-justification-writer 的字数目标对齐篇幅预算

**Files:**
- Modify: `skills/nsfc-justification-writer/config.yaml`（`word_count.target`、`tolerance`）
- Modify: `skills/nsfc-justification-writer/scripts/run.py`（`wordcount` 加 `--info-form`）
- Modify: `skills/nsfc-justification-writer/scripts/core/hybrid_coordinator.py`（`word_count_status` 接收信息表路径）
- Modify: `skills/nsfc-justification-writer/SKILL.md` 或 `README.md` 中描述 `wordcount` 用法或默认字数的地方（`grep -n "wordcount\|9000" skills/nsfc-justification-writer/*.md`）
- Create: `tests/nsfc-justification-writer/test_njw_wordcount_target.py`
- Modify: `skills/nsfc-justification-writer/CHANGELOG.md`（1.4.0 段 `### Fixed（修复）` 末尾）、根 `CHANGELOG.md`

**Interfaces:**
- Produces: `wordcount --project-root P [--mode …] [--info-form FILE]`；`HybridCoordinator.word_count_status(*, project_root, mode=None, info_form_path=None)`。给了 `info_form_path` 时先读它，读不到再按现有的两个默认位置找。

- [ ] **Step 1: 写失败的测试** `tests/nsfc-justification-writer/test_njw_wordcount_target.py`（照 `test_njw_out_dir.py` 的方式用子进程调用 `run.py`，项目放系统临时目录，含 `extraTex/1.1.立项依据.tex`，正文 3 个汉字即可）：
  1. 不给 `--info-form`：输出 JSON 的 `target` 为 7250、`tolerance` 为 2750、`source` 为 `config_default`。
  2. `--info-form` 指向含「字数限制：4500–10000 字」的文件：`source` 为 `info_form`，`target` 为 7250，`tolerance` 为 2750。
  3. `--info-form` 指向不含字数说明的文件：`source` 为 `config_default`。
  运行：1、2 失败（红）。

- [ ] **Step 2: 实现**
  - `config.yaml`：`word_count.target: 7250`、`tolerance: 2750`，上面加一行注释「与 nsfc-length-aligner 的立项依据预算 4500–10000 字一致（中值 ± 半宽）」。
  - `run.py`：`p_wc.add_argument("--info-form", help="可选：已填写的信息表文件（markdown），其中的字数要求优先于配置")`；`cmd_wordcount` 把 `Path(args.info_form)`（给出时）传给 `word_count_status(info_form_path=…)`。
  - `hybrid_coordinator.py`：`word_count_status` 加参数 `info_form_path: Optional[Path] = None`，候选列表把它放在最前。
  - 文档中写「9000±800」或默认目标的地方同步为 7250±2750（4500–10000 字）；CHANGELOG 的历史行不改。

- [ ] **Step 3: 测试转绿**，全套 0 failed。

- [ ] **Step 4: CHANGELOG 与提交**
- `skills/nsfc-justification-writer/CHANGELOG.md` 1.4.0 `### Fixed（修复）` 末尾：「- `wordcount` 新增 `--info-form`；默认字数目标改为 7250±2750（4500–10000 字），与 nsfc-length-aligner 的立项依据预算一致。」
- 根 `CHANGELOG.md`：「- `nsfc-justification-writer` 1.4.0：`wordcount` 可读信息表，默认字数目标与立项依据预算一致。」
- 提交：`fix(nsfc-justification-writer): 字数目标对齐篇幅预算，wordcount 可读信息表`。

---

### Task 3: nsfc-research-foundation-writer 的占位写法统一为【待补充：……】

**Files:**
- Modify: `skills/nsfc-research-foundation-writer/SKILL.md`（第 86 行 `[需补充：XXX]`、第 107 行 `[请补充：XXX]`）
- Modify: `skills/nsfc-research-foundation-writer/scripts/check_project_outputs.py`（第 116–117 行的占位检测）
- Create: `tests/nsfc-research-foundation-writer/test_nrfw_placeholder_style.py`
- Modify: `skills/nsfc-research-foundation-writer/CHANGELOG.md`（0.2.0 段新增 `### Changed（变更）`，放在 BAC 行之前）、根 `CHANGELOG.md`

- [ ] **Step 1: 写失败的测试**：
  1. `SKILL.md` 不含 `[需补充：`、`[请补充：`，含 `【待补充：`。
  2. 照 `test_nrfw_risk_count.py` 的方式运行 `check_project_outputs.py`：研究基础正文含 `【待补充：项目组成员及分工】` 时，输出中有占位提示（提示文字含「【待补充：」）。正文含旧写法 `[请补充：X]` 时，输出提示改用【待补充：……】。
  运行：失败（红）。
- [ ] **Step 2: 实现**
  - `SKILL.md`：两处示例改为 `【待补充：XXX】`。
  - `check_project_outputs.py`：检测 `【待补充：`，提示「found placeholder markers like '【待补充：...】' in outputs; confirm this is intentional and consistent with provided info」。另检测旧写法 `[请补充：`、`[需补充：`，提示「use 【待补充：...】 instead of '[请补充：...]' / '[需补充：...]'」。
- [ ] **Step 3: 测试转绿**，全套 0 failed。
- [ ] **Step 4: CHANGELOG 与提交**
  - skill CHANGELOG：「- 占位写法统一为【待补充：……】，与 nsfc-proposal 的一致性检查一致；检查脚本提示旧写法。」
  - 根：「- `nsfc-research-foundation-writer` 0.2.0：占位写法统一为【待补充：……】。」
  - 提交：`fix(nsfc-research-foundation-writer): 占位写法统一为【待补充：……】`。

---

### Task 4: manifest 的 fallback 标注；research-literature-review 更新日志更正

**Files:**
- Modify: `skills/research-literature-search/scripts/search_runner.py`（`run_search` 中 `provider_policy` 的 `fallback_enabled`）
- Modify: `tests/research-literature-search/test_rls_host_abstracts.py`（`McpOnlyBundleTests` 加断言）或 `test_rls_host_results.py`
- Modify: `skills/research-literature-review/CHANGELOG.md`（`[Unreleased]` 第 12 行）
- Modify: `skills/research-literature-search/CHANGELOG.md`（1.1.0 `### Changed（变更）` 末尾）、根 `CHANGELOG.md`

- [ ] **Step 1: 写失败的测试**：
  1. `run_search(..., provider_order=["mcp"], fallback_enabled=True, ...)` 的 manifest 中 `provider_policy["fallback_enabled"]` 为 False。
  2. `provider_order=["mcp", "semantic_scholar"]`、`fallback_enabled=True` 时为 True。
  3. `provider_order=["mcp", "semantic_scholar"]`、`fallback_enabled=False` 时为 False。

  测试 2、3 用会抛错的 fetcher 也行，只看 manifest。运行：1 失败（红）。
- [ ] **Step 2: 实现**：`"fallback_enabled": fallback_enabled and any(p != "mcp" for p in order)`。
- [ ] **Step 3: research-literature-review CHANGELOG**：第 12 行把「返回先转成通用字段，记录内容不变，`candidates_raw.jsonl` 中不再保存 OpenAlex 原始返回。」改为「返回先转成通用字段再交给 research-literature-search。记录内容有两处变化：没有 DOI 的记录不再带 `openalex_id`，`record_id` 改为按标题生成；`candidates_raw.jsonl` 中不再保存 OpenAlex 原始返回。」（精确替换；从文件复制原文。）
- [ ] **Step 4: 测试转绿**，全套 0 failed。
- [ ] **Step 5: CHANGELOG 与提交**
  - research-literature-search CHANGELOG：「- manifest 的 `fallback_enabled` 只在检索顺序含宿主以外的来源时为真。」
  - 根：「- `research-literature-search` 1.1.0：只用宿主检索结果时 manifest 不再标注可补充；`research-literature-review` 更新日志更正。」
  - 提交：`fix(research-literature-search): 只用宿主结果时 manifest 不标注可补充；更正综述 skill 更新日志`。

---

### Task 5: 设计图自检加图标数量

**Files:**
- Modify: `skills/nsfc-proposal/references/figure_guide.md`（第 2 节 Brief、第 5 节设计图、第 6 节自检）
- Modify: `tests/nsfc-proposal/test_np_skill_docs.py`（`RoundFiveWritingDocsTest` 之后新增 `RoundSixFigureDocsTest`）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

- [ ] **Step 1: 写失败的测试**

```python
class RoundSixFigureDocsTest(unittest.TestCase):
    def test_figure_guide_checks_icon_counts(self) -> None:
        guide = (SKILL / "references" / "figure_guide.md").read_text(encoding="utf-8")
        self.assertIn("数量：", guide)
        self.assertIn("在提示词中写明个数", guide)
        self.assertIn("重复图标的个数与 Brief 一致", guide)
```

运行：失败（红）。

- [ ] **Step 2: 改 `figure_guide.md`**（精确替换或插入，从文件复制原文）
  - 第 2 节 Brief 的五项清单：在「- 可见文字清单：图上每一个标签的原文。」之后加一项：「- 数量：图中重复出现的对象（分类桶、组、条件、时间段等）各画几个，取自下面所列来源。」并把「每张图写五项」改为「每张图写六项」。
  - 第 5 节「- 条件示意中的实物、场景图片、卡片等刺激材料，画成线描图标……」这一条之后加一条：「- 重复出现的对象，在提示词中写明个数，例如「四个分类桶并排，依次标为……」。不写个数时，模型常画成三个或五个。」
  - 第 6 节自检清单，在「- 没有照片或写实渲染的图像（包括缩略图）……」之后加：「- 重复图标的个数与 Brief 一致（如分类桶、组数、时间轴上的阶段数）；不一致判为不合格，提示词中写明个数后重画。」
- [ ] **Step 3: 测试转绿**，全套 0 failed。
- [ ] **Step 4: CHANGELOG 与提交**
  - nsfc-proposal CHANGELOG：「- 设计图的 Brief 与提示词写明重复对象的个数，自检核对图标数量。」
  - 根：「- `nsfc-proposal` 0.1.0：设计图自检核对图标数量。」
  - 提交：`docs(nsfc-proposal): 设计图写明并核对重复图标的个数`。
