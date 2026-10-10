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


NO_NET = {name: _boom for name in ("crossref", "semantic_scholar")}


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

    def test_cli_rejects_invalid_host_file_and_missing_reuse(self) -> None:
        src = self._jsonl("s.jsonl", [{"record_id": "a", "title": TITLE}])
        env = {**os.environ, "PYTHONPYCACHEPREFIX": str(ROOT / ".bensz-api" / "pycache")}
        bad = self.dir / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        runner = str(SCRIPTS / "search_runner.py")
        cases = {
            "invalid host json": ["enrich-abstracts", "--offline", "--input", str(src), "--output", str(self.dir / "o.jsonl"), "--host-results", str(bad)],
            "abstract-queries missing reuse": ["abstract-queries", "--input", str(src), "--output", str(self.dir / "q.json"), "--reuse", str(self.dir / "none.jsonl")],
            "enrich missing reuse": ["enrich-abstracts", "--offline", "--input", str(src), "--output", str(self.dir / "o2.jsonl"), "--reuse", str(self.dir / "none.jsonl")],
        }
        for label, argv in cases.items():
            with self.subTest(label):
                r = subprocess.run([sys.executable, runner, *argv], capture_output=True, text=True, env=env)
                self.assertEqual(r.returncode, 2, r.stderr)


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
