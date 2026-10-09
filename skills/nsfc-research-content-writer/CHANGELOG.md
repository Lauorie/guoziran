# Changelog — nsfc-research-content-writer

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

（暂无）

## [1.1.0] - 2026-10-09

### Fixed（修复）
- `check_project_outputs.py` 原先要求正文至少出现 3 个 S 编号，与 SKILL.md「编号不得进入正文」矛盾；改为检查编号泄漏，删除 `checks.subgoal_markers_min`。README 示例 Prompt 同步修正。

### Added（新增）
- 与 nsfc-proposal 协作：子目标取自科学论证的研究任务，篇幅与章节边界取自 `proposal/section_plan.yaml`。
- S 编号泄漏检查跳过 `checks.allowed_s_tokens` 中的专业写法（默认含 L5–S1、S100β、S1P、S1 受体等）和紧跟在字母、数字或连字符后的 S+数字，不再把解剖节段、标志物报成编号。
- 本分支未写 BAC 记录，经负责人同意。

## [1.0.0] - 2026-02-24

### Changed

- `config.yaml`：版本号 `0.2.3 → 1.0.0`，标记为正式稳定版本
