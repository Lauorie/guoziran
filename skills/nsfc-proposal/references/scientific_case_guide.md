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
