# Provider 指南

默认先用宿主检索结果（mcp，当前为 wispaper）；没有时依次用 Semantic Scholar、Crossref。MCP 与 duckduckgo 需要宿主能力，纯 Python runner 只记录 `skipped`，不把跳过算作成功。

每次 provider 尝试都写入 manifest `attempts[]`，至少包含 provider、query_id、status、结果数和错误/跳过原因。provider 适配器只返回原始命中，字段映射集中在 `normalize_papers.py`/`candidate_schema.py`，避免下游重复猜测字段。

未来新增 provider 或把策略改为无条件 union 时，应升级 provider policy/contract 并单独做候选集合回归；不要在兼容版本静默改变默认召回语义。
