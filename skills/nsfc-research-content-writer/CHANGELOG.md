# Changelog — nsfc-research-content-writer

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

（暂无）

## [1.1.0] - 2026-10-09

### Fixed（修复）
- `check_project_outputs.py` 原先要求正文至少出现 3 个 S 编号，与 SKILL.md「编号不得进入正文」矛盾；改为检查编号泄漏，删除 `checks.subgoal_markers_min`。README 示例 Prompt 同步修正。
- 年度计划原先写死为三年，面上项目（4 年）按三年写也能通过检查。`config.yaml` 新增 `yearly_plan`，按项目类型中的关键词定研究期限（杰出青年、A类、重点项目、重大项目先于面上、地区、青年匹配，不用单独的「重点」；类型与关键词先做 NFKC 规范化并去掉空白再比较，「A 类」「Ａ类」同「A类」），匹配不到时用 `default_years` 并提示记入 assumptions.md；新增 `scripts/plan_years.py`。`check_project_outputs.py` 新增 `--years`、`--project-type`（二选一，都不给时按 3 年），核对第 1 至第 N 年（「第N年」「第 N 年」「第N年度」都算），出现第 N+1 年时报错；`run_checks.py` 透传这两个参数。SKILL.md、README、信息表、年度计划模板、输出骨架、检查清单与反模式同步改为按研究期限写。
- 风险词「首次」改为「首次提出」「首次发现」「国际首次」等 9 个短语，不再把「首次测试前」「首次到实验室」报成宣传用语。

### Added（新增）
- 与 nsfc-proposal 协作：子目标取自科学论证的研究任务，篇幅与章节边界取自 `proposal/section_plan.yaml`。
- S 编号泄漏检查跳过 `checks.allowed_s_tokens` 中的专业写法（默认含 L5–S1、S100β、S1P、S1 受体等）和紧跟在字母、数字或连字符后的 S+数字，不再把解剖节段、标志物报成编号。
- 本分支未写 BAC 记录，经负责人同意。

## [1.0.0] - 2026-02-24

### Changed

- `config.yaml`：版本号 `0.2.3 → 1.0.0`，标记为正式稳定版本
