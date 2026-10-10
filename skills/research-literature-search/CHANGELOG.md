# Changelog

## [Unreleased]

- 修复 legacy stem 空白归一化、字符串文献类型过滤、query_matches 输入变异、重复 provider 请求及零总量上限；补充回归测试。

## [1.1.0] - 2026-10-09

### Added（新增）
- `run` 新增 `--host-results`，接收宿主经 MCP 取得的 wispaper 结果（`rls.host_results.v1`），填入 `mcp` 检索源位置；从出版社链接提取 DOI；摘要片段不当作摘要。不传该参数时行为不变。
- `enrich-abstracts` 新增 `--reuse`：沿用前次输出中同一 `record_id` 已补到的摘要，不再请求；汇总新增 `reused` 与 `reuse_file`。
- `abstract-queries` 子命令；`enrich-abstracts` 新增 `--offline`、`--host-results`：按宿主检索结果补摘要，不发网络请求。

### Fixed（修复）
- `enrich-abstracts` 只采用与原记录 DOI 一致或标题相似度 ≥ 0.9 的命中摘要，避免填入他篇论文的摘要。
- `enrich-abstracts` 读取 OpenAlex 的 `abstract_inverted_index` 并拼回摘要（与 `candidate_schema` 共用 `abstract_from_inverted_index`）；采用 CrossRef 摘要前去掉 JATS 标签。（本版已随 OpenAlex 一并删除，见「Changed」）
- `enrich-abstracts` 遇 fetcher 报 429 或 5xx 时按退避重试（默认 2 次、2 秒，翻倍；CLI 选项 `--retries`、`--backoff-s`），其他异常照旧记录后换下一个来源。
- manifest 与 Search Log 的 `search_skill_version` 改为读取 `config.yaml:skill_info.version`（原为写死的 1.0.4），读不到时报错；README 删去版本号。
- `enrich-abstracts`：某个服务重试用尽后仍报 429 时，记为额度用尽，本次运行的后续记录不再请求它，`attempts` 记 `skipped_exhausted`，汇总新增 `exhausted_providers`；5xx 不计入，只有文字信息的错误只看第一个状态码；补全成功的记录，`abstract_provenance.attempts` 只计实际发出的请求。

### Changed（变更）
- 删除 OpenAlex 检索源、补摘要来源与 `openalex` 标识符；默认顺序为 mcp、Semantic Scholar、Crossref。旧 bundle 中的 `openalex_id` 字段不影响校验。
- `enrich-abstracts` 在固定来源之后，也按标题调用调用方注入的其他来源。
- manifest 的 `fallback_enabled` 只在检索顺序含宿主以外的来源时为真。

- 本分支未写 BAC 记录，经负责人同意。

## [1.0.4] - 2026-09-15

- 明确恢复拆分前 review 的 priority-fallback-topup 检索语义，并在 manifest/Search Log 固化策略与补召阈值，避免将 fallback 误读为全 provider union 召回。
- 增加按领域选择的 preprint profile；默认保留 preprint 作为发现线索，按领域调整排序偏好并在 manifest 中审计，不在搜索层武断删除或认证 preprint 结论。

## [1.0.3] - 2026-09-14

### Fixed

- OpenAlex 合法候选的 `primary_location.source` 为 `null` 时不再中断规范化；缺失 venue 保留为 `null` 并附加质量 warning。
- 增加嵌套 source 空值的回归覆盖，确保其余合法候选仍可生成并通过校验的 manifest bundle。

## [1.0.2] - 2026-09-02

### Fixed

- 将 manifest contract 常量移至唯一命名的 `rls_contract.py`，修复 review runner 进程内导入同名 `query_contract` 导致合法 bundle 无法验证的问题。

## [1.0.1] - 2026-09-02

### Fixed

- provider 返回 `null` 或混入非对象候选时，统一在输入边界跳过无效条目，避免规范化阶段因 `.get()` 崩溃。
- manifest、Search Log 和 dedupe map 记录跳过的空/非法条目数量；全部候选无效时返回 `no_valid_candidates`。
- 增加空记录、混合非法记录和全空 provider 结果的回归测试。

## [1.0.0] - 2026-09-02

### Added

- 新增独立 `research-literature-search` Skill 与 `rls.v1` manifest/candidate 契约。
- 提供 `run`、`enrich-abstracts`、`validate` 稳定命令。
- 支持 OpenAlex 主力、Semantic Scholar/Crossref 补充，以及 MCP/duckduckgo 显式 skipped 审计。
- 输出 raw、normalized、deduped、provenance、dedupe map 和兼容 Search Log。

### Fixed

- 对输出 scope 越界、非法 provider 返回值和不安全错误文本执行 fail-closed 处理，并补充 provider policy 指纹与语言/开放获取过滤。
- 去重合并保留两侧 identifiers；摘要补全成功时不再错误追加 `missing_abstract` 警告；bundle validator 严格校验 artifact hash、字节数和查询计数。
