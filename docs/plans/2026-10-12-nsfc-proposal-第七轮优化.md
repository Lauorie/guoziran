# nsfc-proposal 第七轮优化计划

**来源：** 2026-10-12 用 skill-creator 评估融合版：fresh-3 完整运行记录，加四个单章任务新旧对比测试（`nsfc-proposal-eval/nsfc-proposal-workspace/iteration-1`）。申请人要求「按你建议的三处改，改完重跑这四个测试」，提速一项选了「连同脚本和精简一起做」。

**目标：**
1. 扩写不超页：页数上限优先于字数下限。
2. 没有科学论证时，「（未能提问）」的记录位置写明。
3. 单章任务提速：只读要用的写法；字数与段落没有增加时不编译。
4. 把 fresh-3 中每次手写的文献处理做成 `literature.py` 子命令：`digest`、`select`、`evidence`。
5. 新增 `power.py`：样本量与最小可检测效应，含整群设计；只用标准库。
6. SKILL.md 精简：第 3 步的细节移入 `references/literature.md`，第 7 步各类问题的处理移入 `references/consistency_fixes.md`。

## Global Constraints

- 分支 `nsfc-proposal`；推送只到 `lauorie`，终审后由控制者推送。
- 只用标准库、PyYAML、requests；`power.py` 不用 scipy、statsmodels。
- 脚本用 `Path(__file__).resolve()` 定位资产；文件读写显式 `encoding="utf-8"`；新脚本不超过 500 行。
- 不得出现兄弟 skill 的名字与路径（CHANGELOG 除外）；不出现 OpenAlex；不出现中标书、范例。
- 测试放 `tests/nsfc-proposal/`，文件名以 `test_np_` 开头，不联网，产物写系统临时目录。
- 测试命令（仓库根目录）：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider -W ignore::pytest.PytestConfigWarning tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/nsfc-research-foundation-writer tests/research-literature-search tests/research-literature-review tests/nsfc-ref-alignment`，基线 613 passed。
- 提交信息 `<type>(nsfc-proposal): <中文摘要>`，带 Co-Authored-By。提交前清掉 `__pycache__`、`.pytest_cache`。
- 版本 0.2.0 → 0.3.0（提问规则与本轮改动都是行为变化），CHANGELOG 新增 `## [0.3.0] - 2026-10-12`。

## Task A：文献辅助子命令（`literature.py`）

在 `skills/nsfc-proposal/scripts/literature.py` 加三个子命令；行数超限时拆出 `literature_views.py`。

- `digest --task-root T --name N [--name ...]`：读 `T/nsfc-proposal/output/literature/<N>/candidates.jsonl`，写同目录 `digest.md`，打印路径。按 `query_matches` 的第一条检索式分组（没有的归「（无检索式）」），每篇一行：`record_id | 年份 | 题名（截 160 字） | 期刊或会议（截 50 字） | doi | wispaper 相关度 | 摘要：完整/片段/无`。文件开头写池名、篇数、各检索式篇数。
- `select --task-root T --map <MAP.json>`：MAP 为 `{论断编号: [引用, ...]}`，引用写 `record_id`，或题名开头（不区分大小写、合并空白后前缀匹配）。在 `T/nsfc-proposal/output/literature/*/candidates.jsonl` 中查找。全部唯一匹配时，写 `T/nsfc-proposal/output/selected.jsonl`（去重，按首次出现排序，记录原样）与 `T/nsfc-proposal/output/selected_claim_map.json`（`{论断编号: [record_id, ...]}`），退出码 0。任何一条没匹配或匹配到多篇时，什么都不写，逐条列出问题和最接近的 3 个题名，退出码 1。参数或输入错误退出码 2。
- `evidence --task-root T --project-root P`：读 `selected_claim_map.json`、`T/nsfc-proposal/output/bib_resolve.json` 与 `P/proposal/citation_ledger.jsonl`，写 `T/nsfc-proposal/output/evidence_by_claim.md`，打印路径。每条论断下，每篇一段：bibkey（未入库的写「未入库：<状态与原因>」）、题名、年份、台账摘要全文（没有写「（无摘要）」）。段首给出这条论断可引用的篇数。缺输入文件退出码 2。

测试：`tests/nsfc-proposal/test_np_literature_views.py`。覆盖分组与摘要状态；前缀匹配唯一、重名报错、未匹配报错且不写文件；evidence 对 added、exists（台账有记录）、unresolved 三种状态的输出。

## Task B：`power.py`

`skills/nsfc-proposal/scripts/power.py`，只用 `statistics.NormalDist`。

- `props --p0 P0 --p1 P1 [--alpha 0.05] [--power 0.8] [--cluster-size M --icc ICC] [--r R]`：两比例每组人数 n = (zα√(2p̄q̄) + zβ√(p0q0+p1q1))² / (p1−p0)²；整群时设计效应 DE = 1 + (M−1)·ICC，调整后 n·DE·(1−R²)，每组群数取上整。
- `props-mde --p0 P0 --clusters K --cluster-size M --icc ICC [--r R] [--alpha] [--power]`：在 p0 之上以 0.001 步长找到所需群数不超过 K 的最小 p1，打印 p1 与相差的百分点。
- `means --d D [--ratio K] [--alpha] [--power] [--cluster-size M --icc ICC]`：两样本均值每组人数，正态近似加 Guenther 修正 zα²/4（d = 0.5 时每组 64）；整群同上。
- `means-mde --n1 N1 --n2 N2 [--alpha] [--power]`：最小可检测效应 d；n1 = n2 = 30 时约 0.74。
- 每条命令打印中文结论与所用公式；`--json` 输出机器可读结果。参数越界退出码 2。

测试：`tests/nsfc-proposal/test_np_power.py`。核对：0.60 对 0.70 每组 356 人；d = 0.5 每组 64 人；M = 40、ICC = 0.10 时 DE = 4.9，每组 314 人、8 个群；n1 = n2 = 30 时 d ≈ 0.74。

## Task C：文档（控制者执笔）

- **页数优先：** `references/length.md` 与 SKILL.md「篇幅对齐」「只改一章」。扩写或改写使篇幅增加时，全文不超过 `length_standard.pages.hard_max`；扩写前先编译记页数，按每页约 800 字估算可加的字数；到不了字数下限时停在页数允许处，按「提问」问申请人从哪一章腾篇幅；不能提问时停在页数上限，记「（未能提问）」。
- **记录位置：** 「提问」末条写明：有 `proposal/` 时记 `P/proposal/assumptions.md`；没有时记 `T/nsfc-proposal/output/assumptions.md`（同样的四节）。
- **单章提速：** 三种单章任务只读该章写法，九条规则适用时另读 `evidence_wording.md`；改动后该章字数或段落数增加时才编译查页数。
- **用新脚本：** 第 3 步改用 `digest`、`select`、`evidence`；科学论证指南第 9 步改用 `power.py`。
- **精简：** 第 3 步的退出码、补检、复用等细节移入 `references/literature.md`；第 7 步各类问题的处理移入 `references/consistency_fixes.md`。SKILL.md 保留命令顺序、要点与指向。文档测试钉住的句子留在 SKILL.md，包括 wispaper 第 4 项的 600000 与「原样重跑」、`literature.py pool`、`abstract-queries`、`enrich-abstracts`、`--name abstracts_1 --tool quick_search`、「| wispaper 不可用」一行。
- 版本 0.3.0；CHANGELOG；README 中的流程说明同步。

## 验证

1. 单元测试全绿。
2. 每个 Task 独立审查，最后整体审查一次。
3. 本机安装同步后，重跑四个单章测试（iteration-2，对照 iteration-1 的结果），再完整运行一次（fresh-4，同 fresh-3 的输入），对比耗时与产出。
