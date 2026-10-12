# 文献检索与证据

第 3 步的细节。SKILL.md 列出命令的顺序；这里写每一项怎么做、各脚本的退出码怎么处理。

## 检索式

- 关键词检索式用英文，条数在 `config.yaml` 中 `literature.keyword_queries` 的范围内（`min` 至 `max` 条），写入 `T/nsfc-proposal/input/keyword_queries.json`（格式 `{"queries": [...]}`），并抄入 `P/proposal/literature_leads.md` 的「## 检索式」。
- 对每条 `gap`、`mechanism` 类论断和每条方法类论断写一个英文问句，写入 `T/nsfc-proposal/input/claim_queries_1.json`；超过 `literature.bundle_max_queries` 条时拆成 `claim_queries_2.json` 等，每个文件不超过这个条数。

## 方法类论断

研究方案依赖的任务范式、量表、模型和统计方法，同现状论断一起检索。每个方法在 `evidence_map.yaml` 中写成一条论断：`id` 取 `C<n>`，n 接在现有最大编号之后；`text` 以「方法：」开头；`sections` 填使用该方法的研究内容文件（如 `["研究内容"]`）。`case_validate.py` 不接受 `type: method`，所以 `type` 用最接近的 `background`，`support` 按证据记，没有证据时记 `unsupported`。正文引用它们，条件同规则 5。

## 申请人论文

- 申请人提供的已发表论文也在第 3 步处理。每篇写成一行 `rls.paper.v1` 记录，写入 `T/nsfc-proposal/output/applicant.jsonl`（字段同其他记录：`record_id`、`title`、`identifiers.doi` 或 `doi`、`year`；标题、DOI、年份取自申请人材料）。不写进 `selected.jsonl`：`select` 会整份重写那个文件。核对元数据时把它与检索记录合并，经 `bib_resolve.py` 进入 `.bib`。
- 每篇（或每组）申请人论文，在 `evidence_map.yaml` 中对应一条 `type: applicant_result`、`support: applicant_material` 的论断，`sections` 含立项依据；`evidence` 列该论文的 bibkey，`role: supporting`，`basis` 按实际读到的内容写（`fulltext` 或 `full_abstract`）。材料中有该论文的 PDF 并已由 `materials.py` 解析时，`basis` 写 `fulltext`，数字从解析结果（`primary` 指向的文件）中取。这样 6.1 引用它时满足规则 5 的 (b)。
- 这些论文的台账摘要可能为空。引用句含数字时会报 `no_abstract_for_numbers`：按 `consistency_fixes.md` 的办法改写，或只写申请人材料写明的数字。

## wispaper 检索

- `top_n` 默认取 `literature.quick_search_top_n` 与 `literature.deep_search_top_n`。
- 每条检索式的原始返回逐字存进 `T/nsfc-proposal/output/wispaper/raw/<名称>/`，再汇成 `T/nsfc-proposal/output/wispaper/<名称>_host.json`（`rls.host_results.v1`），汇总在 `<名称>_host.summary.json`。不要改写这些文件。
- 退出码 0：完成。4：到了单次时限，原样再跑同一条命令，已存档的不重查。1：有检索式失败，原样再跑一次；仍失败的检索式在 `stages.md` 记下，按 SKILL.md「失败与恢复」处理。3：未配置或凭据被拒，按「wispaper 不可用」处理。

## 文献池与阅读表

- 池写在 `T/nsfc-proposal/output/literature/<名称>/`：`candidates.jsonl` 是去重后的候选，`manifest.json` 记录各检索式的命中篇数。
- `pool` 退出码 0：池已建成；`manifest.json` 的 `status` 为 `partial_success` 时，其中列出没有结果的检索式。
- `pool` 退出码 1（`failed`）：这次检索的检索式全都没有结果，池不提供候选。论断问句换个写法写入新的 `claim_queries_<n>.json`（关键词池则换写法写入新的关键词检索式文件），按 SKILL.md 第 3 步第 4、5 项再检索一次，用新的名称建池；仍没有结果的，在 `stages.md` 记下，相关论断保持 `unsupported`。
- `pool` 退出码 2：参数或输入错误（host 文件不存在、格式不对），按提示修正。
- `digest` 为每个池写 `digest.md`：按检索式分组，每篇一行，列出 `record_id`、年份、题名、期刊、DOI、wispaper 相关度和摘要状态。挑文献读这张表。

## 选定文献

- 把每条论断选中的文献写成 `{论断编号: [引用, ...]}`，存为 `T/nsfc-proposal/input/claim_map.json`。引用写 `record_id`，或题名开头（不区分大小写，开头能唯一确定一篇即可）。
- `select` 全部唯一匹配时，写 `T/nsfc-proposal/output/selected.jsonl` 与 `selected_claim_map.json`，退出码 0。有引用没匹配或匹配到多篇时，什么都不写，列出问题和最接近的题名，退出码 1：改 `claim_map.json` 后重跑。

## 补摘要

关键词检索只返回摘要片段，片段不算完整摘要；按标题检索通常能拿到完整摘要。所以先列出缺完整摘要的记录标题，按标题检索，再把摘要填回记录。

- `wispaper_search.py` 的退出码：0 继续；4 原样重跑同一条命令；1 原样重跑一次，仍失败的标题不改写、不另建检索式文件，照常用已写出的 host 文件运行 `enrich-abstracts`，失败的标题保持缺摘要，在 `stages.md` 列出；3 按「wispaper 不可用」处理。
- `abstract-queries` 输出的 `queries` 为 0 时，不运行 `wispaper_search.py`，`enrich-abstracts` 去掉 `--host-results`。
- `enrich-abstracts` 只从 host 文件和 `--reuse` 取摘要，按 DOI 或标题核对是同一篇，不发网络请求。

### 补检与复用

- 汇总写在 `T/nsfc-proposal/output/selected_enriched.jsonl.summary.json`。`filled / attempted` 低于一半（`attempted` 为 0 时不算）时，背景类论断也可以写成论断问句检索，以拿到带完整摘要的记录：问句写入新的 `claim_queries_<n>.json`（n 接在已有文件之后），按第 4、5 项检索并建池，再回到选定与补摘要。在 `stages.md` 记录这一偏离及原因。
- 补检后重新选定、再次补全摘要时，编号递增（`abstract_queries_2.json`、`--name abstracts_2`），`abstract-queries` 与 `enrich-abstracts` 都加 `--reuse T/nsfc-proposal/output/selected_enriched.jsonl`（与 `--output` 相同即可，脚本先读旧文件再覆盖）：同一 `record_id` 上一次已补到的摘要直接沿用，不再检索。汇总的 `reused` 是沿用条数，不计入 `attempted`；判断「低于一半」时也不计入。不手工合并两次运行的结果。在 `stages.md` 记下每次的检索式条数、`filled`、`reused`。

## 核对元数据

- 申请人论文与检索记录先合并成一个文件，`bib_resolve` 只对它运行一次。每次运行都会覆盖 `T/nsfc-proposal/output/bib_resolve.json`；加 `--dry-run` 时只查询，不写 `.bib`、引用台账和线索文件，汇总写入同目录的 `bib_resolve.dryrun.json`，不覆盖前者。
- 检索记录排在前面：同一 DOI 出现两次时 `bib_resolve` 采用第一条，检索记录带有补全的摘要。没有申请人论文时，`cat` 只列 `selected_enriched.jsonl`。两个文件都要以换行结尾，否则拼接处两行相连，`bib_resolve` 会报该行不是合法 JSON 并以退出码 2 停下。
- `bib_resolve` 写入 `.bib` 的同时，把来源写进 `P/proposal/citation_ledger.jsonl`。候选引用键是输出中 `added` 条目的 bibkey，以及 `exists` 且在台账中有有效记录（`citation_ledger.py show` 能列出）的 bibkey；`exists` 但台账中没有记录的（`init` 之前就在 `.bib` 中、未经申请人确认的条目），不得引用。`unresolved` 条目已写入线索清单，正文不得引用。能否在正文引用，取决于规则 5 的三个条件。

## 按论断汇总证据

`evidence` 写 `T/nsfc-proposal/output/evidence_by_claim.md`：每条论断下列出选中的文献、bibkey（未入库的写明状态与原因）和台账中的完整摘要，段首给出可引用的篇数。读这份文件填写 `evidence_map.yaml` 的 `evidence` 与 `support`，不必再逐条查台账。
