# Changelog

All notable changes to this skill will be documented in this file.

The version number is the single source of truth in `config.yaml` (`skill_info.version`).

## [0.1.0] - 2026-10-09

### Added（新增）

- 初始化技能，实现核心功能：建立科学论证、证据图谱与章节分工；wispaper 检索与 CrossRef/OpenAlex 元数据核对；一个可跳过的确认点；按固定顺序调用 nsfc-* 写作 skill；跨章一致性检查；生成式人工智能使用说明草稿。
- OpenAlex 按标题匹配到带 DOI 的条目时，回 CrossRef 取元数据。
- `consistency_check.py --numbers` 列出各章带单位的数值，供跨章对照。

### Changed（变更）

- 按验收运行的发现修正执行说明：第 2、3 步只要求论证与证据图谱的校验清零；确认点缩短并逐条列出 AI 拟定项；离线时篇幅作上限；研究内容与研究基础改用 `check_project_outputs.py`；现状句必须引用；术语改动后全文同步；跨章数值对照；收尾记录页数；设计参数逐条记入 AI 拟定项。
- 本分支未写 BAC 记录，经负责人同意。
