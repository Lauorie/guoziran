# Changelog

All notable changes to this skill will be documented in this file.

The version number is the single source of truth in `config.yaml` (`skill_info.version`).

## [0.4.0] - 2026-10-13

依据：中文检索式试检（wispaper 能返回中文期刊论文，但多数没有期刊名与卷期页；知网 DOI 在 CrossRef 查不到）。申请人选择「按分层兜底做」。

### Added（新增）

- `scripts/bib_cn.py`：CrossRef 没有记录的中文文献，从出版方文章页的 `citation_*` 引文标签取期刊名、卷、期、页码、作者与摘要；文章页题名须与记录相符，缺期刊名不兜底；DOI 经 doi.org handle 接口确认已注册才写入；只访问公网主机名，页面最多读 2 MB。

### Changed（变更）

- `bib_resolve.py`：中文记录在 CrossRef 核对失败后走上述兜底，来源记为 `publisher_page`，逐条登记到 `assumptions.md` 的「## 待核实项」；中文条目的 bibkey 为 `cn<年份><题名哈希>`。`config.yaml` 新增 `literature.cn_publisher_fallback`。
- 引用台账记下文章页地址，摘要取自文章页时记 `abstract_source`；`bib_refresh.py` 拒绝刷新 `publisher_page` 条目。
- 检索式以英文为主，研究对象、政策背景或数据在国内的另写中文检索式；元数据规则改为「CrossRef，或中文文献的出版方文章页」。

## [0.3.0] - 2026-10-12

依据：fresh-3 完整运行的记录，以及四个单章任务的新旧对比测试（2026-10-12，skill-creator）。

### Added（新增）

- 「提问」一节：会改变正文内容又拿不准的事，用 AskUserQuestion 问申请人。开头集中问一次缺的材料；写作中的取舍（科学问题候选、设计参数、口径与文献冲突、章节与文件对不上、删改申请人原文）都问；用户说「全自动」时确认点不停，其余照样问；提问分三种情形：有 AskUserQuestion 时用它问；没有提问工具但有人在对话中时，把问题写在回复里，停下等下一轮；无人值守（后台运行，或用户说「无人值守」）时不停下，按保守做法写，把本该问的事标「（未能提问）」记入 AI 拟定项并列入报告（来源：申请人 2026-10-12 的要求）。
- `literature.py digest`（文献池阅读表）、`select`（按论断选文，生成 `selected.jsonl`）、`evidence`（按论断汇总入库文献与摘要）：取代每次运行手写的处理代码。
- `scripts/power.py`：两比例、两均值的样本量与最小可检测效应，含整群设计与个体随机设计、结局下降的情形；每组少于 10 人时按小样本加 1 人；只用标准库。
- `references/literature.md`（第 3 步的细节与退出码）、`references/consistency_fixes.md`（第 7 步各类问题的处理）。

### Changed（变更）

- 篇幅对齐：页数优先于字数下限，扩写后全文不超过 `pages.hard_max`；冲突时问申请人从哪里腾篇幅（来源：单章测试中扩写研究基础后全文 31 页）。
- 三种单章任务只读要用的写法；字数与段落没有增加时不编译。
- SKILL.md 第 3、7 步只留命令顺序与要点，细节移入参考资料。
- 日志时间用 `date` 取，不估填；写前先读原文件；研究内容写完编译一次看页数。
- 完整流程的压缩时机：研究内容写完后的编译只用来决定研究基础、工作条件按下限写，不再压缩已写的章节；收尾时超过 `pages.hard_max` 才压缩，压缩哪一章按「提问」问申请人，删去的内容记入 AI 拟定项（来源：fresh-4 在研究基础写完前把立项依据的引用从 73 篇删到 56 篇，最终 27 页，空出一页）。
- 第 4 步写明 `must_include` 能填的编号与字段名；`case.py validate` 报未知项时列出可填的字段（来源：fresh-3、fresh-4 都因填中文名或论断编号返工一次）。
- 没有科学论证时，「（未能提问）」等记录写在 `T/nsfc-proposal/output/assumptions.md`。
- 本分支未写 BAC 记录，经负责人同意。

## [0.2.0] - 2026-10-12

本版把 nsfc-proposal 与它原先调用的 6 个 skill（立项依据、研究内容、研究基础、摘要、篇幅、文献检索）融合成一个自包含的 skill。写作规则进 `references/`，确定性检查进 `scripts/`；不再读取或调用其他 skill 的文件（来源：申请人 2026-10-12 的要求）。

### Added（新增）

- 各章写法：`references/justification.md`（立项依据）、`research_content.md`（研究内容、特色与创新、年度研究计划）、`foundation.md`（研究基础、工作条件）、`abstract.md`（摘要与题目）、`length.md`（篇幅对齐）。规则冲突时按本 skill 统一：只在确认点提问，缺失写占位，措辞不超过证据。
- `scripts/literature.py`（与 `literature_records.py`）：`pool` 把 wispaper 的检索结果建成去重的文献池，退出码 1 表示检索式全都没有结果；`abstract-queries`、`enrich-abstracts` 只从 wispaper 结果补摘要，不发网络请求。
- `scripts/chapter_check.py`：按章检查内部编号、非标准占位、绝对化短语、年度标题与研究期限、风险条数、已具备与尚缺条件；`scripts/abstract_check.py`：摘要字数、引号、千分位、Markdown 标记、题目候选与主要研究领域。
- `scripts/length_check.py`：篇幅检查，`--out-dir` 必填并按当前目录解析，报告不再落进项目目录。
- `scripts/plan_years.py`：按项目类型定研究期限。
- 三种新任务：只改一章、只写摘要、篇幅对齐。
- `config.yaml` 新增 `yearly_plan`、`chapter_checks`、`abstract`、`length_standard`、`length_checker`；各章新增 `guide` 与 `brief`。

### Changed（变更）

- `case.py to-info-form --writer …` 改为 `case.py brief --section 立项依据|研究内容|研究基础`，输出写作要点。
- `section_plan.yaml` 的条目由 `writer` 改为 `section`（章节名）；只有 `writer` 的旧条目按文件名识别，照常可用。
- 第 6 步每章走同一个循环：写作要点 → 读写法 → 写前副本 → 写入 → `chapter_check.py` → 自查 → `mark-written`。规则 7 改为各章写法没有提问环节。
- 科学问题与假设的写法并入 `references/scientific_case_guide.md`；`section_boundaries.md` 只留各章分工表，各章细节移入写法文件。

### Fixed（修复）

- `bib_resolve` 写 `.bib` 时把标题、作者、期刊与出版者中的 U+2010、U+2011 连字符换成普通连字符，删去软连字符：Times New Roman 没有这两个字形，编译后缺字（来源：fresh-3 运行）。旧条目用 `bib_refresh.py` 刷新。

### Removed（移除）

- 对兄弟 skill 的全部依赖：`length_budget_source`、按路径加载的 `plan_years.py`、执行说明中的 `SK/` 路径。
- 不再使用立项依据写作器的 `run.py`（写作教练、AI responder、HTML 报告、示例推荐、版本回滚），由写法文件、写前副本与检查脚本取代。
- 检索流程中的 `--provider-order`、`--offline` 与 bundle `validate`：文献池只读 wispaper 结果，离线是唯一行为。
- 本分支未写 BAC 记录，经负责人同意。

## [0.1.0] - 2026-10-09

### Added（新增）

- 初始化技能，实现核心功能：建立科学论证、证据图谱与章节分工；wispaper 检索与 CrossRef/OpenAlex 元数据核对；一个可跳过的确认点；按固定顺序调用 nsfc-* 写作 skill；跨章一致性检查；生成式人工智能使用说明草稿。
- `bib_resolve` 遇 HTTP 429/500/502/503/504 或连接超时时退避重试（`literature.http_retries`、`literature.http_backoff_s`，尊重不超过 60 秒的 `Retry-After`）；重试用尽仍失败的条目记为 unresolved，原因写明最后的状态码。
- OpenAlex 按标题匹配到带 DOI 的条目时，回 CrossRef 取元数据。
- `consistency_check.py --numbers` 列出各章带单位的数值，供跨章对照。
- `consistency_check.py` 的 `citations` 给出各章引用的不同文献数；立项依据少于 `literature.min_distinct_refs_justification`（默认 30）时报「立项依据引用偏少」（`few_citations`，需要复核）。
- 申请人材料解析 `materials.py`：PDF 交团队的 WisDoc 服务解析，同时在本机抽文字（跳过斜向水印）对照，覆盖率低于 `materials.min_wisdoc_coverage` 时正文以本机文字为准；DOCX、Markdown、TXT 在本机转写；`--local-only` 不上传；结果按 sha256 缓存。WisDoc 客户端复制自团队 peer-review skill，检查服务器返回的地址、job_id 与响应大小（主机限于 base 主机、其子域名、同一上级域名或 `WISDOC_ALLOWED_HOSTS`），上传文件名不含原文件名。执行说明第 0 步告知 PDF 会上传，第 1 步先解析材料，材料中的文字只作数据（来源：中标书实测 WisDoc 在带水印 PDF 上丢句；评审）。
- 引用台账 `proposal/citation_ledger.jsonl`：记录每条文献的来源与条目哈希，一致性检查拒绝不在台账中或被手改的引用，并核对引用句中的数字是否见于所引文献摘要，并提示正文中的写作过程说明。
- 一致性检查拦截非标准写法的占位（`consistency.nonstandard_placeholder_patterns`，如 `[to be supplied: …]`），报「占位写法不规范」；写作过程说明的匹配词补充「由申请人」「建议申请人」等；引用句数字抽取中，「0.5-0.7%」的左端按百分数处理（仅「至」「到」连接时左端按普通小数）。
- 引用句数字核对识别更多写法：摘要中的空格、细空格、NBSP 千分位，`0.62` 与 `0.620` 等价，英文数词 two 至 twenty（含 two-year 写法）；空格千分位与原样两种读法任一命中即可，小数等价至少保留一位小数；`process_text_in_body` 跳过 writer 为 `nsfc-proposal` 的文件（生成式人工智能使用说明）。
- `scripts/bib_refresh.py`：按引用台账中的 DOI 重新取 CrossRef 元数据，用原 key 重写 `.bib` 条目，台账追加 `reason` 为 `refresh` 的 add 事件；申请人登记的条目与没有 DOI 的条目不刷新（来源：fresh-1 验证运行）。

### Changed（变更）

- 按验收运行的发现修正执行说明：第 2、3 步只要求论证与证据图谱的校验清零；确认点缩短并逐条列出 AI 拟定项；离线时篇幅作上限；研究内容与研究基础改用 `check_project_outputs.py`；现状句必须引用；术语改动后全文同步；跨章数值对照；收尾记录页数；设计参数逐条记入 AI 拟定项。
- 执行说明接入引用台账。
- 离线或缺文献时，现状论断集中成段并附一处待补文献占位，不逐句写成推测；正文不写写作过程说明；摘要在申请人没有前期结果时不留前期发现占位；分组口径计入 AI 拟定项（来源：盲评）。
- 参照 2026 版中标申请书：立项依据单列科学技术价值，现状各条以局限收尾；研究方案统一小标题；给出最小样本量；方法注明出处；研究框架图占位；收尾报告列出各章引用数（来源：申请人提供的中标书）。
- `init` 不再把 `.bib` 中已有的条目登记入账：只建空台账，并把这些条目列入警告与「待核实项」；`citation_ledger.py register-user` 改为 `--key K`（可重复）逐条登记，全部登记须显式加 `--all`；有台账时 `case.py validate` 只把台账记录为 `add` 的文献计入 `single_verified`、`multi_verified` 的篇数（`basis: full_abstract` 还要求台账摘要非空）；没有台账（`no_citation_ledger`）改为必须修正（来源：终审）。
- `consistency_check.py` 识别跨行的 `\cite`：逐行去注释后按文件拼接再查引用，`missing_bibkey`、台账检查、各章引用数与引用句数字核对都覆盖 key 换行写的情形；引用句可以跨行，按句末标点和空行切句（来源：终审）。
- 确认点的「我替你拟定」清单同时列出 `assumptions.md`「AI 拟定项」下的每一行（样本量、终点、分组口径等设计参数），一屏放不下时单独占第二屏（来源：终审）。
- 引用台账是只追加的 JSONL 事件日志，没有用 BSK：这是申请人选定的设计（借用 academic-literature 的做法），本机没有 BSK 源码可调用；设计文档 §11 注明了这一例外。
- `citation_ledger` 的 `add` 记录只在解析出的 DOI 与检索记录 DOI 规范化后相同、或记录本来没有 DOI 时保存记录的摘要，否则摘要记 null（来源：终审）。
- 执行说明：申请人论文的记录写入 `applicant.jsonl`，与检索记录合并后只运行一次 `bib_resolve`；篇幅检查加 `--out-dir`；检索式条数引用 `literature.keyword_queries`、`literature.bundle_max_queries`；S 编号误报的处理办法（来源：终审）。
- content-writer 信息表第 10 项改为「研究期限与分年硬约束」：年数由项目类型经 `SK/nsfc-research-content-writer/scripts/plan_years.py` 算出，不再写死三年；类型匹配不到时按 3 年，并提示在 assumptions.md 记一条 AI 拟定项（类型为空写「项目类型未写明」，非空写「项目类型「X」不在年数表中」；找不到 plan_years.py 时单独报错）。第 6.2 步的检查命令加 `--project-type`；`references/section_boundaries.md` 的年度研究计划一行同步。
- 研究框架图与各研究的设计图：新增 `scripts/figures.py render`，调用团队的生图服务 WisImage（`WISMODEL_IMAGE_URL`、`WISMODEL_API_KEY`、`DEPLOY_REGION`，环境变量或 `.env`），图写入 `P/figures/nsfc-proposal/<名称>.png`，提示词副本与 `index.json` 写入 `T/nsfc-proposal/output/figures/`；未配置时不发请求（退出码 3）；返回 200 但没有图片、不是 PNG/JPEG/WebP 或超过 `figures.max_image_bytes` 时报失败，不写文件；5xx 与网络错误重试 1 次，4xx 立即失败（402 记额度不足）；输出、日志与索引不含地址和 token。新增 `config.yaml` 的 `figures` 段与 `references/figure_guide.md`；第 6.2 步先出图再写研究内容，框架图占位只在出图失败或未配置时放；`.env` 读取提到 `scripts/envfile.py`，WisDoc 客户端与出图脚本共用。`consistency_check.py` 新增 `missing_figure_file`（图片文件不存在）：`\includegraphics` 指向的文件不在项目中时报错；`\includegraphics` 中的路径不再计入写作过程说明（来源：中标书有 6 张图，第一轮运行只有 1 处框架图占位）。评审修复：拒绝文字先全文遮盖 token 与网关地址（主机名不区分大小写）再截取；按返回格式存 `.png` 或 `.jpg`，WebP 等记 `unsupported_format`；新增 `figures.total_timeout_s`（每次请求取剩余时间，来不及重试时记 `timeout`）；token 或地区含非 ASCII 字符时按未配置处理；`\includegraphics*`、带空白或换行的写法也检查，图片检查移入 `scripts/figure_check.py`；第 0 步告知作图说明会发送到 WisImage；未配置时只放框架图一处占位。
- `bib_resolve.py --dry-run` 的汇总写入 `bib_resolve.dryrun.json`，不再覆盖正式运行的 `bib_resolve.json`；执行说明第 3 步第 7 项与「输出管理」同步。
- 写法规则：政策文件、课程标准、行业指南经发文机关官网核对文件名、发文机关与年份后在正文写明，不进 `.bib`，网址与核对日期记入 `literature_leads.md` 的「## 官方文件」（`case.py init` 的模板新增这一节），核对不到的按背景类论断处理（规则 5、`references/evidence_wording.md`）；`enrich-abstracts` 的 `filled / attempted` 低于一半或 `exhausted_providers` 不为空时，背景类论断也可写成论断问句检索，偏离记入 `stages.md`（第 3 步）；检验力按实际检验的模型算效应量与自由度，分组单位为班级或学校时计入聚类，最小可检测效应与文献效应量比较（`references/scientific_case_guide.md` 第 9 步、`references/section_boundaries.md`）；神经或生理信号设静息或低负荷基线，可能有非特异效应的操纵设对照条件（`references/section_boundaries.md`，第 6.2 步追加到信息表）；每个分假设各写一条可单独判定的否证条件，核心假设不以「几项同时失败」判定（`references/scientific_case_guide.md` 第 4 步）。
- wispaper 检索改由 `scripts/wispaper_search.py` 执行：传输层并入自 academic-literature，原始返回逐字存档，断点续查，汇成 rls.host_results.v1；不再用 MCP 工具做检索轮次（来源：funded-2 验证运行，280 条记录只能手抄）。
- 作图提示词的标签不加括号、引号、书名号，自检查清单外符号；动作不同的条件间比较神经或生理信号时，设动作匹配的对照；编译命令不带相对路径的 `--project-dir`（来源：funded-2 验证运行）。
- 过程说明词加入「正式申请书」「正式稿」「请申请人」；内文只有省略号的【待补充：……】视为格式说明，不计入占位（来源：funded-2 验证运行）。
- bib_resolve 按 CrossRef/OpenAlex 类型写条目：书章为 @incollection（booktitle、publisher），图书为 @book；其余 @misc 也带 publisher。参考文献样式不渲染 howpublished，书章此前没有出处（来源：funded-2 验证运行）。
- 信息表列出 section_plan 中的占位并要求逐字照抄；研究基础的缺失项不再自拟占位文字，同一缺失项只有一种写法（来源：funded-2 验证运行）。
- `nsfc-proposal` 0.1.0：wispaper 检索的 HTTP 正文与错误信息先脱敏再截断到 200 字；占位格式说明只在 AI 使用说明中豁免，其他文件的空占位报 `empty_placeholder`（需要复核）；执行说明补检索步骤的前台运行与超时重跑，第 0 步告知检索式会发送到 wispaper 服务，可选输入补 `WIS_MCP_URL`、`WIS_MCP_TOKEN`。
- `bib_resolve` 先解 HTML 实体（最多两层）再做 LaTeX 转义，标题比对同样先解实体；此前 CrossRef 期刊名中的 `&amp;` 会写成 `\&amp;`，排版显示「&amp;」（来源：fresh-1 验证运行）。
- 引用句数字核对把摘要中的 percent、per cent 读作 %（含「10–20 percent」「12 to 15 percent」这类区间），英文数字词先转成数字（「ten percent」读作 10%）；percentage points 是另一个量，不读作 %；此前这类写法会被报为数字不见于摘要（来源：fresh-1 验证运行）。
- 第 3 步第 6 项：再次补全摘要时用 `enrich-abstracts --reuse` 沿用前次结果，不手工合并（来源：fresh-1 验证运行）。
- `bib_resolve` 只查 CrossRef：删去 OpenAlex 兜底。CrossRef 查不到的记录写入线索清单，正文不引用。
- 第 3 步只用 wispaper：bundle 加 `--provider-order mcp`；补摘要改为按标题检索 wispaper（`abstract-queries`、`enrich-abstracts --offline`）；wispaper 不可用时停在第 3 步，不改用其他检索源。
- 研究内容的小标题按每项研究的类型选，一章中两类研究都有时各用各的；设计图中的实物与刺激材料画成线描图标，自检时照片或写实渲染判为不合格。
- 引用台账的说明不再提 OpenAlex；文档测试检查所有 nsfc-* skill 不含 OpenAlex。
- 第 3 步补上 wispaper 失败时的去向：bundle 全空、补摘要批次退出码 1、`use_wispaper` 为 false；README 写明 Crossref 无法核对的 DOI。
- `bib_resolve` 认 CrossRef 条目类型：标题检索跳过试验注册、数据集等非出版物，DOI 指向这类条目时记为未核实；学位论文写成 `@phdthesis`/`@mastersthesis`（`degree` 不含 master、硕士等字样时按博士论文写）（`school`，年份缺失时取 `approved`）；带书名与页码的 `other` 写成书章。
- 设计图的 Brief 与提示词写明重复对象的个数，自检核对图标数量。
- 失败与恢复表加一行：旧版 bensz-nsfc 包缺 `mastersthesis` 时更新包；非标准占位也认 `[需补充`；`bib_resolve` 标题检索取前 10 条。
- 第 0 步不再向用户说明检索式、材料和作图说明发往哪些服务；PDF 默认经 WisDoc 解析，申请人说材料不能离开本机时加 `--local-only`。
- 本分支未写 BAC 记录，经负责人同意。
