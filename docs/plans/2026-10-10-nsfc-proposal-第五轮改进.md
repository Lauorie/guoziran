# nsfc-proposal 第五轮改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** nsfc-proposal 的检索只用 wispaper，元数据核对只用 CrossRef：去掉流程中所有 OpenAlex（及随之而来的 Semantic Scholar）请求；补摘要改由 wispaper 按标题检索。另做 fresh-1 候选第 5、6 条：数据驱动研究的小标题、设计图中的照片。

**Architecture:** 四处改动。`bib_resolve.py` 删去 OpenAlex 兜底，只查 CrossRef。research-literature-search 的 `enrich-abstracts` 新增 `--offline` 与 `--host-results`：只从 wispaper 的检索结果取摘要，不发网络请求；新增 `abstract-queries` 子命令，列出缺完整摘要的记录标题，供 `wispaper_search.py` 按标题检索。nsfc-proposal 的 SKILL.md 第 3 步改用这三条命令，bundle 加 `--provider-order mcp`，wispaper 不可用时停下而不是换检索源。第 5、6 条只改文档。

**Tech Stack:** Python 3 标准库、PyYAML、requests；pytest（unittest 风格）。

**Spec:** `docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md`。本轮要求来自申请人 2026-10-10 在对话中的决定：
- 「把 OpenAlex 去掉！」，理由是「我们整个检索都是搭建在 wispaper 上的」。
- 「第 5、6 条也做」：评测目录 `funded-comparison.md`「fresh-1 暴露的问题」第 5、6 条。

依据（评测目录，未提交）：
- fresh-1 的 130 条 `.bib` 条目全部由 CrossRef 核对，OpenAlex 一条也没有贡献（当日额度已用完，返回 429）。
- fresh-1 第一次补摘要 18 条中，多数来自 OpenAlex；第二次只补到 2 条。
- 探测（`probe-abs/`）：用 wispaper quick_search 按标题检索 4 篇文献，4 篇都返回了同一篇文献的完整摘要（1100–1800 字符），其中 3 篇是 OpenAlex、Semantic Scholar、CrossRef 都补不上的。
- 关键词检索（quick_search）返回的摘要多是片段（440 条中 389 条带省略号），`host_results.adapt_wispaper` 已把片段当作缺摘要处理。

## Global Constraints

- 分支 `nsfc-proposal`，远程 `lauorie`（git@github.com:Lauorie/guoziran.git）。各任务不推送，由控制者在终审后统一推送。
- 不新增必需的第三方依赖：只用标准库、PyYAML、requests。
- 脚本用 `Path(__file__).resolve()` 定位 skill 资产；文件读写显式 `encoding="utf-8"`。
- 仓库中不得出现本机用户目录的绝对路径和团队服务的域名；检查用的 `git grep` 模式由控制者在派发任务时给出，不写进仓库。
- HTTP 请求不附带个人邮箱或身份信息（不加 mailto）。
- `.bib` 条目文本只由脚本按检索结果写入；不手写、不手改。
- 正文占位格式固定为 `【待补充：……】`；内部编号不进正文。
- 示例不得回显对比基准（中标书）的题材：创造力、具身、物化、照样制作、近红外、综合实践活动课程、课时、班级等词不进 skill 文档与测试。tracked 文件不提中标书本身。
- 版本号不改动：nsfc-proposal 0.1.0、research-literature-search 1.1.0。改动记入各自 CHANGELOG 的现有版本段落（`### Changed（变更）` 或 `### Added（新增）` 末尾，BAC 行仍在段落最后）。根 `CHANGELOG.md` `[Unreleased]`：每项一句，依任务顺序插在「- `nsfc-length-aligner`：立项依据与研究内容的字数下限下调」那一行之后、「- 本分支未写 BAC 记录，经负责人同意。」（第 39 行附近、紧接其后的那一行）之前。
- research-literature-search 是通用 skill：OpenAlex、Semantic Scholar、CrossRef 检索源保留，供它单独使用；不加 `--offline`、`--host-results`、`--provider-order mcp` 时行为不变。nsfc-proposal 的流程不再触及这些检索源。
- 测试放 `tests/<skill名>/`，unittest 风格，文件名全仓唯一（带 skill 缩写前缀）。测试不联网，产物写系统临时目录。测试命令（仓库根目录）：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider -W ignore::pytest.PytestConfigWarning tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/nsfc-research-foundation-writer tests/research-literature-search`。基线 420 passed、19 subtests passed。
- 提交信息 `<type>(<skill>): <中文摘要>`，末尾附 `Co-Authored-By: <实际完成提交的模型> <noreply@anthropic.com>`。每次提交前测试 0 failed；`find skills tests -name __pycache__ -o -name .pytest_cache` 无输出。不要用 `python3 -I`（它忽略 PYTHONPYCACHEPREFIX）。
- 改文档一律按原文做精确替换（Edit 工具，或在会话临时目录写小脚本做 `str.replace` 并断言命中一次）；不重打中文引号「」“”，不改未要求改动的行。提交前 `git diff` 中不得出现与本任务无关的引号字形变化。
- 文档风格：短句，少副词，不写宣传用语。
- 不改系统级 skill，不碰网页版（`nsfc-skill-web`）。

## Review Focus

1. 在 nsfc-proposal 的流程中，任何一步都不得向 OpenAlex 或 Semantic Scholar 发请求，包括失败兜底：bib_resolve 中 CrossRef 查不到时只记 unresolved（Task 1 测试）；`enrich-abstracts --offline` 不调用任何 fetcher（Task 2 测试）；`run --provider-order mcp` 遇到没有 wispaper 结果或结果为空的检索式时，不调用其他检索源，且 bundle 状态不是 failed（Task 2 测试）。
2. 旧台账中 `source` 为 `openalex` 的记录（funded-2 有一条）：`citation_ledger.py audit`、`consistency_check.py` 照常读取，不报错（Task 1 保持现有测试 `test_np_consistency.py` 第 388 行附近的用例通过）。
3. wispaper 按标题检索返回的摘要仍是片段（带省略号）：不当作完整摘要填入（Task 2 测试）。
4. 记录的标题被 wispaper 截断（以省略号结尾）：检索式去掉省略号；返回的文献标题以截断部分开头且截断部分不少于 30 个字符时，视为同一篇（Task 2 测试）。
5. 第二次补摘要（补检之后）：`abstract-queries --reuse` 不再列出上一次已补到摘要的记录；`enrich-abstracts --reuse` 沿用它们（Task 2 测试）。

---

### Task 1: bib_resolve 只用 CrossRef

**Files:**
- Modify: `skills/nsfc-proposal/scripts/bib_resolve.py`
- Modify: `skills/nsfc-proposal/scripts/citation_ledger.py`（模块文档字符串第 4 行）
- Modify: `tests/nsfc-proposal/test_np_bib_resolve.py`
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

**Interfaces:**
- Produces: `lookup(record, *, session, settings) -> (WorkMeta | None, "crossref" | None, reason | None)`，来源只可能是 `"crossref"`。删去 `OPENALEX_WORKS`、`OPENALEX_TYPES`、`openalex_meta`、`_authoritative_by_doi`（只被 OpenAlex 分支使用；删前 `grep -n _authoritative_by_doi skills tests -r` 确认）。`crossref_by_doi`、`check_task_root`、`backup_file` 不变（`bib_refresh.py` 依赖）。

- [ ] **Step 1: 改测试（先红）**

在 `tests/nsfc-proposal/test_np_bib_resolve.py`：

1. 导入行改为 `from bib_resolve import CROSSREF_WORKS, USER_AGENT, WorkMeta, crossref_meta, make_bibkey, run, title_matches, to_bibtex  # noqa: E402`；删去 `OPENALEX_ITEM_3`。
2. 删去 `test_openalex_fallback`、`_openalex_only_routes`、`test_openalex_doi_goes_back_to_crossref_for_metadata`、`test_openalex_doi_crossref_404_keeps_openalex_metadata`、`HelperTest.test_openalex_book_chapter`。
3. `test_network_failure_goes_to_leads_and_bib_untouched`、`test_server_error_does_not_stop_other_records`、`test_persistent_503_is_unresolved_with_status_in_reason` 的路由表删去 `OPENALEX_WORKS` 那一项，其余断言不变。
4. 在 `ResolveTest` 中新增：

```python
    def test_title_search_uses_crossref_only(self) -> None:
        unrelated = dict(CROSSREF_ITEM_1, title=["Something else entirely about cardiac imaging"])
        session = FakeSession({CROSSREF_WORKS: FakeResponse(200, {"message": {"items": [unrelated]}})})
        summary = self._run(session, {"record_id": "r3", "title": "Reconstruction kernels and texture stability in test scans", "year": 2022})
        outcome = summary["outcomes"][0]
        self.assertEqual(outcome["status"], "unresolved")
        self.assertIn("CrossRef 无标题匹配的条目", outcome["reason"])
        self.assertNotIn("OpenAlex", outcome["reason"])
        self.assertTrue(session.calls)
        for url, _params, _headers in session.calls:
            self.assertTrue(url.startswith(CROSSREF_WORKS), url)

    def test_script_has_no_openalex(self) -> None:
        source = (Path(bib_resolve.__file__)).read_text(encoding="utf-8").lower()
        self.assertNotIn("openalex", source)
```

运行 `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_bib_resolve.py`：导入失败或新测试失败（红）。记下输出。

- [ ] **Step 2: 改 `bib_resolve.py`**

- 模块文档字符串第 4–5 行改为：「输入：rls.paper.v1 记录（JSONL）。有 DOI 时查 CrossRef 并核对标题；没有 DOI 或核对失败时，按标题查 CrossRef。不查其他服务。核对成功的条目追加到 main.tex 指向的第一个 .bib」（下一行「（写前备份，按 DOI 去重）；其余写入 …」保持不变）。
- 删去常量 `OPENALEX_WORKS`、`OPENALEX_TYPES`，函数 `openalex_meta`、`_authoritative_by_doi`。
- `lookup` 中按标题检索的部分改为只查 CrossRef（失败原因的措辞与现在相同：「CrossRef 标题检索失败（…）」「CrossRef 无标题匹配的条目」）：

```python
    query = re.sub(r"\s+", " ", ELLIPSIS_RE.sub(" ", title)).strip()
    try:
        data = _get_json(session, CROSSREF_WORKS, {"query.bibliographic": query, "rows": 5}, settings)
    except (requests.RequestException, ValueError) as exc:
        failures.append(f"CrossRef 标题检索失败（{failure_label(exc)}）")
        return None, None, "；".join(failures)
    for item in ((data or {}).get("message") or {}).get("items") or []:
        meta = crossref_meta(item) if isinstance(item, Mapping) else None
        if meta and title_matches(title, meta.title, settings.title_similarity) and year_ok(year, meta.year, settings.year_window):
            return meta, "crossref", None
    failures.append("CrossRef 无标题匹配的条目")
    return None, None, "；".join(failures)
```

- 删去后不再使用的导入（如 `Callable`），用 `python3 -m pyflakes` 不可用时以 `grep` 逐个确认。
- `grep -n -i openalex skills/nsfc-proposal/scripts/bib_resolve.py` 无输出。

- [ ] **Step 3: `citation_ledger.py` 文档字符串**

第 4 行「元数据出自 CrossRef 还是 OpenAlex、」改为「元数据出自哪个服务（现只用 CrossRef；旧台账中 source 为 openalex 的记录照常读取）、」。代码不改：读取不检查 `source` 的取值。

- [ ] **Step 4: 测试转绿**

运行 Step 1 的命令，全部通过；再跑全套测试命令，0 failed（预期 420 − 4 删去〔`ResolveTest` 3 个、`HelperTest` 1 个〕+ 2 新增 = 418 passed；以实际为准，在报告中写明增减明细）。

- [ ] **Step 5: CHANGELOG 与提交**

- `skills/nsfc-proposal/CHANGELOG.md` 0.1.0 `### Changed（变更）` 末尾（BAC 行之前）加：「- `bib_resolve` 只查 CrossRef：删去 OpenAlex 兜底。CrossRef 查不到的记录写入线索清单，正文不引用。」
- 根 `CHANGELOG.md` 按 Global Constraints 的位置加：「- `nsfc-proposal` 0.1.0：`bib_resolve` 只查 CrossRef，删去 OpenAlex 兜底。」
- 提交：`fix(nsfc-proposal): bib_resolve 只查 CrossRef，删去 OpenAlex 兜底`。

---

### Task 2: research-literature-search 按 wispaper 结果补摘要

**Files:**
- Modify: `skills/research-literature-search/scripts/search_runner.py`
- Create: `tests/research-literature-search/test_rls_host_abstracts.py`
- Modify: `skills/research-literature-search/SKILL.md`、`skills/research-literature-search/README.md`（各加一段用法）
- Modify: `skills/research-literature-search/CHANGELOG.md`（1.1.0 段 `### Added（新增）` 末尾、BAC 行之前）、根 `CHANGELOG.md`

**Interfaces:**
- Consumes: `providers.host_results.load_host_results(path) -> dict[str, list[dict]]`（检索式原文 → 适配后的记录；片段摘要已置为 `None`）；现有 `_read_jsonl`、`_title_key`、`_same_paper`、`_reusable_abstracts`、`write_json`。
- Produces:
  - `abstract_queries(input_path: Path, output_path: Path, *, max_papers: int = 200, min_chars: int = 80, reuse_path: Path | None = None) -> dict`，写 `{"queries": [标题, ...]}`，返回 `{"queries": n, "skipped_reusable": k, "no_title": m, "output": 文件名}`。
  - `enrich_abstracts(..., offline: bool = False, host_results: Mapping[str, list[dict]] | None = None, host_results_name: str | None = None)`：`host_results` 不为 None 时视同 `offline=True`。
  - CLI：`abstract-queries --input --output [--reuse] [--max-papers] [--min-abstract-chars]`；`enrich-abstracts` 新增 `--offline`、`--host-results PATH`。
  - Task 3 的 SKILL.md 依赖这些名字与汇总字段：`attempted`、`filled`、`reused`、`missing`、`offline`、`host_results`。

- [ ] **Step 1: 写失败的测试** `tests/research-literature-search/test_rls_host_abstracts.py`

```python
# tests/research-literature-search/test_rls_host_abstracts.py
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/research-literature-search/scripts"
sys.path.insert(0, str(SCRIPTS))

from providers.host_results import load_host_results  # noqa: E402
from search_runner import abstract_queries, enrich_abstracts, run_search  # noqa: E402

TITLE = "Household food waste separation behavior and the importance of convenience"
FULL = "Two different strategies aiming at increasing household source-separation of food waste were assessed in a full-scale trial."
SNIPPET = "… strategies aiming at increasing household source-separation of food waste were assessed …"
TRUNC = "Promoting and maintaining public participation in waste separation policies…"
TRUNC_FULL = "Promoting and maintaining public participation in waste separation policies: a comparative study in two cities"


def _boom(*_a: object, **_k: object) -> list:
    raise AssertionError("no network request is allowed in offline mode")


NO_NET = {name: _boom for name in ("crossref", "semantic_scholar", "openalex")}


def _host(path: Path, entries: list[tuple[str, list[dict]]]) -> Path:
    payload = {"schema": "rls.host_results.v1", "provider": "wispaper",
               "queries": [{"query": q, "tool": "quick_search", "papers": papers} for q, papers in entries]}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class HostAbstractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _jsonl(self, name: str, rows: list[dict]) -> Path:
        path = self.dir / name
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return path

    def _enrich(self, rows: list[dict], host: Path | None, **kwargs: object) -> tuple[dict, list[dict]]:
        src, dst = self._jsonl("selected.jsonl", rows), self.dir / "enriched.jsonl"
        results = load_host_results(host) if host else None
        summary = enrich_abstracts(src, dst, fetchers=NO_NET, offline=True, host_results=results,
                                   host_results_name=host.name if host else None, **kwargs)
        return summary, [json.loads(line) for line in dst.read_text(encoding="utf-8").splitlines()]

    def test_fills_from_host_by_title_without_network(self) -> None:
        host = _host(self.dir / "abstracts_1_host.json", [(TITLE, [{"title": TITLE, "abstract": FULL, "year": 2014}])])
        summary, rows = self._enrich([{"record_id": "r1", "title": TITLE}], host)
        self.assertEqual(rows[0]["abstract"], FULL)
        self.assertEqual(rows[0]["abstract_status"], "present")
        prov = rows[0]["abstract_provenance"]
        self.assertEqual((prov["source"], prov["method"], prov["query"], prov["host_results"]),
                         ("wispaper", "post_selection", TITLE, "abstracts_1_host.json"))
        self.assertEqual((summary["attempted"], summary["filled"], summary["missing"]), (1, 1, 0))
        self.assertTrue(summary["offline"])
        self.assertEqual(summary["host_results"], "abstracts_1_host.json")
        self.assertEqual(summary["exhausted_providers"], [])

    def test_snippet_from_host_is_not_a_full_abstract(self) -> None:
        host = _host(self.dir / "h.json", [(TITLE, [{"title": TITLE, "abstract": SNIPPET}])])
        summary, rows = self._enrich([{"record_id": "r1", "title": TITLE}], host)
        self.assertEqual(rows[0]["abstract_status"], "missing")
        self.assertEqual(summary["filled"], 0)

    def test_doi_disagreement_rejects_hit(self) -> None:
        host = _host(self.dir / "h.json", [(TITLE, [{"title": TITLE, "abstract": FULL, "doi": "10.1000/other"}])])
        _summary, rows = self._enrich([{"record_id": "r1", "title": TITLE, "doi": "10.1000/own"}], host)
        self.assertEqual(rows[0]["abstract_status"], "missing")
        self.assertEqual(rows[0]["abstract_provenance"]["rejected_mismatch"], 1)

    def test_truncated_title_matches_by_prefix(self) -> None:
        host = _host(self.dir / "h.json", [(TRUNC.rstrip("…"), [{"title": TRUNC_FULL, "abstract": FULL}])])
        _summary, rows = self._enrich([{"record_id": "r1", "title": TRUNC}], host)
        self.assertEqual(rows[0]["abstract"], FULL)

    def test_offline_without_host_requests_nothing(self) -> None:
        summary, rows = self._enrich([{"record_id": "r1", "title": TITLE}], None)
        self.assertEqual(rows[0]["abstract_status"], "missing")
        self.assertEqual((summary["attempted"], summary["filled"]), (1, 0))
        self.assertIsNone(summary["host_results"])

    def test_reuse_then_host(self) -> None:
        prior = self._jsonl("prior.jsonl", [{"record_id": "r1", "title": "Earlier paper", "abstract": FULL, "abstract_status": "present"}])
        host = _host(self.dir / "h.json", [(TITLE, [{"title": TITLE, "abstract": FULL}])])
        summary, rows = self._enrich([{"record_id": "r1", "title": "Earlier paper"}, {"record_id": "r2", "title": TITLE}], host, reuse_path=prior)
        self.assertEqual((summary["reused"], summary["attempted"], summary["filled"]), (1, 1, 1))
        self.assertEqual([r["abstract_status"] for r in rows], ["present", "present"])


class AbstractQueriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _jsonl(self, name: str, rows: list[dict]) -> Path:
        path = self.dir / name
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return path

    def test_lists_titles_missing_full_abstracts(self) -> None:
        rows = [
            {"record_id": "a", "title": TITLE},
            {"record_id": "b", "title": "Already complete", "abstract": FULL},
            {"record_id": "c", "title": "  household   food waste separation behavior and the importance of convenience "},
            {"record_id": "d", "title": TRUNC},
            {"record_id": "e", "title": ""},
        ]
        out = self.dir / "abstract_queries_1.json"
        summary = abstract_queries(self._jsonl("s.jsonl", rows), out)
        queries = json.loads(out.read_text(encoding="utf-8"))["queries"]
        self.assertEqual(queries, [TITLE, TRUNC.rstrip("…").strip()])
        self.assertEqual((summary["queries"], summary["no_title"], summary["skipped_reusable"]), (2, 1, 0))

    def test_reuse_skips_already_filled_records(self) -> None:
        prior = self._jsonl("prior.jsonl", [{"record_id": "a", "title": TITLE, "abstract": FULL, "abstract_status": "present"}])
        out = self.dir / "q.json"
        summary = abstract_queries(self._jsonl("s.jsonl", [{"record_id": "a", "title": TITLE}]), out, reuse_path=prior)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["queries"], [])
        self.assertEqual((summary["queries"], summary["skipped_reusable"]), (0, 1))

    def test_cli_round_trip_and_missing_host_file(self) -> None:
        src = self._jsonl("s.jsonl", [{"record_id": "a", "title": TITLE}])
        env = {**os.environ, "PYTHONPYCACHEPREFIX": str(ROOT / ".bensz-api" / "pycache")}
        q = subprocess.run([sys.executable, str(SCRIPTS / "search_runner.py"), "abstract-queries", "--input", str(src),
                            "--output", str(self.dir / "q.json")], capture_output=True, text=True, env=env)
        self.assertEqual(q.returncode, 0, q.stderr)
        self.assertEqual(json.loads(q.stdout)["queries"], 1)
        e = subprocess.run([sys.executable, str(SCRIPTS / "search_runner.py"), "enrich-abstracts", "--offline", "--input", str(src),
                            "--output", str(self.dir / "o.jsonl"), "--host-results", str(self.dir / "absent.json")],
                           capture_output=True, text=True, env=env)
        self.assertEqual(e.returncode, 2)


class McpOnlyBundleTests(unittest.TestCase):
    def test_mcp_only_order_never_calls_other_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "q.json").write_text(json.dumps({"queries": ["alpha query", "beta query", "gamma query"]}), encoding="utf-8")
            host = _host(base / "host.json", [
                ("alpha query", [{"title": "Alpha paper on habits", "doi": "10.1000/a1", "year": 2020, "authors": ["A B"], "abstract": FULL}]),
                ("beta query", []),
            ])
            manifest = run_search(topic="t", domain=None, query_file=base / "q.json", output_dir=base / "out", scope_root=base,
                                  filters={}, provider_order=["mcp"], max_results_per_query=20, max_total=100, fallback_enabled=True,
                                  provider_options={"min_queries": 1, "max_queries": 25}, preprint_profile="auto",
                                  host_results=load_host_results(host), provider_functions=NO_NET)
        self.assertIn(manifest["status"], {"success", "partial_success"})
        self.assertEqual({a["provider"] for a in manifest["attempts"]}, {"mcp"})


if __name__ == "__main__":
    unittest.main()
```

运行 `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/research-literature-search/test_rls_host_abstracts.py`：导入 `abstract_queries` 失败（红）。`McpOnlyBundleTests` 在现有代码上应已通过（它钉住现有行为）；若不通过，停下报告。

- [ ] **Step 2: 实现**

在 `search_runner.py`（`_reusable_abstracts` 之后）加：

```python
ELLIPSES = ("…", "...")
TRUNCATED_TITLE_MIN_CHARS = 30


def _strip_ellipses(text: str) -> str:
    text = " ".join(str(text or "").split())
    while text.endswith(ELLIPSES):
        text = text[:-1].rstrip() if text.endswith("…") else text[:-3].rstrip()
    while text.startswith(ELLIPSES):
        text = text[1:].lstrip() if text.startswith("…") else text[3:].lstrip()
    return text


def _needs_abstract(row: Mapping[str, Any], min_chars: int) -> bool:
    abstract = row.get("abstract")
    return not (isinstance(abstract, str) and len(abstract.strip()) >= min_chars)


def _host_match(hit: Mapping[str, Any], *, title: str, doi: str | None) -> bool:
    """wispaper 结果是否就是这条记录：DOI 都有时比 DOI；否则比标题，截断的标题按前缀比。"""
    if _same_paper(hit, title=title, doi=doi):
        return True
    hit_doi = normalize_doi(hit.get("doi"))
    if doi and hit_doi:
        return False
    own = _title_key(_strip_ellipses(title))
    truncated = str(title or "").strip().endswith(ELLIPSES)
    return truncated and len(own) >= TRUNCATED_TITLE_MIN_CHARS and _title_key(hit.get("title")).startswith(own)


def _host_candidates(host_results: Mapping[str, list[dict[str, Any]]], title: str) -> list[tuple[str, dict[str, Any]]]:
    """标题与检索式相同的那一组排在前面，其余按文件顺序。"""
    own = _title_key(_strip_ellipses(title))
    first = [(q, hit) for q, hits in host_results.items() if _title_key(q) == own for hit in hits]
    rest = [(q, hit) for q, hits in host_results.items() if _title_key(q) != own for hit in hits]
    return first + rest


def abstract_queries(input_path: Path, output_path: Path, *, max_papers: int = 200, min_chars: int = 80,
                     reuse_path: Path | None = None) -> dict[str, Any]:
    """列出缺完整摘要的记录标题（去重、去省略号），写成 {"queries": [...]}，供 wispaper 按标题检索。"""
    rows = _read_jsonl(input_path)
    reusable = _reusable_abstracts(reuse_path, min_chars) if reuse_path is not None else {}
    queries: list[str] = []
    seen: set[str] = set()
    skipped_reusable = no_title = 0
    for row in rows[: max_papers if max_papers > 0 else len(rows)]:
        if not _needs_abstract(row, min_chars):
            continue
        if str(row.get("record_id") or "") in reusable:
            skipped_reusable += 1
            continue
        title = _strip_ellipses(row.get("title") or "")
        key = _title_key(title)
        if not key:
            no_title += 1
            continue
        if key not in seen:
            seen.add(key)
            queries.append(title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, {"queries": queries})
    return {"queries": len(queries), "skipped_reusable": skipped_reusable, "no_title": no_title, "output": output_path.name}
```

注意：`TITLE` 与 `"  household   food waste …"` 的 `_title_key` 相同，只保留先出现的那条原文。`write_json` 若不建父目录，以上 `mkdir` 保留；若它已建，删去这一行。

`enrich_abstracts` 改动：

- 签名加 `offline: bool = False, host_results: Mapping[str, list[dict[str, Any]]] | None = None, host_results_name: str | None = None`；函数开头 `offline = offline or host_results is not None`。
- 跳过已有摘要的判断改用 `_needs_abstract(row, min_chars)`（行为不变）。
- 沿用（`--reuse`）的分支不变。
- `attempted += 1` 之后，`offline` 为真时走下面这段，然后 `continue`（不进入现有的 crossref / semantic_scholar / openalex 循环）：

```python
        if offline:
            title = str(row.get("title") or "")
            doi = normalize_doi(str(row.get("doi") or (row.get("identifiers") or {}).get("doi") or ""))
            rejected = 0
            for query, hit in _host_candidates(host_results or {}, title):
                candidate = _hit_abstract(hit)
                if len(candidate) < min_chars:
                    continue
                if not _host_match(hit, title=title, doi=doi):
                    rejected += 1
                    continue
                row["abstract"] = candidate
                row["abstract_status"] = "present"
                row["abstract_provenance"] = {"source": "wispaper", "method": "post_selection", "query": query,
                                              "host_results": host_results_name, "rejected_mismatch": rejected}
                filled += 1
                break
            else:
                row["abstract_status"] = "missing"
                row["abstract_provenance"] = {"source": "wispaper", "method": "post_selection", "query": None,
                                              "host_results": host_results_name, "rejected_mismatch": rejected}
            row.setdefault("quality_warnings", [])
            if row["abstract_status"] == "missing" and "missing_abstract" not in row["quality_warnings"]:
                row["quality_warnings"].append("missing_abstract")
            continue
```

  `rejected` 只统计「摘要够长、但不是同一篇」的结果；对于测试 `test_doi_disagreement_rejects_hit`，结果为 1。`_host_candidates` 遍历全部结果，摘要片段已由 `adapt_wispaper` 置为 `None`，`_hit_abstract` 返回空串，被长度判断跳过。
- 汇总加 `"offline": offline` 与 `"host_results": host_results_name`；`offline` 时 `exhausted_providers` 为 `[]`。

CLI：

- `enrich` 子解析器加 `--offline`（`action="store_true"`，help「不向任何检索服务发请求；摘要只取自 --host-results 与 --reuse」）与 `--host-results`（`type=Path`，help「rls.host_results.v1 文件（wispaper 按标题检索的结果）；给出时只从它取摘要，不发网络请求」）。
- 主函数 `enrich-abstracts` 分支：`--host-results` 给出但文件不存在时打印 `✗ --host-results 文件不存在：<路径>` 到 stderr，返回 2；`load_host_results` 抛 `ValueError` 时打印 `✗ --host-results 读不了：<原因>`，返回 2；否则传入 `offline=args.offline, host_results=..., host_results_name=args.host_results.name`。
- 新增子解析器 `abstract-queries`：`--input`、`--output`（必需，`type=Path`）、`--reuse`（可选，不存在时同 `enrich-abstracts` 返回 2）、`--max-papers`（默认 200）、`--min-abstract-chars`（默认 80）；打印 `abstract_queries(...)` 的返回值（JSON），返回 0。

- [ ] **Step 3: 测试转绿，全套 0 failed**（预期 +12）

- [ ] **Step 4: 文档**

- `skills/research-literature-search/SKILL.md`：在 `enrich-abstracts` 的说明处（`--reuse` 那句之后）加一段：「宿主已有检索服务（如 wispaper）时，先用 `abstract-queries` 列出缺完整摘要的记录标题，由宿主按标题检索并存为 `rls.host_results.v1` 文件，再运行 `enrich-abstracts --offline --host-results <文件>`：摘要只从该文件取，按 DOI 或标题核对是同一篇，摘要片段不算；不向其他检索服务发请求。`--offline` 不带 `--host-results` 时只沿用 `--reuse` 的结果。」
- `README.md` 同步一句。
- `CHANGELOG.md` 1.1.0 `### Added（新增）` 末尾（BAC 行之前）：「- `abstract-queries` 子命令；`enrich-abstracts` 新增 `--offline`、`--host-results`：按宿主检索结果补摘要，不发网络请求。」
- 根 `CHANGELOG.md`：「- `research-literature-search` 1.1.0：`enrich-abstracts` 可只按 wispaper 的标题检索结果补摘要（`--offline`、`--host-results`、`abstract-queries`），不发其他网络请求。」

- [ ] **Step 5: 提交** `feat(research-literature-search): 按 wispaper 标题检索结果补摘要，可完全离线`

---

### Task 3: nsfc-proposal 第 3 步只用 wispaper

**Files:**
- Modify: `skills/nsfc-proposal/SKILL.md`、`skills/nsfc-proposal/README.md`
- Modify: `tests/nsfc-proposal/test_np_skill_docs.py`（新增 `RoundFiveRetrievalDocsTest`）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

**Interfaces:**
- Consumes: Task 2 的 `abstract-queries`、`enrich-abstracts --offline --host-results`，汇总字段 `attempted`、`filled`、`reused`、`missing`；Task 1 的 CrossRef-only `bib_resolve`。

每处改动都是精确替换：先用 `grep -n` 找到原文，再替换。原文以文件为准；下面引用的原文若与文件有出入，以文件为准并在报告中写明。

- [ ] **Step 1: 写失败的文档测试**（`tests/nsfc-proposal/test_np_skill_docs.py` 末尾、`if __name__` 之前）

```python
class RoundFiveRetrievalDocsTest(unittest.TestCase):
    def test_flow_never_mentions_other_search_services(self) -> None:
        for rel in ("SKILL.md", "README.md", "scripts/bib_resolve.py", "scripts/bib_refresh.py"):
            text = (SKILL / rel).read_text(encoding="utf-8").lower()
            for name in ("openalex", "semantic scholar", "semantic_scholar"):
                self.assertNotIn(name, text, f"{rel}: {name}")

    def test_bundles_are_wispaper_only(self) -> None:
        self.assertEqual(TEXT.count("--provider-order mcp"), 2)
        self.assertNotIn("--no-fallback", TEXT)
        self.assertNotIn("其他检索源", TEXT.replace("不改用其他检索源", ""))

    def test_abstracts_come_from_wispaper_offline(self) -> None:
        self.assertIn("abstract-queries", TEXT)
        self.assertIn("--name abstracts_1 --tool quick_search", TEXT)
        self.assertIn("enrich-abstracts --offline", TEXT)
        self.assertNotIn("exhausted_providers", TEXT)

    def test_wispaper_unavailable_stops(self) -> None:
        row = [ln for ln in TEXT.splitlines() if ln.startswith("| wispaper 不可用")]
        self.assertEqual(len(row), 1)
        self.assertIn("停在第 3 步", row[0])
        self.assertIn("不改用其他检索源", row[0])
```

运行该文件：4 个新测试失败（红）。

- [ ] **Step 2: SKILL.md「### 输入」**

- 「必需」下 `申请人的研究信息` 那一行之后加一行（与上一行同缩进）：「  - wispaper 检索凭据：`WIS_MCP_URL`、`WIS_MCP_TOKEN`（环境变量或 `.env`）。缺失或被拒时停在第 3 步，见「失败与恢复」。」
- 「可选」那一行删去「wispaper 检索凭据（`WIS_MCP_URL`、`WIS_MCP_TOKEN`，缺失时按「wispaper 不可用」处理）；」这一段（含分号），其余不动。

- [ ] **Step 3: 第 3 步第 5 项（建 bundle）**

- 两条 `search_runner.py run` 命令：关键词 bundle 的 `--max-results-per-query 20 --host-results …` 改为 `--max-results-per-query 20 --provider-order mcp --host-results …`；论断 bundle 的 `--max-results-per-query 10 --no-fallback --host-results …` 改为 `--max-results-per-query 10 --provider-order mcp --host-results …`。
- 代码块之后「没有 wispaper 时去掉 `--host-results`；论断 bundle 同时去掉 `--no-fallback`。」改为：「`--provider-order mcp` 让 bundle 只用 wispaper 的结果，不向其他检索服务发请求。wispaper 不可用时不建 bundle，见「失败与恢复」。」
- 检查第 5 项及其他各处是否还有 `--no-fallback`；有则同样改为 `--provider-order mcp`。

- [ ] **Step 4: 第 3 步第 6 项（补摘要）整段替换**

从「6. 逐条论断从各 bundle 的」起，到「在 `stages.md` 记下 `reused` 条数。」止，替换为：

````markdown
6. 逐条论断从各 bundle 的 `candidates_deduped.jsonl` 中挑候选证据，原样写入 `T/nsfc-proposal/output/selected.jsonl`，再用 wispaper 补全摘要。关键词检索只返回摘要片段，片段不算完整摘要；按标题检索通常能拿到完整摘要。先列出缺完整摘要的记录标题，按标题检索，再把摘要填回记录：

```bash
python3 SK/research-literature-search/scripts/search_runner.py abstract-queries \
  --input T/nsfc-proposal/output/selected.jsonl --output T/nsfc-proposal/input/abstract_queries_1.json
python3 S/scripts/wispaper_search.py run --task-root T --name abstracts_1 --tool quick_search \
  --query-file T/nsfc-proposal/input/abstract_queries_1.json
python3 SK/research-literature-search/scripts/search_runner.py enrich-abstracts --offline \
  --input T/nsfc-proposal/output/selected.jsonl --output T/nsfc-proposal/output/selected_enriched.jsonl \
  --host-results T/nsfc-proposal/output/wispaper/abstracts_1_host.json
```

   - `wispaper_search.py` 的退出码按第 4 项处理。
   - `abstract-queries` 输出的 `queries` 为 0 时，不运行 `wispaper_search.py`，`enrich-abstracts` 去掉 `--host-results`，保留 `--offline`。
   - `--offline` 保证补摘要不向 wispaper 以外的服务发请求，不得去掉。
   - 汇总写在 `T/nsfc-proposal/output/selected_enriched.jsonl.summary.json`。`filled / attempted` 低于一半（`attempted` 为 0 时不算）时，背景类论断也可以写成论断问句检索，以拿到带完整摘要的记录：问句写入新的 `claim_queries_<n>.json`（n 接在已有文件之后），按本步第 4、5 项检索，再回到本项挑选并补全摘要。在 `stages.md` 记录这一偏离及原因。
   - 补检后重新挑选、再次补全摘要时，编号递增（`abstract_queries_2.json`、`--name abstracts_2`），`abstract-queries` 与 `enrich-abstracts` 都加 `--reuse T/nsfc-proposal/output/selected_enriched.jsonl`（与 `--output` 相同即可，脚本先读旧文件再覆盖）：同一 `record_id` 上一次已补到的摘要直接沿用，不再检索。汇总的 `reused` 是沿用条数，不计入 `attempted`；判断「低于一半」时也不计入。不手工合并两次运行的结果。在 `stages.md` 记下每次的检索式条数、`filled`、`reused`。
````

- [ ] **Step 5: 「失败与恢复」表与约束**

逐行替换（整行）：

- `| wispaper 不可用（…退出码 3） | …` →
  `| wispaper 不可用（`wispaper_search.py` 退出码 3） | 停在第 3 步，不改用其他检索源。告诉申请人检查 `WIS_MCP_URL`、`WIS_MCP_TOKEN`（未配置，或凭据被拒）；全自动运行也停下，在报告中写明。配置好后从第 3 步第 4 项继续，已存档的检索式不重查 |`
- `| 部分检索式重跑后仍失败（退出码 1） | …` →
  `| 部分检索式重跑后仍失败（退出码 1） | 把仍失败的检索式换个写法（缩短，或换关键词），写入新的检索式文件（论断问句写入新的 `claim_queries_<n>.json`），按第 3 步第 4、5 项再检索一次；仍失败的在 `stages.md` 记下。bundle 用已取得的结果建，不改用其他检索源 |`
- `| CrossRef 与 OpenAlex 都不可达 | …` → `| CrossRef 不可达 | 不新增 `.bib` 条目；相关论断记为 `unsupported` |`
- `| 文献服务限流 | …` →
  `| CrossRef 限流 | `bib_resolve` 自动退避重试；仍未解析的记录稍后只对未解析的子集重跑 `bib_resolve`（未解析记录见 `T/nsfc-proposal/output/bib_resolve.json` 中 status 为 unresolved 的 outcomes；按 record_id 从 `bib_records.jsonl` 取出，另存为 JSONL 作 `--records`），不重跑已写入的记录 |`
- 「### Skill 专属约束」中「文献的作者、期刊、年份、卷期页码只取自 CrossRef 或 OpenAlex 的返回，不凭记忆填写。」→「文献的作者、期刊、年份、卷期页码只取自 CrossRef 的返回，不凭记忆填写。」
- 「## 约束」中关于 wis-scholar-search 的那一条，「未配置时改用其他检索源。」→「未配置时停在检索这一步，请你配置；不改用其他检索源。」（README.md 第 29 行有同一句，同样替换。）
- 全文再 `grep -n -i "openalex\|semantic\|exhausted\|其他检索源\|现有检索源\|--no-fallback" skills/nsfc-proposal/SKILL.md skills/nsfc-proposal/README.md`：只允许「不改用其他检索源」。其余命中逐处改写为 wispaper/CrossRef 的说法并在报告中列出。

- [ ] **Step 6: 测试转绿，全套 0 failed**（预期 +4）

- [ ] **Step 7: CHANGELOG 与提交**

- `skills/nsfc-proposal/CHANGELOG.md` 0.1.0 `### Changed（变更）` 末尾（BAC 行之前）：「- 第 3 步只用 wispaper：bundle 加 `--provider-order mcp`；补摘要改为按标题检索 wispaper（`abstract-queries`、`enrich-abstracts --offline`）；wispaper 不可用时停在第 3 步，不改用其他检索源。」
- 根 `CHANGELOG.md`：「- `nsfc-proposal` 0.1.0：第 3 步只用 wispaper 检索与补摘要，不再请求 OpenAlex、Semantic Scholar；wispaper 不可用时停下。」
- 提交：`docs(nsfc-proposal): 第 3 步只用 wispaper，补摘要改按标题检索`。

---

### Task 4: 数据驱动研究的小标题；设计图不画照片

fresh-1 的研究三是数据驱动研究，子代理为了全章一致用了实验研究的小标题，设计图因此放在「设计」下。`SKILL.md` 第 6.3 步写「要求每项研究内容用同一组，全章一致」，而 `figure_guide.md` 第 7 节已假定数据驱动研究没有「设计」小标题。规则改为按每项研究的类型选。fresh-1 的设计图把「投放情境图片」画成了照片；提示词虽写了「无照片」，自检清单里没有这一条，子代理接受了这张图。

**Files:**
- Modify: `skills/nsfc-proposal/references/section_boundaries.md`（「## 研究内容的小标题」一节）
- Modify: `skills/nsfc-proposal/SKILL.md`（第 6.3 步那一段）
- Modify: `skills/nsfc-proposal/references/figure_guide.md`（第 3、5、6 节，骨架）
- Modify: `tests/nsfc-proposal/test_np_skill_docs.py`（新增 `RoundFiveWritingDocsTest`）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

- [ ] **Step 1: 写失败的文档测试**

```python
class RoundFiveWritingDocsTest(unittest.TestCase):
    def test_subheadings_follow_each_study_type(self) -> None:
        bounds = (SKILL / "references" / "section_boundaries.md").read_text(encoding="utf-8")
        self.assertIn("小标题按每项研究的类型选", bounds)
        self.assertIn("各用各的一组", bounds)
        self.assertNotIn("全章一致", bounds)
        self.assertIn("不为统一改用另一组", TEXT)
        self.assertNotIn("要求每项研究内容用同一组，全章一致", TEXT)

    def test_figures_draw_stimuli_as_icons_and_reject_photos(self) -> None:
        guide = (SKILL / "references" / "figure_guide.md").read_text(encoding="utf-8")
        self.assertEqual(guide.count("无照片、无写实渲染"), 2)
        self.assertIn("画成线描图标", guide)
        self.assertIn("没有照片或写实渲染的图像", guide)
```

运行：2 个新测试失败（红）。

- [ ] **Step 2: `section_boundaries.md`**

- 「每项研究内容下用同一组小标题，按研究类型选一组，全章一致。不用加粗的（1）至（10）罗列。」→「小标题按每项研究的类型选，同类研究用同一组。不用加粗的（1）至（10）罗列。」
- 在「- 数据驱动研究：「数据」「方法」「验证」「判定标准」。」这一行之后空一行，加一段：「一章中既有实验研究又有数据驱动研究时，各用各的一组，不为全章统一改用另一组。数据驱动研究没有被试、流程和操纵，套用实验研究的小标题，「对象与样本量」「流程」下只能写数据来源，设计图也会放错位置。」
- 「研究内容开头放研究框架图，各项研究内容的「设计」小标题下放该研究的设计图」→「研究内容开头放研究框架图，各项研究内容的「设计」小标题下（数据驱动研究为「方法」）放该研究的设计图」。

- [ ] **Step 3: `SKILL.md` 第 6.3 步**

- 「先按研究类型选定一组小标题（实验研究：设计、对象与样本量、流程、指标与分析、预期结果与判定；数据驱动研究：数据、方法、验证、判定标准），作为额外几行追加到信息表」→「先按每项研究的类型选定小标题（实验研究：设计、对象与样本量、流程、指标与分析、预期结果与判定；数据驱动研究：数据、方法、验证、判定标准），逐项写明「研究一：实验研究，用……」，作为额外几行追加到信息表」。
- 「要求每项研究内容用同一组，全章一致，不用加粗的（1）至（10）罗列。」→「要求同类研究用同一组；一章中两类都有时各用各的一组，不为统一改用另一组；不用加粗的（1）至（10）罗列。」
- 「框架图放在研究内容开头，设计图放在对应研究内容的「设计」小标题下，写法见 figure_guide 第 7 节。」→「框架图放在研究内容开头，设计图放在对应研究内容的「设计」小标题下（数据驱动研究为「方法」），写法见 figure_guide 第 7 节。」

- [ ] **Step 4: `figure_guide.md`**

- 第 3 节第 1 条与骨架首行各有一句「…配色不超过 4 种、无照片、无真人面孔、无商标、无水印。」，两处都改为「…配色不超过 4 种、无照片、无写实渲染、无真人面孔、无商标、无水印；实物、场景与刺激材料都画成线描图标。」（用 `str.replace` 一次替换两处并断言替换了 2 处。）
- 第 5 节「- (A) 条件示意：每组或每个条件一格，用图标表示操纵。」之后加一条：「- 条件示意中的实物、场景图片、卡片等刺激材料，画成线描图标，提示词中写明「画成线描图标，不画成照片」。实测时「情境图片」「实物卡片」一类词常被画成照片。」
- 第 6 节自检清单，在「- 数字与第 2 节所列来源一致。」之后加：「- 没有照片或写实渲染的图像（包括缩略图）；有则不合格，提示词中把该对象写成「……的线描图标」后重画。」

- [ ] **Step 5: 测试转绿，全套 0 failed**（预期 +2）

- [ ] **Step 6: CHANGELOG 与提交**

- `skills/nsfc-proposal/CHANGELOG.md` 0.1.0 `### Changed（变更）` 末尾（BAC 行之前）：「- 研究内容的小标题按每项研究的类型选，一章中两类研究都有时各用各的；设计图中的实物与刺激材料画成线描图标，自检时照片或写实渲染判为不合格。」
- 根 `CHANGELOG.md`：「- `nsfc-proposal` 0.1.0：小标题按每项研究的类型选；设计图不画照片，自检把照片判为不合格。」
- 提交：`docs(nsfc-proposal): 小标题按研究类型选；设计图的刺激材料画成图标`。

---

## 追加（2026-10-10）：国自然写作的 skill 一律不用 OpenAlex

申请人在 Task 1–4 之后追加两句：「research-literature-search 里的 OpenAlex 也删掉」；「我要的是整个国自然写作的 skill 里面都不用 openalex……只用 wispaper」。

范围：

- `skills/nsfc-*` 与 research-literature-search 中不留 OpenAlex 的代码、默认顺序、请求和文档。验收：`git grep -il openalex -- 'skills/nsfc-*' skills/research-literature-search tests/nsfc-* tests/research-literature-search ':!*CHANGELOG*'` 只命中 `tests/nsfc-proposal/test_np_consistency.py`（旧台账读取的回归测试，保留）。
- research-literature-review 不是国自然写作的 skill，主力检索源是 OpenAlex，并借用 research-literature-search 的 OpenAlex 适配器。把适配器挪进 research-literature-review，由它自己注入，行为不变。
- CrossRef 只做一件事：按 DOI 或标题核对文献元数据，补全 wispaper 不返回的卷期页码和完整作者名。research-literature-search 单独使用时的 Semantic Scholar、CrossRef 检索源保留；国自然写作的 skill 走不到它们（`--provider-order mcp`、`--offline`，Task 3 的文档测试已钉住）。

Global Constraints 的补充：

- 测试命令加上 `tests/nsfc-ref-alignment`：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider -W ignore::pytest.PytestConfigWarning tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/nsfc-research-foundation-writer tests/research-literature-search tests/nsfc-ref-alignment`。Task 4 之后基线 434 passed、19 subtests passed（`tests/nsfc-ref-alignment` 尚不存在时 pytest 会报目录不存在，Task 7 之前去掉这一项）。
- research-literature-review 的测试在 skill 目录内：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider skills/research-literature-review/tests`。基线 2 failed（`test_search_validator_isolated_from_review_query_contract`、`test_each_supported_autodiscovery_location_uses_multi_query` 的 subtest 3，均为既有失败）、15 passed、16 subtests passed。改动后不得新增失败。
- research-literature-review、nsfc-ref-alignment 的版本号不改；改动记入各自 CHANGELOG 的 `[Unreleased]`（没有就新建，放在第一个版本段落之前，含 `### Changed`）。根 `CHANGELOG.md` 的位置规则同上：依任务顺序接在上一条之后、「- 本分支未写 BAC 记录，经负责人同意。」之前。

### Task 5: research-literature-review 自带 OpenAlex 适配器

先做这一步，再在 Task 6 从 research-literature-search 删除，使每次提交后两个 skill 都能用。

**Files:**
- Modify: `skills/research-literature-search/scripts/search_runner.py`（只改检索源的跳过条件）
- Create: `skills/research-literature-review/scripts/openalex_provider.py`
- Modify: `skills/research-literature-review/scripts/openalex_search.py`、`skills/research-literature-review/scripts/multi_query_search.py`
- Create: `skills/research-literature-review/tests/test_openalex_provider.py`
- Modify: `tests/research-literature-search/test_rls_host_results.py`（加 1 个测试）
- Modify: `skills/research-literature-review/CHANGELOG.md`、根 `CHANGELOG.md`

**Interfaces:**
- Produces: `openalex_provider.search(query, *, max_results=50, min_year=None, max_year=None, mailto=None, timeout=30, session=None, **_) -> list[dict]`。每条结果已转成通用字段：`id`、`title`、`authors`（字符串列表）、`doi`、`year`、`venue`、`abstract`（由 `abstract_inverted_index` 还原的纯文本；没有时为 None）、`url`、`is_open_access`、`type`。research-literature-search 不再需要认识 OpenAlex 的返回格式。
- `run_search`：调用方经 `provider_functions` 注入的检索源，即使名字不在 `SUPPORTED_PROVIDERS` 中，也照常调用。

- [ ] **Step 1: 检索源的跳过条件**

`search_runner.py` 中：

```python
            if provider not in SUPPORTED_PROVIDERS:
                item = {"provider": provider, "status": "skipped", "results": 0, "reason": "host tool required"}
```

改为只跳过没有适配器的检索源，跳过原因不变：

```python
            if provider not in SUPPORTED_PROVIDERS and provider not in registry:
                item = {"provider": provider, "status": "skipped", "results": 0, "reason": "host tool required"}
```

（`registry = _provider_registry(provider_functions)` 已含注入的函数；`mcp` 在前面的分支处理，`duckduckgo` 没有适配器，行为不变。）在 `tests/research-literature-search/test_rls_host_results.py` 加一个测试：`run_search(..., provider_order=["custom_source"], provider_functions={"custom_source": fake})` 时 `fake` 被调用，bundle 中有它返回的记录。先红后绿。

- [ ] **Step 2: 适配器与等价测试**

`openalex_provider.py`：把 `skills/research-literature-search/scripts/providers/openalex.py` 的 `search()` 搬过来（请求参数、`mailto` 行为不变），返回前逐条转换为上面的通用字段。转换规则：`title` 取 `title` 或 `display_name`；`authors` 取 `authorships[].author.display_name`；`doi` 去掉 `https://doi.org/` 前缀；`year` 取 `publication_year`；`venue` 取 `primary_location.source.display_name`；`abstract` 由 `abstract_inverted_index` 按位置还原（把 research-literature-search 中 `abstract_from_inverted_index` 的实现复制进来）；`url` 取 `doi` 链接或 `primary_location.landing_page_url`；`is_open_access` 取 `open_access.is_oa`；`type` 原样。

`skills/research-literature-review/tests/test_openalex_provider.py`（unittest，不联网）：

1. 等价测试：构造一条典型 OpenAlex work（含 `authorships`、`primary_location.source`、`abstract_inverted_index`、`publication_year`、`doi`、`open_access`）。分别用（a）现有方式：原始 work 直接交给 research-literature-search 的 `normalize_record(raw, provider="openalex")`；（b）新方式：`openalex_provider._to_raw(work)`（或你命名的转换函数）的结果交给 `normalize_record(..., provider="openalex")`。断言两者的 `title`、`authors`、`year`、`venue`、`identifiers["doi"]`、`abstract`、`abstract_status`、`publication["is_open_access"]` 相同。
2. 注入测试：`multi_query_search` 的进程内接口与 CLI `--bundle-dir` 路径都把 `{"openalex": openalex_provider.search}` 传给 `run_search`。用 `unittest.mock.patch` 替换 `openalex_provider.search`，断言被调用。

- [ ] **Step 3: 两个 wrapper 改用本地适配器**

- `openalex_search.py`：`from providers.openalex import search as search_openalex` 改为从同目录的 `openalex_provider` 导入（同目录导入的写法照该文件现有的 `sys.path` 处理）。
- `multi_query_search.py`：`search_openalex` 改从 `openalex_provider` 导入；`multi_search()` 中的 `functions` 映射与 `main()` 中 `--bundle-dir` 分支的 `run_search(...)` 调用都传 `provider_functions={"openalex": search_openalex, ...}`（`main()` 现在没有传，必须加上，否则 OpenAlex 会从综述 skill 的主路径中消失）。

- [ ] **Step 4: 测试**：本仓库测试命令（不含 `tests/nsfc-ref-alignment`）0 failed；`skills/research-literature-review/tests` 不新增失败。

- [ ] **Step 5: CHANGELOG 与提交**
- `skills/research-literature-review/CHANGELOG.md` `[Unreleased]` `### Changed`：「- OpenAlex 适配器移入本 skill（`scripts/openalex_provider.py`），由本 skill 注入 research-literature-search；检索行为不变。」
- `CHANGELOG.md`：「- `research-literature-review`：OpenAlex 适配器移入本 skill，research-literature-search 接受调用方注入的检索源。」
- 提交：`refactor(research-literature-review): OpenAlex 适配器移入本 skill，经注入使用`。

### Task 6: research-literature-search 删除 OpenAlex

**Files:**
- Delete: `skills/research-literature-search/scripts/providers/openalex.py`
- Modify: `skills/research-literature-search/scripts/providers/__init__.py`、`search_runner.py`、`candidate_schema.py`、`dedupe_papers.py`、`config.yaml`、`SKILL.md`、`README.md`、`references/provider-guide.md`、`references/paper-schema.md`
- Modify: `tests/research-literature-search/test_rls_enrich_abstracts.py`、`test_rls_host_results.py`、`test_rls_host_abstracts.py`
- Create: `tests/research-literature-search/test_rls_no_openalex.py`
- Modify: `skills/research-literature-search/CHANGELOG.md`（1.1.0 段 `### Changed（变更）`，没有则新建该小节，BAC 行之前）、根 `CHANGELOG.md`

- [ ] **Step 1: 写失败的测试** `tests/research-literature-search/test_rls_no_openalex.py`：

```python
# tests/research-literature-search/test_rls_no_openalex.py
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "research-literature-search"
sys.path.insert(0, str(SKILL / "scripts"))

import search_runner  # noqa: E402
from candidate_schema import IDENTIFIER_KEYS  # noqa: E402

TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".txt"}


class NoOpenAlexTests(unittest.TestCase):
    def test_skill_files_never_mention_openalex(self) -> None:
        hits = [str(p.relative_to(ROOT)) for p in SKILL.rglob("*")
                if p.is_file() and p.suffix in TEXT_SUFFIXES and p.name != "CHANGELOG.md"
                and "__pycache__" not in p.parts and "openalex" in p.read_text(encoding="utf-8").lower()]
        self.assertEqual(hits, [])

    def test_defaults_have_no_openalex(self) -> None:
        self.assertNotIn("openalex", search_runner.DEFAULT_PROVIDER_ORDER)
        self.assertNotIn("openalex", search_runner.SUPPORTED_PROVIDERS)
        self.assertNotIn("openalex", search_runner._provider_registry())
        self.assertNotIn("openalex", IDENTIFIER_KEYS)
        self.assertFalse((SKILL / "scripts" / "providers" / "openalex.py").exists())


if __name__ == "__main__":
    unittest.main()
```

运行：2 个失败（红）。

- [ ] **Step 2: 删除与改写**

- 删除 `providers/openalex.py`；`providers/__init__.py` 去掉 `search_openalex` 的导入与 `__all__` 项。
- `search_runner.py`：两处 `from providers import …` 去掉 `search_openalex`；`DEFAULT_PROVIDER_ORDER = ["mcp", "semantic_scholar", "crossref", "duckduckgo"]`；`SUPPORTED_PROVIDERS = {"semantic_scholar", "crossref"}`；`_provider_registry` 去掉 `"openalex"`；补摘要的来源元组去掉 `("openalex", title)`；`# OpenAlex is the main source; …` 注释改为 `# Stop once the first source meets the target; only supplement if clearly below it.`；`_hit_abstract` 不再还原倒排索引（只取 `abstract` 纯文本），文档字符串相应改写；导入中去掉 `abstract_from_inverted_index`。
- `candidate_schema.py`：删除 `abstract_from_inverted_index` 及其在 `normalize_record` 中的调用；`IDENTIFIER_KEYS = ("doi", "pmid", "arxiv", "semantic_scholar")`；`stable_record_id` 的键元组去掉 `"openalex"`；`_source_envelope` 去掉 `or raw.get("openalex_id")`；删除 `if provider == "openalex" …` 两行；扁平视图去掉 `"openalex_id"`。旧 bundle 中多出的 `identifiers.openalex`、`openalex_id` 不影响校验（`validate_record` 只检查 `IDENTIFIER_KEYS` 中的键），在报告中用 fresh-1 的一个 bundle（`/home/juli/guoziran/nsfc-proposal-eval/fresh-1/projects/proj/.bensz-api/task-20261010-1702-waste-sorting-habit/research-literature-search/output/keyword-bundle`）跑 `search_runner.py validate --bundle` 证明。
- `dedupe_papers.py`：两处键元组去掉 `openalex` / `openalex_id`。
- `config.yaml`：`provider_priority: [mcp, semantic_scholar, crossref, duckduckgo]`。
- 文档：`SKILL.md`、`README.md`（第 31 行示例改为 `--provider-order semantic_scholar,crossref`；第 51 行那段删去或改写为与 OpenAlex 无关的说法）、`references/provider-guide.md`（第 3 行改为：「默认先用宿主检索结果（mcp，当前为 wispaper）；没有时依次用 Semantic Scholar、Crossref。MCP 与 duckduckgo 需要宿主能力……」，后半句照原文）、`references/paper-schema.md`（identifiers 列表去掉 openalex）。全目录 `grep -rn -i openalex skills/research-literature-search` 只允许命中 CHANGELOG。
- 测试：`test_rls_enrich_abstracts.py` 去掉离线 fetcher 元组中的 `"openalex"`，删除 `test_openalex_inverted_index_is_rebuilt` 与 `InvertedIndexTests`，以及导入 `abstract_from_inverted_index`；其他用 `openalex` 作 fetcher 名的测试改用 `semantic_scholar` 或 `crossref`，断言语义不变。`test_rls_host_results.py` 中的 `fake_openalex` / `"openalex"` 改为 `semantic_scholar`。`test_rls_host_abstracts.py` 的 `NO_NET` 去掉 `"openalex"`。

- [ ] **Step 3: 测试转绿**：本仓库测试命令（不含 `tests/nsfc-ref-alignment`）0 failed，报告增减明细；`skills/research-literature-review/tests` 不新增失败（它已在 Task 5 改为自带适配器）。

- [ ] **Step 4: CHANGELOG 与提交**
- `skills/research-literature-search/CHANGELOG.md`：「- 删除 OpenAlex 检索源、补摘要来源与 `openalex` 标识符；默认顺序为 mcp、Semantic Scholar、Crossref。旧 bundle 中的 `openalex_id` 字段不影响校验。」
- `CHANGELOG.md`：「- `research-literature-search` 1.1.0：删除 OpenAlex（检索源、补摘要、标识符与文档）。」
- 提交：`refactor(research-literature-search): 删除 OpenAlex`。

### Task 7: nsfc-ref-alignment 只用 CrossRef 核验 DOI；国自然写作的 skill 全部不含 OpenAlex

**Files:**
- Modify: `skills/nsfc-ref-alignment/scripts/online_verify.py`、`scripts/run_ref_alignment.py`、`config.yaml`、`README.md`（以及 `SKILL.md` 中若有的相同说法）
- Modify: `skills/nsfc-proposal/scripts/citation_ledger.py`（模块文档字符串）
- Create: `tests/nsfc-ref-alignment/test_nra_online_verify.py`
- Modify: `tests/nsfc-proposal/test_np_skill_docs.py`（新增 1 个测试）
- Modify: `skills/nsfc-ref-alignment/CHANGELOG.md`、`skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

- [ ] **Step 1: 写失败的测试**

`tests/nsfc-ref-alignment/test_nra_online_verify.py`（unittest，不联网）：用 `unittest.mock.patch.object(online_verify, "_http_get_json", fake)` 记录 URL。
1. CrossRef 返回带 `message.title` 的结果：`check_doi_online("10.1000/x", "Some title")` 的 `ok` 为真，`crossref_title` 正确；所有 URL 以 `https://api.crossref.org/` 开头。
2. CrossRef 失败（`fake` 返回 `(None, "HTTP 404")`）：`ok` 为假；所有 URL 仍只有 CrossRef；结果的 `to_dict()` 中没有任何以 `openalex` 开头的键。
3. `online_verify.py` 与 `run_ref_alignment.py` 的源码（小写）不含 `openalex`。

`tests/nsfc-proposal/test_np_skill_docs.py` 加：

```python
class NsfcSkillsHaveNoOpenAlexTest(unittest.TestCase):
    def test_no_nsfc_skill_mentions_openalex(self) -> None:
        suffixes = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".tex", ".sh"}
        hits = [str(p.relative_to(ROOT)) for d in sorted(SKILLS.glob("nsfc-*")) for p in d.rglob("*")
                if p.is_file() and p.suffix in suffixes and p.name != "CHANGELOG.md" and "__pycache__" not in p.parts
                and "openalex" in p.read_text(encoding="utf-8", errors="ignore").lower()]
        self.assertEqual(hits, [])
```

运行：失败（红），命中 nsfc-ref-alignment 的 4 个文件与 `citation_ledger.py`。

- [ ] **Step 2: 改写**
- `online_verify.py`：删去 OpenAlex 请求与 `openalex_ok`、`openalex_title`、`title_similarity_openalex` 字段；`ok = crossref_ok`；错误信息只含 CrossRef。
- `run_ref_alignment.py`：标题不符的判断只用 CrossRef 的相似度；输出字段去掉 `title_similarity_openalex`；文档字符串与 `--verify-online` 的 help 改为「在线核验 DOI（Crossref）」。
- `config.yaml` 第 31 行、`README.md` 第 108 行：「Crossref/OpenAlex」改为「Crossref」。
- `citation_ledger.py` 第 4 行：「元数据出自哪个服务（现只用 CrossRef；旧台账中 source 为 openalex 的记录照常读取）、」改为「元数据出自哪个服务（现只用 CrossRef；旧台账中其他来源的记录照常读取）、」。
- 全部 `skills/nsfc-*`：`grep -rn -i openalex skills/nsfc-* --include=* | grep -v CHANGELOG` 无输出。

- [ ] **Step 3: 测试转绿**：完整测试命令（含 `tests/nsfc-ref-alignment`）0 failed。

- [ ] **Step 4: CHANGELOG 与提交**
- `skills/nsfc-ref-alignment/CHANGELOG.md` `[Unreleased]` `### Changed`：「- 在线核验 DOI 只查 Crossref，删去 OpenAlex。」
- `skills/nsfc-proposal/CHANGELOG.md` 0.1.0 `### Changed（变更）` 末尾（BAC 行之前）：「- 引用台账的说明不再提 OpenAlex；文档测试检查所有 nsfc-* skill 不含 OpenAlex。」
- `CHANGELOG.md`：「- `nsfc-ref-alignment`：在线核验 DOI 只查 Crossref；国自然写作的 skill 均不再含 OpenAlex。」
- 提交：`fix(nsfc-ref-alignment): 在线核验只查 Crossref，国自然写作的 skill 不再含 OpenAlex`。
