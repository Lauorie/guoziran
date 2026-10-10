# 建立科学论证

科学论证是各章共同的出发点。先把它写对，再动笔写正文。科学问题与假设的写法以 `../nsfc-justification-writer/references/scientific_question_guidelines.md` 和 `scientific_hypothesis_guidelines.md` 为准，本文不重复。

## 步骤

1. **重要性**：写清问题为什么值得做，填 `importance`。每条挂上论断编号（如 `C1`），论断同时写进 `evidence_map.yaml`。
2. **缺口**：写清已有研究缺什么，填 `gaps`（`G1`、`G2`…）。缺口要具体到「哪类研究、在什么条件下、没有回答什么」。
3. **科学问题**：先写 2–3 个候选，从国自然契合度、可行性、创新性、风险四方面比较，选定后填 `questions`；落选的候选和理由写进 `assumptions.md` 的「## AI 拟定项」。每个问题用疑问句，并在 `answers_gaps` 中写明回应哪些缺口。
4. **假设**：写一个可证伪的陈述句，填 `hypothesis`。`falsification.condition` 写「什么结果出现时假设不成立」，`metric` 写判定所用的指标。否定条件要考虑检验力：要求「每个分层都显著」通常过严，宜写成交互检验或方向一致。

   每个分假设各写一条可单独判定的否证条件。分假设写在 `predictions` 中，一条一个，否证条件写在该条末尾：「……；若……，这一分假设不成立」。核心假设的判定不得要求「几项同时失败」才算不成立：`falsification.condition` 写一个能单独判定的结果，通常是主要分析的结果。

   - 反例：研究一、二、三的结果都不支持时，核心假设不成立。（任何一项单独失败都推翻不了假设）
   - 正例：核心假设是「每周用药指导随访比一般健康宣教更能提高高血压患者的服药依从性」。`falsification.condition` 写「两组 6 个月服药依从率之差的 95% 置信区间包含 0 或方向相反」，所需样本量按第 9 步估算，保证这一判定有足够的检验力。分假设「效果在基线依从性较低的患者中更大」写成「……；若基线依从性与组别交互项的 95% 置信区间包含 0，这一分假设不成立」。
5. **研究对象**：分别写研究对象、目标人群、样本来源。样本来源与目标人群不同时（例如目标是筛查发现的结节，样本却是手术病例），在 `sample_vs_target_gap` 写明差异，在 `bias_handling` 写明怎么处理或讨论。
6. **术语**：标题中的每个专业术语都在 `terms` 中界定。申请人没给定义的，标 `source: ai_proposed`。
7. **研究任务**：每个任务对应一个科学问题。`baselines` 至少列一个最简单的对照，例如只用临床或形态学指标的模型；`confounders` 列出必须控制的混杂。
8. **可行性**：只录申请人提供的材料，标 `source: user_material`；没有的标 `source: missing`，正文会留占位。
9. **AI 拟定的内容**：申请人没提供而由你补上的（研究设计、合作单位、样本来源等），一律标 `source: ai_proposed`，并写进 `assumptions.md` 的「## AI 拟定项」。设计参数（环带宽度、纳入排除阈值、样本量、随访时长、主要终点与分组口径（哪些病理类型进入哪一组，哪些不进入主要分析）等）逐条写入，一个参数一行，不按类别合并。申请人没给例数时，按检验效能估算主要比较所需的最小样本量：写明效应量假设、α、检验效能与所用方法，写进对应 `tasks` 条目的 `validation`，并作为一条 AI 拟定项写进 `assumptions.md`。实际可得的例数仍写占位。正文写「至少需要 N 例」，不写「已有 N 例」。改动申请人写明的分组或终点，同样算 AI 拟定项，逐条写入。

   估算检验力时：

   - 效应量与自由度要和实际检验的模型一致。层级回归按新增的预测变量个数算分子自由度，效应量用新增部分的 f² = ΔR² / (1 − R²)（R² 取加入新变量后的模型），不用整个模型的 R²。例：3 个控制变量之后加入 2 个预测变量，分子自由度是 2，不是 5。
   - 以医院、社区、工作单位等群组为单位分组的研究，要计入聚类：用设计效应 1 + (m − 1) × ICC 放大按个体算出的样本量（m 为每个群组的人数），或按多层模型估算检验力；写明组内相关系数（ICC）的假设值及其来源。例：以社区卫生服务中心为单位随机分组，每个中心纳入 40 名患者，ICC 假设为 0.10，设计效应为 4.9；按个体算出每组 64 人（d = 0.5），计入聚类后每组约 314 人，即每组 8 个中心。
   - 写出最小可检测效应后，与所引文献报告的效应量比较。最小可检测效应更大时，写明这一比较的检验力不足，或增加样本，或把它降为次要分析。例：每组 30 人、α = 0.05、检验力 0.80 时，两独立样本 t 检验的最小可检测效应约为 d = 0.74；所引研究报告 d = 0.5，这一比较的检验力不足。

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

## 列表条目的写法

字段名和允许值以 `scripts/case_validate.py` 为准。内容用 `……` 代替，写作时替换。

```yaml
terms:
  - term: "……"
    definition: "……"
    source: user            # user | ai_proposed
importance:
  - text: "……"
    claim_ids: [C1]         # 对应 evidence_map.yaml 中的论断编号
gaps:
  - id: G1
    text: "……"
    claim_ids: [C2]
mainstream_routes:
  - name: "……"
    limitation: "……"
    claim_ids: [C3]
questions:
  - id: Q1
    text: "……？"            # 必须以问号结尾
    answers_gaps: [G1]      # 至少一个，且必须是已有缺口编号
tasks:
  - id: T1
    question: Q1            # 每个科学问题至少对应一个任务
    aim: "……"
    indicator: "……"
    baselines: ["……"]       # 至少一项必比基线
    confounders: ["……"]
    validation: "……"
    subtasks: ["……"]
    depends_on: []
constraints:
  - text: "……"
    source: user            # user | ai_proposed
feasibility:
  - text: "……"
    kind: preliminary       # paper | patent | data | platform | preliminary | team | collaborator | condition
    source: user_material   # user_material | missing
risks:
  - risk: "……"
    mitigation: "……"
    category: technical     # technical | schedule | resource
```

- `claim_ids` 只出现在 `importance`、`gaps`、`mainstream_routes`。
- `feasibility` 中 `source: missing` 的条目，在研究基础的 `placeholders` 里各留一条。
- 要写研究基础时，`risks` 至少 3 条。
