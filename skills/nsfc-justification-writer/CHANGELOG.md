# Changelog

All notable changes to this skill will be documented in this file.

The version number is the single source of truth in `config.yaml` (`skill_info.version`).

## [Unreleased]

### Changed
- 将默认流程改为完全自动：自动选择/创建正文目标、执行 Tier1+Tier2、自主生成与修订正文、生成 diff、备份并写入；不再要求用户中途确认或审核。`preview` 默认自动写入，`--dry-run` 保留只读模式。
- 写作教练与 Tier2 将缺失信息转为最小保守假设和待核验项，自动继续执行，不生成“需要你补充/确认的问题”。
- 移除默认流程中的交互式信息表问答入口；信息表由宿主 AI 从现有材料自动提取和补齐。
- Tier2 架构改为宿主 AI 直接执行：新增 `references/tier2_semantic_review.md` 作为唯一审查规范；Python `diagnose` 仅负责 Tier1 确定性检查，不再通过 `AIIntegration.responder` 分块、缓存或生成 Tier2 fallback 结论，并移除 Tier2 专用 CLI 参数与 prompt 配置。
- Tier2 宿主 AI 语义检查改为主诊断流程的必选步骤：由当前宿主 AI 直接执行，不再因结构检查失败而静默跳过。
- 移除术语矩阵与固定内容维度检查链路及其独立 `terms` 命令；逻辑、术语、论证维度和专业可读性统一交由宿主 AI 按参考规范自主规划，Python 保留确定性校验和安全写入。
- 移除 Python 侧固定吹牛式表述词表与 `BoastfulExpressionAI` 运行时调用；措辞风险改由宿主 AI 按 `references/boastful_expression_guidelines.md` 进行语义复核，脚本继续负责引用、路径和结构命令等确定性检查。
- 增加面向大同行的专业可读性复核准则：`review`、`coach --stage polish` 和 Tier2 均要求识别长句层级、指代/缩写界定、抽象名词关系与段内衔接问题，并在不改变事实、限定、术语和 LaTeX 结构的前提下给出保真改法。
- Tier2 新增向后兼容的 `readability` 列表，聚合与 HTML 展示均保留旧字段；无 AI 回退继续输出确定性的可读性自检，不将其作为拒写条件。
- 新增 `references/professional_readability_guidelines.md`，同步更新 README、SKILL 和参考文档索引。
- 合并 README 与 `references/docs/` 中重复的教程、工作流和架构说明；删除不再需要的 `references/docs/` 文档目录。
- 按 2026-08-23 精简重构计划，将 Skill 契约改为语义写作优先：取消固定文件名、固定标题、开篇 300 字和四维度硬门槛。
- 默认输出 `preview`/unified diff 并自动写入；保留引用 key、白名单、备份与回滚保护，`--dry-run` 提供只读模式。
- 新增 `scripts/run.py preview` 与通用变更范围检查；`apply-section` 降级为 legacy 兼容入口。
- 精简配置与 AI 提示词，支持自定义文件名和标题宏。
- auto-test-skill A/B 轮优化：无唯一目标不再回退固定路径；统一 realpath/白名单校验；preview 对结构命令返回非零并提示缺失 bibkey；修复 coach/review/HTML 的旧四小节引导；Tier2 分块改为不依赖标题宏。
- 新增 `tests/test_semantic_boundaries.py`，覆盖目标解析、结构 diff、正文-only diff 和引用守护。

## [1.4.0] - 2026-10-09

### Fixed（修复）
- 提案可新增模板使用的标题命令（`guardrails.allowed_new_heading_commands`，默认 `subsubsection`）；删改已有标题仍被拒绝。
- `list-runs` 不再把任务工作区的 `input/output/log/cache` 当作运行记录。
- 新增顶层参数 `--task-root`；`diff`、`rollback`、`list-runs` 未指定时跨任务目录按 run_id 查找，修复跨分钟找不到前一步的问题。

### Added（新增）
- 与 nsfc-proposal 协作：读取 `proposal/` 下的信息表、篇幅与章节边界；Tier2 追加措辞强度与章节边界两项检查。
- 本分支未写 BAC 记录，经负责人同意。

## [1.0.0] - 2026-02-24

### Changed
- `config.yaml`：版本号 `0.7.9 → 1.0.0`，标记为正式稳定版本

## [0.7.9] - 2026-02-22

### Added
- 第三方约束（瘦身提质）诊断预警：预估页数（经验估算）、核心文献数（去重 cite keys）、开篇 300 字信号检查（启发式）

### Changed
- 配置兜底字数调整为 9000±800，并新增 `constraints.*` 约束区间（页数/字数/文献数量/开篇长度）
- `test-session` 将 pytest/python 缓存隔离到会话目录，保证测试中间产物可追溯且集中收口

## [0.7.8] - 2026-02-17

### Added
- 科学问题与科学假设写作要点参考文档（用于“瓶颈→约束→问题→假设”的闭环自检）

### Changed
- 信息表与写作教练：强化“科学问题≠研究目标”“假设不写验证方式”“瓶颈→约束映射”提示
- 信息表生成标题去年份化（避免时间敏感硬编码）
## Unreleased

- runs/cache 默认收敛到任务级 `.bensz-api/task-.../nsfc-justification-writer`。
