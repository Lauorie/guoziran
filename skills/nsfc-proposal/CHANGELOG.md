# Changelog

All notable changes to this skill will be documented in this file.

The version number is the single source of truth in `config.yaml` (`skill_info.version`).

## [0.1.0] - 2026-10-09

### Added（新增）

- 初始化技能，实现核心功能：建立科学论证、证据图谱与章节分工；wispaper 检索与 CrossRef/OpenAlex 元数据核对；一个可跳过的确认点；按固定顺序调用 nsfc-* 写作 skill；跨章一致性检查；生成式人工智能使用说明草稿。
- `bib_resolve` 遇 HTTP 429/500/502/503/504 或连接超时时退避重试（`literature.http_retries`、`literature.http_backoff_s`，尊重不超过 60 秒的 `Retry-After`）；重试用尽仍失败的条目记为 unresolved，原因写明最后的状态码。
- OpenAlex 按标题匹配到带 DOI 的条目时，回 CrossRef 取元数据。
- `consistency_check.py --numbers` 列出各章带单位的数值，供跨章对照。
- 引用台账 `proposal/citation_ledger.jsonl`：记录每条文献的来源与条目哈希，一致性检查拒绝不在台账中或被手改的引用，并核对引用句中的数字是否见于所引文献摘要，并提示正文中的写作过程说明。
- 一致性检查拦截非标准写法的占位（`consistency.nonstandard_placeholder_patterns`，如 `[to be supplied: …]`），报「占位写法不规范」；写作过程说明的匹配词补充「由申请人」「建议申请人」等；引用句数字抽取中，「0.5-0.7%」的左端按百分数处理（仅「至」「到」连接时左端按普通小数）。

### Changed（变更）

- 按验收运行的发现修正执行说明：第 2、3 步只要求论证与证据图谱的校验清零；确认点缩短并逐条列出 AI 拟定项；离线时篇幅作上限；研究内容与研究基础改用 `check_project_outputs.py`；现状句必须引用；术语改动后全文同步；跨章数值对照；收尾记录页数；设计参数逐条记入 AI 拟定项。
- 本分支未写 BAC 记录，经负责人同意。
