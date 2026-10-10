# nsfc-proposal 设计

- 日期：2026-10-09
- 分支：`nsfc-proposal`（本仓库的 fork 分支）
- 状态：待申请人审阅

## 1. 背景

2026-10-09，我们用同一份肺磨玻璃结节示例输入，对比了两套写作系统：独立仓库 nsfc-writer 和本仓库的 nsfc-justification-writer。两份立项依据转成同一格式后交给两名盲评评审。两人都判 nsfc-justification-writer 略好，总分 31:29 和 31:28（满分 35）。nsfc-writer 赢在研究设计：它先控制病灶大小和实性成分比例，再检验瘤周增量；它用浸润灶最大径做连续标签；它界定了标题中的「多模态」。它还在写正文前产出了科学论证和证据图谱。对比报告存放在仓库外的 `nsfc-compare-20261009/REPORT.md`。

问题出在结构上。本仓库的三个写作 skill（立项依据、研究内容、研究基础）各读一份信息表，彼此不共享。立项依据里的科学问题能否和研究内容拆出的任务对上，取决于申请人每次重填的内容。nsfc-writer 先建科学论证，再分章写作，各章同出一源。但它是独立仓库，没有 LaTeX 白名单写入、写前备份、Tier2 自审，也没有文献检索。

对比实验暴露了 7 个缺陷：

| 编号 | 缺陷 | 出现在 |
|---|---|---|
| D1 | 立项依据中约四分之一篇幅是研究方案 | nsfc-writer |
| D2 | 正文不提标题中的「多模态」 | justification-writer |
| D3 | 研究对象从「筛查发现的 GGN」换成手术病例，没有讨论偏倚 | 两者 |
| D4 | 没有以病灶大小、实性成分比例作必比基线 | justification-writer |
| D5 | 「前期基础」被略去，没有留占位 | 两者 |
| D6 | 写入申请人没有提供的「多中心」设计，没有记为假设 | justification-writer |
| D7 | 20 处「待补文献」写成 LaTeX 注释，PDF 中看不到 | justification-writer |

## 2. 目标与非目标

目标：

1. 新建 skill `nsfc-proposal`，作为写国自然正文的统一入口。
2. 写正文前建立三份共享文件：科学论证、证据图谱、章节分工。三个写作 skill 从这里取输入。
3. 文献经 wispaper 检索、元数据经 CrossRef 核对后才进入 `.bib`。正文措辞的强度受证据约束。借用 academic-literature 的引用台账做法，记录每条文献的来源。
4. D1–D7 在新流程的产出中不再出现。
5. 修复 nsfc-justification-writer 的 3 处 bug。

非目标：

- 网页版 `nsfc-skill-web` 接入新 skill。
- 修改 nsfc-reviewers、nsfc-qc、nsfc-length-aligner、nsfc-budget、nsfc-code、nsfc-humanization。
- 替代 research-idea 的选题探索。
- 向上游 `huangwb8/ChineseResearchLaTeX` 提交 PR。推送到 GitHub fork 需申请人另行确认。

## 3. 已定决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 上游策略 | fork，在分支 `nsfc-proposal` 上修改 | 写作 skill 要直接读共享文件，bug 要就地修 |
| 实现方式 | 写作 skill 原生读取共享文件；文件不存在时退回原信息表 | 措辞强度和章节分工能进入写作 skill 的自审；单独使用不受影响 |
| 确认点 | 一个，可跳过 | 科学问题定错，各章会沿错误方向写完；其余步骤保持 nsfc-* 的全自动 |
| 运行环境 | 本地代理（Claude Code、Codex） | 流程要调用 skill、脚本、MCP 和网络 |
| 文献来源 | 只用 wispaper；不可用时停在检索这一步。CrossRef 只用于核对元数据 | wispaper 召回切题，但 DOI、期刊、作者全名常缺，需另行补全 |
| 共享文件位置 | `{project_root}/proposal/` | 要跨会话保存；任务目录名每次运行都变 |

未采用的方案：

- 由调度器代填信息表、写作 skill 不改。措辞强度和章节分工进不了写作 skill 的自审，只能事后检查。
- 只给 nsfc-justification-writer 加「先建论证」阶段。研究内容和研究基础仍各写各的。
- 重写成一个大 skill。会丢掉白名单写入、备份和 Tier2 自审，也与上游彻底分叉。

## 4. 总体流程

```text
1 材料与项目画像
2 科学论证
3 文献与证据
4 章节分配
◆ 确认点
5 分章写作
6 跨章一致性检查
7 收尾
```

所有步骤共用一个任务目录 `./.bensz-api/task-{yyyymmdd-hhmm}-{简短描述}/`，遵循 `skills/WORKSPACE.md`。调用下游写作 skill 时显式传入这个任务目录。

### 4.1 材料与项目画像

- 输入：用户消息、上传材料、`project_root`（如 `projects/NSFC_Young`）。
- 动作：确定项目类型、标题、要写的章节、各章篇幅。篇幅默认取 `skills/nsfc-length-aligner/config.yaml` 的预算（立项依据 8000–10000 字，研究内容 12000–15000 字，研究基础 5000–6000 字），用户可改。
- 缺少 `project_root` 时停下，请用户指定。无人值守模式下直接报错退出。
- 创建任务目录前，向用户逐项说明将调用的 skill、各自的工作和调用顺序。任务目录只宣布一次，之后不更换；调用下游 skill 时显式传入。
- 输出：`scripts/case.py init` 在 `proposal/` 下建好骨架文件。

### 4.2 科学论证

- AI 按 `references/scientific_case_guide.md` 填写 `scientific_case.yaml`。科学问题和假设的写法，以 `nsfc-justification-writer/references/` 下的 `scientific_question_guidelines.md` 和 `scientific_hypothesis_guidelines.md` 为准，本 skill 不另写一份。
- 三项必填：研究对象与目标人群的差异及偏倚处理（针对 D3），标题中专业术语的界定（针对 D2），每个研究任务的必比基线（针对 D4）。
- 申请人没有提供、由 AI 拟定的内容，在字段中标 `source: ai_proposed`，同时写入 `assumptions.md`（针对 D6）。申请人没给例数时，按检验效能估算主要比较所需的最小样本量（写明效应量、α、检验效能、方法），同样作为 AI 拟定项；可得例数仍写占位。
- 论证中用到的每条论断，在这一步就写入 `evidence_map.yaml`：填 `id`、`text`、`type`、`sections`，`support` 一律先记为 `unsupported`，`evidence` 留空。第 3 步只补证据、重算 `support`，不新增编号；方法类论断除外，它们不被 `scientific_case.yaml` 引用，在第 3 步新增。这样 `scientific_case.yaml` 中的 `claim_ids` 从一开始就有着落。
- `case.py validate` 通过后才进入下一步。
- 用户想先系统探索选题时，`SKILL.md` 提示先运行 research-idea，再把它的报告导入本文件。本 skill 不调用 research-idea。

### 4.3 文献与证据

见第 6 节。研究方案借用的方法（范式、量表、模型、统计方法）与现状论断一起检索，写成 `type: background`、`text` 以「方法：」开头的论断，正文引用。申请人提供的已发表论文经 `bib_resolve.py` 入 `.bib`，在立项依据相关处引用。

### 4.4 章节分配

- AI 填写 `section_plan.yaml`：每个目标文件必写哪些编号、不写哪些内容、篇幅、必须留的占位。
- 各章默认的「不写」清单来自 `references/section_boundaries.md`。例如立项依据不写实验步骤、技术路线、样本量设计、年度安排（针对 D1）。
- 科学论证中 `source: missing` 的可行性条目，必须进入研究基础的占位清单（针对 D5）。
- 离线或缺文献时，缺口类论断写「尚不清楚」；背景类论断集中成段，段末放一处列出待补文献的可见占位，不逐句写成「可能」，也不写凭记忆的研究名称、作者、年份和具体数字。背景类判断在 `evidence_map.yaml` 中仍有对应论断，`support` 为 `unsupported`。
- 参照 2026 版中标申请书：立项依据用 `\subsubsection` 单列科学技术价值，现状各条以局限收尾，小节标题写判断；研究内容的每项用同一组小标题，开头放研究框架图占位。

### 4.5 确认点

展示 `scientific_case.md` 中的这些内容：科学问题、假设与否定条件、术语界定、研究对象差异、各章分工摘要、AI 拟定的条目。申请人回答：

| 回答 | 动作 |
|---|---|
| 同意 | `status: confirmed` |
| 修改：…… | 修改 YAML，`version` 加一，重新校验，再次展示 |
| 先继续 | `status: bypassed`，记入 `assumptions.md` |

配置项 `confirm.mode` 默认取 `ask`。取 `auto` 时，或用户请求中写明「全自动」「无人值守」时，流程不停，按「先继续」处理。

确认点只是 `scientific_case.yaml` 中的 `status` 字段，不是 BSK 的 Gate，不引入 State、Verifier 或事件账本（见第 11 节）。

### 4.6 分章写作

| 顺序 | 调用的 skill | 写入文件 |
|---|---|---|
| 1 | nsfc-justification-writer | `extraTex/1.1.立项依据.tex` |
| 2 | nsfc-research-content-writer | `extraTex/2.1.研究内容.tex`、`2.2.特色与创新.tex`、`2.3.年度研究计划.tex` |
| 3 | nsfc-research-foundation-writer | `extraTex/3.1.研究基础.tex`、`3.2.工作条件.tex` |
| 4 | nsfc-abstract | `NSFC-ABSTRACTS.md`（在 `project_root` 下） |

顺序固定。研究内容从立项依据的科学问题拆出任务；研究基础逐条对应研究内容的任务；摘要最后写。每写完一章，在 `section_plan.yaml` 中记下该章依据的科学论证版本。

### 4.7 跨章一致性检查

`scripts/consistency_check.py` 做确定性检查：

- 内部编号出现在正文中。只扫描 `proposal/` 文件里实际定义过的编号（如 `G1`、`Q1`、`T1`、`C1`），以及 research-content-writer 内部规划用的 `S1`–`S4`，作为独立词匹配。命中后由 AI 复核是否误报，例如医学稿中的「T1 加权」。
- LaTeX 注释里有「待补」「待核实」「TODO」等字样，即 PDF 中不可见的占位（针对 D7）。
- 正文中的可见占位与 `assumptions.md` 的占位清单不一致。
- `\cite` 的 key 不在 `.bib` 中。
- `terms` 中定义过的术语没有在任何一章出现。
- 某章依据的科学论证版本低于当前版本。
- 引用台账：`\cite` 的 key 不在台账中，或 `.bib` 条目与台账记录的哈希不符（手改）。
- 引用句中的数字不见于所引文献的台账摘要；所引文献没有摘要可核。
- 项目没有台账；正文中出现写作过程说明；占位写法不是 `【待补充：……】`。
- 立项依据引用的不同文献少于 `literature.min_distinct_refs_justification`（默认 30），提示复核；报告同时给出各章引用的不同文献数。

AI 做语义检查：各章的科学问题和假设表述一致；研究内容的任务与科学问题一一对应；研究基础覆盖每个任务的可行性。

发现问题时，回到对应的写作 skill 修改，最多 2 轮。仍不通过的问题写入收尾报告。

### 4.8 收尾

- 起草 `extraTex/4.5.生成式人工智能.tex`。依据是运行日志：AI 做了哪几步、产出了哪些文件、申请人确认了哪些、跳过了哪些。第一行写占位「【待补充：申请人核对本声明后删除此行】」，按 5.6 节规则列入占位清单。
- 模板 `main.tex` 没有引用 `extraTex/4.5.生成式人工智能.tex` 时（如 NSFC_Young），改写到 `proposal/ai_declaration.md`，并在 `assumptions.md` 记一条待核实项。
- 更新 `assumptions.md`。
- 向用户报告：写了哪些文件、各章引用的不同文献数、待核实项、占位位置、建议的下一步（编译、nsfc-length-aligner、nsfc-reviewers、nsfc-qc）。
- 用户要求时，调用 nsfc-reviewers 或 nsfc-qc。

## 5. 共享文件

### 5.1 位置

```text
{project_root}/
├── extraTex/*.tex                      正文，由各写作 skill 写入
├── references/<\bibliography 指向的 .bib>   核实过的文献追加到这里
└── proposal/
    ├── scientific_case.yaml            科学论证，程序读取的唯一来源
    ├── scientific_case.md              由 YAML 生成，供确认点展示
    ├── evidence_map.yaml               证据图谱
    ├── section_plan.yaml               章节分工
    ├── assumptions.md                  确认点状态、AI 拟定项、待核实项、占位清单
    ├── citation_ledger.jsonl           引用台账，只追加；记录每条文献的来源与条目哈希
    └── literature_leads.md             检索式和未核实的文献线索

./.bensz-api/task-…/nsfc-proposal/      wispaper 原始返回、检索 bundle、运行日志
```

`proposal/` 下的文件不被 `main.tex` 引用，不进 PDF，也不计入 nsfc-length-aligner 的篇幅统计。`.md` 由 `.yaml` 生成，不手改。

### 5.2 `scientific_case.yaml`

```yaml
version: 1                    # 每次修改加一
status: draft                 # draft | confirmed | bypassed
project:
  type: ""                    # 如 青年科学基金
  title: ""
  sections: []                # 本次要写的章节
research_object:
  object: ""
  target_population: ""
  sample_source: ""
  sample_vs_target_gap: ""    # 样本与目标人群的差异；无差异时写明「无」
  bias_handling: ""           # 偏倚的处理或讨论方式
  source: user                # user | ai_proposed
terms:                        # 标题中的专业术语必须在此界定
  - term: ""
    definition: ""
    source: user
importance:
  - text: ""
    claim_ids: []
gaps:
  - id: G1
    text: ""
    claim_ids: []
mainstream_routes:            # 主流路线与代表工作
  - name: ""
    limitation: ""
    claim_ids: []
questions:
  - id: Q1
    text: ""                  # 疑问句
    answers_gaps: [G1]
hypothesis:
  statement: ""               # 可证伪的陈述句
  rationale: []
  predictions: []
  falsification:
    condition: ""             # 什么结果出现时假设不成立
    metric: ""                # 判定所用的指标
entry_point: ""               # 与最近工作的差别
aim: ""                       # 总体目标
tasks:
  - id: T1
    question: Q1
    aim: ""
    indicator: ""             # 可判定的指标
    baselines: []             # 必比基线
    confounders: []           # 需控制的混杂
    validation: ""            # 数据来源与验证方式
    subtasks: []
    depends_on: []
constraints:                  # 资源、伦理、年度硬约束
  - text: ""
    source: user
feasibility:
  - kind: paper               # paper | patent | data | platform | preliminary | team | collaborator | condition
    text: ""
    source: user_material     # user_material | missing
risks:
  - category: technical       # technical | schedule | resource
    risk: ""
    mitigation: ""
```

`case.py validate` 的规则：

1. 每个 `questions[].text` 以问号结尾。
2. 每个科学问题至少回应一个缺口；`answers_gaps` 中的编号都存在。
3. `hypothesis.falsification.condition` 和 `metric` 非空。
4. 每个任务指向一个存在的科学问题；每个科学问题至少有一个任务。
5. 每个任务的 `baselines` 非空。
6. `research_object.sample_vs_target_gap` 非空。
7. `terms` 至少一条。
8. 所有 `claim_ids` 都能在 `evidence_map.yaml` 中找到。
9. `project.sections` 含研究基础时，`risks` 至少 3 条（nsfc-research-foundation-writer 的信息表要求）。

三个写作 skill 的信息表格式不同。`case.py to-info-form --writer <skill名>` 按各自格式生成：

| 写作 skill | 信息表字段 | 来自科学论证 |
|---|---|---|
| justification-writer | 研究对象、痛点与不足、科学问题、假设、切入点、方法概览、前期基础、主流路线 | `research_object`、`gaps`、`questions`、`hypothesis`、`entry_point`、`tasks`、`feasibility`、`mainstream_routes` |
| research-content-writer | 研究对象、问题与假说、总体目标、子目标（指标、对照、验证）、技术路线、任务分解、创新对照、年度约束、风险 | `research_object`、`questions`、`hypothesis`、`aim`、`tasks`、`mainstream_routes`、`constraints`、`risks` |
| research-foundation-writer | 前期论文与成果、预实验、团队与合作单位、条件与资源、风险 | `feasibility`、`risks` |

### 5.3 `evidence_map.yaml`

```yaml
version: 1
claims:
  - id: C1
    text: ""
    sections: []              # 用在哪些章
    type: background          # background | gap | mechanism | applicant_result
    support: unsupported      # multi_verified | single_verified | unsupported | applicant_material
    evidence:
      - ref: ""               # bibkey，或 lead:L3 表示未核实线索
        role: supporting      # supporting | counter
        basis: full_abstract  # fulltext | full_abstract
```

`support` 的判定规则和对应写法：

| support | 判定 | 正文写法 |
|---|---|---|
| `multi_verified` | 至少 2 条支持证据，`ref` 是 bibkey，`basis` 为全文或完整摘要 | 可写「多项研究表明」 |
| `single_verified` | 恰好 1 条这样的证据 | 只写「有研究报道」，不写成共识 |
| `unsupported` | 没有已核实证据 | 不写成事实。缺口类写「尚不清楚」；背景类集中成段并附待补文献占位；或删去（见 §4.4） |
| `applicant_material` | 来自申请人提供的材料 | 按材料原样写，不夸大 |

类型为 `applicant_result` 但没有申请人材料的论断，正文不写，只留占位。线索（`lead:`）和摘要片段都不能作为支持证据。

`support` 按不同的 bibkey 计数。同一个 bibkey 列两次，只算一篇。

### 5.4 `section_plan.yaml`

```yaml
version: 1
files:
  - file: extraTex/1.1.立项依据.tex
    writer: nsfc-justification-writer
    must_include: [G1, G2, Q1, hypothesis, entry_point]
    must_exclude: [实验步骤, 技术路线, 样本量设计, 年度安排]
    length: {min: 8000, max: 10000, unit: cjk_chars}
    placeholders: []
    written_with_case_version: null
```

### 5.5 `assumptions.md`

四个小节：确认点状态（时间、回答）；AI 拟定项（字段、内容、理由）；待核实项；占位清单（文件、所在段落、占位内容）。

### 5.6 两条硬规则

1. **占位在 PDF 中可见。** 格式为 `【待补充：……】`，写在正文里，不写成 LaTeX 注释。所有占位同步列入 `assumptions.md`。
2. **内部编号不进正文。** `Q1`、`G1`、`T1`、`C1` 等编号只出现在 `proposal/` 下的文件中。

## 6. 文献与证据

### 6.1 召回

- 由 AI 生成 5–25 条检索式，写入 `literature_leads.md`。
- 对每条检索式调用 `mcp__wis-scholar-search__quick_search`，`top_n` 默认 20。
- 对证据图谱中每条 `gap`、`mechanism` 类论断，用一个问句调用 `deep_search`，`top_n` 默认 10。返回标记为 perfect 的论文作为该论断的支持证据候选。
- 两个 `top_n` 和是否使用 wispaper（`literature.use_wispaper`，默认 `true`）写在 `config.yaml`。
- 原始返回保存到任务目录 `nsfc-proposal/output/wispaper/`。

2026-10-09 实测：`quick_search` 返回的 5 篇都切题，但 DOI 和期刊全为空，部分标题被截断，作者只有缩写，摘要是片段。`deep_search` 返回的 3 篇中有 2 篇带完整 DOI、期刊、作者和摘要。

### 6.2 交给 `research-literature-search`

`search_runner.py run` 对每条检索式按检索源优先级循环，`mcp` 排在第一位，但现在遇到它就记为「跳过」（`search_runner.py` 约第 254 行）。给 `run` 增加一个参数，把 wispaper 的结果填进这个位置：

```bash
python3 skills/research-literature-search/scripts/search_runner.py run \
  --topic <主题> --query-file <检索式> --output-dir <bundle 目录> \
  --host-results <按 query_id 归档的 wispaper 原始返回>
```

- 某条检索式在 `--host-results` 中有结果时，`mcp` 位置记为成功，来源写 `wispaper`；结果数不足时，按 `run` 原有的补充规则（约 70% 阈值）继续用 OpenAlex 等补足。没有结果时，仍记为「跳过」。
- 每条记录转为 `rls.paper.v1`。`quick_search` 的摘要片段不作为摘要：`abstract` 置空、`abstract_status` 为 `missing`，片段原文存入 `provenance.host_abstract_snippet`，并加 `abstract_snippet_only` 警告；之后由 `enrich-abstracts` 补全。
- 去重、manifest 和 `validate_bundle` 沿用 `run` 的现有逻辑，不另写一套。
- 不传 `--host-results` 时，`run` 的行为与改动前一致。

检索式分两个 bundle，以符合 `run` 每个 bundle 5–25 条检索式的限制：

| bundle | 内容 | 检索式数量 |
|---|---|---|
| 关键词 bundle | 6.1 节的关键词检索式，来自 `quick_search` | 5–25 条 |
| 论断 bundle | 每条 `gap`、`mechanism` 论断一个问句，来自 `deep_search` | 每个 bundle 不超过 25 条，用 `--min-queries 1`；超过 25 条时拆成多个 bundle |

### 6.3 补全摘要

要作为证据的论文，先用现有的 `enrich-abstracts` 补全摘要。补不到完整摘要的，不作为支持证据。

### 6.4 元数据补全：`scripts/bib_resolve.py`

1. **取 DOI**：用规范记录中的 DOI。wispaper 记录的 DOI 已由 research-literature-search 在导入时从链接中提取。
2. **有 DOI**：查询 CrossRef，取标题、全部作者、期刊、年、卷、期、页码、DOI。
3. **无 DOI**：在 CrossRef 按标题检索，取首条结果。规范化后的标题相似度达到 0.92 且年份相差不超过 1 年，才算匹配。标题被截断（含「…」）时，只比较已知的前缀。CrossRef 不匹配时，按同样规则查 OpenAlex。
4. **生成 bibkey**：第一作者姓 + 年份 + 标题首个实词，小写 ASCII。重名时加 a、b 后缀。
5. **写入 `.bib`**：目标文件取 `main.tex` 及其 `\input` 文件中 `\bibliography{}` 指向的文件。写入前备份；DOI 已存在的条目跳过。`--task-root` 必须是 `.bensz-api/task-*/` 目录，其父目录名为 `.bensz-api`。BibTeX 转义只剥离已知标记标签（i、b、em、strong、sub、sup、scp、span、mml:*），并在 title、author、journal 中转义 `\ { } ~ ^ & % $ # _`；doi 字段保持原样。
6. **未匹配的**：写入 `literature_leads.md`，标 `[unverified]`，正文不引用。
7. **请求规范**：请求中不附带个人邮箱或其他身份信息。
8. **写台账**：写入 `.bib` 的同时向 `proposal/citation_ledger.jsonl` 追加 `add` 事件；`bib_resolve` 不登记申请人提供的条目。

### 6.5 证据判断

AI 阅读完整摘要，填写 `evidence_map.yaml` 的 `evidence` 和 `support`。`case.py validate` 按 5.3 节的规则复核 `support` 是否与证据相符。

### 6.6 降级

| 情况 | 处理 |
|---|---|
| wispaper 不可用 | 用 `search_runner.py run` 的现有检索源 |
| CrossRef 和 OpenAlex 都不可达 | 不新增 `.bib` 条目；全部候选进入线索；相关论断记为 `unsupported` |
| 完全离线 | 只写检索式；所有文献类论断记为 `unsupported` |

## 7. 改动清单

### 7.1 新建 `skills/nsfc-proposal/`

| 文件 | 内容 |
|---|---|
| `SKILL.md` | 第 4 节的流程；确认点格式；wispaper 调用方式；结构见第 11 节 |
| `config.yaml` | `skill_info.version: 0.1.0`；`confirm.mode`；检索参数；写入白名单：`extraTex/4.5.生成式人工智能.tex`、`proposal/` 下的文件，以及运行时从 `main.tex` 解析出的 `\bibliography` 目标文件（只追加，写前备份） |
| `CHANGELOG.md`、`README.md` | 按本仓库各 skill 的惯例 |
| `references/scientific_case_guide.md` | 建科学论证的方法，改写自 nsfc-writer 的 `scientific_case_builder.md` |
| `references/evidence_wording.md` | 5.3 节的措辞强度规则 |
| `references/section_boundaries.md` | 各章必写和不写的内容 |
| `references/confirm_prompt.md` | 确认点的展示格式 |
| `assets/*.yaml` | 三个共享文件的空白模板 |
| `scripts/case.py` | `init`、`render`、`validate`、`to-info-form` |
| `scripts/bib_resolve.py` | 6.4 节 |
| `scripts/consistency_check.py` | 4.7 节的确定性检查 |

### 7.2 `research-literature-search`：1.0.4 → 1.1.0

`run` 子命令新增 `--host-results` 参数（6.2 节）。不传该参数时，所有子命令的行为不变。

### 7.3 三个写作 skill

| skill | 版本 | 改动 |
|---|---|---|
| nsfc-justification-writer | 1.3.0 → 1.4.0 | 接收 nsfc-proposal 生成的信息表（经已有的 `--info-form` 参数传入）；`proposal/` 存在时，Tier2 自审读取 `evidence_map.yaml` 和 `section_plan.yaml`，增加两项检查：措辞强度不超出证据图谱，正文不出现 `must_exclude` 的内容；篇幅取自 `section_plan.yaml`；修复第 8 节的 3 处 bug |
| nsfc-research-content-writer | 1.0.0 → 1.1.0 | 子目标取自 `tasks`：指标对应 `indicator`，对照对应 `baselines` 和 `confounders`，验证对应 `validation`；「特色与创新」取自 `entry_point` 和 `mainstream_routes` |
| nsfc-research-foundation-writer | 0.1.2 → 0.2.0 | 可行性和风险取自 `feasibility`、`risks`；`source: missing` 的条目写成可见占位，不略去 |

三者在 `proposal/` 不存在时保持现有行为。

信息表由 nsfc-proposal 一侧生成：调用写作 skill 前，先运行自己的 `case.py to-info-form`，把生成的文件路径交给写作 skill。justification-writer 经 `--info-form` 接收；另两个 skill 没有这个参数，在调用说明中给出文件路径。写作 skill 不调用 nsfc-proposal 的脚本，所以安装到 `~/.claude/skills/` 后路径变化也不受影响。写作 skill 只直接读取 `proposal/` 下的 `evidence_map.yaml` 和 `section_plan.yaml`。

nsfc-abstract 只在 `SKILL.md` 中补一句：存在科学论证时，科学问题和术语以它为准。版本 2.1.2 → 2.1.3。

### 7.4 文档

- `skills/README.md`：加入 nsfc-proposal，把推荐流程改为以它为入口。
- 每个改动过的 skill 更新自己的 `CHANGELOG.md`。
- 仓库根目录 `CHANGELOG.md` 的 `[Unreleased]` 记录本次新增与改动。仓库版本号和 Git tag 不动，由申请人决定。

## 8. 已知缺陷修复

| bug | 原因 | 修法 |
|---|---|---|
| 不允许新增 `\subsubsection` 标题 | `scripts/core/change_guard.py` 的 `STRUCTURE_COMMAND_RE` 把增删 `\subsubsection` 的行都判为结构变动 | 区分新增标题与删改已有结构。模板使用的标题命令允许新增，白名单写在 `config.yaml`；删改已有标题、增删 `\input`、`\usepackage` 等命令仍然拒绝 |
| `list-runs` 把 `input/output/log` 列为运行记录 | `scripts/core/versioning.py` 的 `list_runs` 把所有子目录都当作运行记录 | 只列出含运行记录文件的目录 |
| 任务目录名每分钟变一次 | `scripts/core/config_loader.py` 的 `get_runs_dir` 每次调用都用当前时间生成目录名；两条命令分属不同分钟时，`diff`、`rollback` 找不到前一步 | 所有子命令接受 `--task-root`，nsfc-proposal 总是显式传入。`diff`、`rollback`、`list-runs` 未传入时，在 `.bensz-api/task-*/nsfc-justification-writer/` 下按 run_id 查找。写入类命令未传入时保持现行为，并在输出中打印所用任务目录。不猜测「最近一次」的目录，以免两个任务混用一个目录 |
| research-content-writer 检查脚本要求正文出现 S 编号 | `check_project_outputs.py` 要求至少 3 个 S 编号，SKILL.md 却禁止编号进入正文 | 改为检查编号泄漏，删除 `subgoal_markers_min` |

每个 bug 单独提交，附回归测试：修复前失败，修复后通过。

对比实验时我曾把「默认篇幅 9000 字」也算作问题。它与 nsfc-length-aligner 的预算一致，不是 bug。

## 9. 错误处理

| 情况 | 处理 |
|---|---|
| `case.py validate` 不通过 | 不进入写作；列出不通过的规则，由 AI 修正后重试 |
| 某个写作 skill 失败 | 保留已写完的章节和日志；记录失败步骤；修复后从该步续跑 |
| 写完后科学论证又被修改 | 一致性检查标出依据旧版本的章节，提示重写 |
| 一致性检查 2 轮后仍不通过 | 不再重试，问题列入收尾报告 |
| LaTeX 编译失败 | 报告错误位置；不自动改动结构命令 |
| 写 `.bib` 时出错 | 从备份恢复，报告错误 |

## 10. 验收

### 10.1 单元测试与回归

测试放在 `tests/nsfc-proposal/`、`tests/nsfc-justification-writer/`、`tests/research-literature-search/`，与仓库现有的 `tests/research-idea/` 等目录同一布局；用 unittest 编写，可用 pytest 运行。运行缓存写入 `.bensz-api/`（`PYTHONPYCACHEPREFIX`，pytest 的 `cache_dir`），不留在 `tests/` 或源码目录。

| 测试对象 | 用例 |
|---|---|
| `case.py` | 5.2 节每条校验规则各有通过和不通过的用例；`to-info-form` 生成的三种信息表包含各写作 skill 的必填字段 |
| `bib_resolve.py` | 从 2026-10-09 实测的 3 个 wispaper 链接中提取 DOI；CrossRef 响应用模拟数据；联网实测 1 次；DOI 去重；写入前有备份 |
| `run --host-results` | 用一份真实的 wispaper 返回运行后，`validate_bundle` 通过，`mcp` 位置记为成功；结果不足时触发补充；不传参数时输出与改动前一致 |
| `consistency_check.py` | 能检出内部编号、不可见占位、旧版本章节 |
| 3 处 bug | 每处一个回归测试 |
| 改动过的 skill | 原有自检脚本（`validate_skill.py`、`run_checks.py` 等）全部通过 |
| 单独使用 | 项目中没有 `proposal/` 时，nsfc-justification-writer 的输出流程与改动前一致 |

### 10.2 端到端：肺结节示例，联网运行

运行在 `projects/NSFC_Young` 的副本中进行。副本放在仓库外，先清空模板自带的示例正文和示例文献，与对比实验的做法相同。仓库内的模板不被改动。

输入文件为 `<eval-dir>/input_full.md`，放在仓库外、对比实验目录旁边，实施阶段创建。它在对比实验的 `input.md` 基础上扩展：

- 写作范围从「只写立项依据」扩大到全部正文章节；篇幅取 nsfc-length-aligner 的默认预算，不再是 4000 字。
- 「前期基础」「团队与合作单位」「平台条件」逐项写明「无」，用来检验 D5：缺什么，就在正文中留可见占位。
- 其余内容（题目、关键词、研究对象、痛点、科学问题、假设）与 `input.md` 一致。

- 无人值守跑一次全流程，写出 1.1、2.1、2.2、2.3、3.1、3.2、摘要和 4.5。
- 交互模式跑一次，在确认点回答「修改：删掉科学问题二」。检查三件事：`version` 加一；`scientific_case.md` 重新生成；已写章节被标为依据旧版本。
- 把 `literature.use_wispaper` 设为 `false`，跑一次文献步骤，检查是否改走 OpenAlex。

通过标准：

| 检查项 | 方法 |
|---|---|
| LaTeX 编译通过，总页数不超过 30 | 项目自带的 `scripts/nsfc_build.py build --project-dir .` |
| 各章篇幅在 `section_plan.yaml` 的范围内 | nsfc-length-aligner |
| 正文没有内部编号；所有占位可见，并列入 `assumptions.md` | `consistency_check.py` |
| 每个 `\cite` 的 key 都在 `.bib` 中 | `consistency_check.py` 和 nsfc-ref-alignment |
| 新增 `.bib` 条目的元数据与 CrossRef 一致，引用句与论文摘要相符 | 由 Claude 抽查 10 条，0 错；逐条核对记录交申请人复核 |
| 立项依据与研究内容中的科学问题、假设一致 | `consistency_check.py` 和 AI 检查 |

### 10.3 缺陷复查

逐条检查 D1–D7。新流程的产出中，7 项都不得出现。哪一项仍在，就修改对应的指南并重跑。

### 10.4 盲评对比

- 对照组：本仓库的现状，即 `main` 分支上未改动的三个写作 skill。用 `git worktree` 把 `main` 检出到仓库外的目录，从那里调用。输入同为 `input_full.md`，三个 skill 各自独立运行。
- 实验组：nsfc-proposal。
- 两组都离线运行、不提供文献，让差别只来自科学论证和章节分工。文献的作用由 10.2 节单独检验。
- 每组运行 2 次。
- 评审方法沿用对比实验：先统一格式，再随机标为 A、B；两名评审读整份正文，阅读顺序相反。评分在原有 7 个维度之外，增加「跨章一致性」。
- 通过标准：实验组的总分、「跨章一致性」「可用程度」都不低于对照组；「对申请人材料的忠实度」不下降。

## 11. 实现约束

来源：本仓库 `AGENTS.md`，以及 2026-10-09 查阅的 `huangwb8/skills` 的 `AGENTS.md`（本仓库要求开发 Skill 前对齐该文件）。

- **SKILL.md 结构**：frontmatter 含 `name`、`description`、`metadata.author`。`description` 只写用途和触发条件，不写文件名、参数和默认值。正文按「目标 → 流程（输入、执行步骤、输出、输出管理、校验、失败与恢复）→ 约束」组织。nsfc-proposal 不声明 State、Verifier 或 Gate，所以不设「控制」一节。
- **公共约束**：「约束」一节逐字复制 `docs/templates/skill-common-constraints.md` 的公共块，块后加「Skill 专属约束」。本仓库没有上游的 `check_skill_structure.py` 和 `sync_skill_constraints.py`，改由单元测试比对公共块与模板是否一致。
- **不用 BSK**：本机没有安装 `bensz_skill_kernel`；本任务也不需要状态机或验证器。确认点、版本号和运行日志都用普通文件表达，不另建事件账本或哈希链。例外：引用台账 `proposal/citation_ledger.jsonl`（5.1 节、6.4 节第 8 条）是只追加的事件日志，记录条目哈希。这是申请人选定的设计，借用 academic-literature 的做法；本机没有 BSK 源码可调用，所以用独立的 JSONL 文件实现。
- **脚本**：用 `Path(__file__).resolve()` 定位 skill 自身的资产，不依赖当前工作目录；文件读写显式指定 `encoding="utf-8"`；阈值和路径放进 `config.yaml`；用户给出的路径必须限制在 `project_root` 内。
- **分工**：确定性工作（校验、DOI 提取、去重、编号扫描）放进脚本；语义判断（证据是否支持论断、各章是否一致）交给 AI。
- **版本**：只改各 skill 的 `config.yaml:skill_info.version`。新 skill 的 `CHANGELOG.md` 以 `[0.1.0]` 和「初始化技能，实现核心功能」开头。
- **计划文档**：实施计划按本仓库约定，存放在 `docs/plans/2026-10-09-nsfc-proposal-实施计划.md`。
- **README**：上游规范要求用 `write-readme` 和 `which-model` 两个 skill 生成 README，本机没有这两个 skill，改为参照本仓库现有 skill 的 README 手写。

## 12. 局限与风险

- 评审由模型扮演，不是领域专家。课题只有肺结节一个。
- 一次全流程运行约需 40–60 分钟。10.4 节的 4 次运行可以并行。
- wispaper 只在配置了该 MCP 的环境中可用；其他环境走降级路径。
- 标题匹配可能误配。阈值和年份校验降低误配，10.2 节的抽查兜底；抽查由模型完成，申请人复核其记录。
- fork 后合并上游更新会有冲突。对写作 skill 的改动限于 `SKILL.md` 的新增段落和第 8 节的 3 个脚本文件，以减少冲突面。
- `projects/NSFC_Young/README.md` 写的编译入口是 `code/nsfc_build.py`，实际文件在 `scripts/nsfc_build.py`。验收按实际路径执行，此处文档不一致不在本次修复范围。

## 13. 申请人的决定

| 事项 | 背景 | 决定（2026-10-09） |
|---|---|---|
| BAC 贡献记录 | 本仓库要求维护任务使用 `bac` 记录，只有项目负责人明确要求才可关闭。本机没有 `bac` | fork 负责人明确豁免：本分支不写 BAC 记录。各 `CHANGELOG.md` 和交付说明写明「本分支未写 BAC 记录，经负责人同意」 |
| `metadata.author` | 上游规范写 `Bensz Conan`。nsfc-proposal 是 fork 中的新 skill | 新 skill 写 `Lauorie`（本地 git 用户名）；改动的现有 skill 保持原作者 |
| 远程推送 | 分支只在本地 | 待定：实施完成、验收通过后再决定是否推送到 GitHub fork |

## 14. 后续工作（不在本次范围）

- 网页版 `nsfc-skill-web` 接入 nsfc-proposal 的科学论证步骤。
- 把 nsfc-proposal 安装到 `~/.claude/skills/`，在本仓库以外也能触发。
- 申请人同意后，推送分支到 GitHub fork，或向上游提 PR。
- 申请人同意后，按 `bensz-collect-bugs` 的规范，向上游报告 3 处 bug。
