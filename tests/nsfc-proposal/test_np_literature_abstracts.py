"""文献池补摘要：只用 host 检索结果与 --reuse，不联网。"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import literature as lit  # noqa: E402
from literature_records import load_host_results  # noqa: E402

TITLE = "Household food waste separation behavior and the importance of convenience"
FULL = "Two different strategies aiming at increasing household source-separation of food waste were assessed in a full-scale trial."
SNIPPET = "… strategies aiming at increasing household source-separation of food waste were assessed …"
TRUNC = "Promoting and maintaining public participation in waste separation policies…"
TRUNC_FULL = "Promoting and maintaining public participation in waste separation policies: a comparative study in two cities"


def _host(path: Path, entries: list[tuple[str, list[dict]]]) -> Path:
    payload = {"schema": "rls.host_results.v1", "provider": "wispaper",
               "queries": [{"query": q, "tool": "quick_search", "papers": papers} for q, papers in entries]}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _no_socket(*_a: object, **_k: object) -> None:
    raise AssertionError("不允许联网")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def jsonl(self, name: str, rows: list[dict]) -> Path:
        path = self.dir / name
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return path


class EnrichTests(Base):
    def _enrich(self, rows: list[dict], host: Path | None, **kwargs: object) -> tuple[dict, list[dict]]:
        src, dst = self.jsonl("selected.jsonl", rows), self.dir / "enriched.jsonl"
        results = load_host_results(host) if host else None
        with mock.patch.object(socket, "socket", _no_socket):
            summary = lit.enrich_abstracts(src, dst, host_results=results, host_results_name=host.name if host else None, **kwargs)
        return summary, [json.loads(line) for line in dst.read_text(encoding="utf-8").splitlines()]

    def test_fills_from_host_by_title(self) -> None:
        host = _host(self.dir / "abstracts_1_host.json", [(TITLE, [{"title": TITLE, "abstract": FULL, "year": 2014}])])
        summary, rows = self._enrich([{"record_id": "r1", "title": TITLE}], host)
        self.assertEqual((rows[0]["abstract"], rows[0]["abstract_status"]), (FULL, "present"))
        prov = rows[0]["abstract_provenance"]
        self.assertEqual((prov["source"], prov["method"], prov["query"], prov["host_results"]),
                         ("wispaper", "post_selection", TITLE, "abstracts_1_host.json"))
        self.assertEqual((summary["attempted"], summary["filled"], summary["reused"], summary["missing"]), (1, 1, 0, 0))
        self.assertEqual(summary["host_results"], "abstracts_1_host.json")

    def test_snippet_from_host_is_not_a_full_abstract(self) -> None:
        host = _host(self.dir / "h.json", [(TITLE, [{"title": TITLE, "abstract": SNIPPET}])])
        summary, rows = self._enrich([{"record_id": "r1", "title": TITLE}], host)
        self.assertEqual(rows[0]["abstract_status"], "missing")
        self.assertIn("missing_abstract", rows[0]["quality_warnings"])
        self.assertEqual(summary["filled"], 0)

    def test_doi_disagreement_with_same_title_is_accepted_and_marked(self) -> None:
        # 平台实测：期刊版 DOI 与仓储版 DOI 不同，标题逐字相同，摘要应能取用
        host = _host(self.dir / "h.json", [(TITLE, [{"title": TITLE, "abstract": FULL, "doi": "10.1000/other"}])])
        _s, rows = self._enrich([{"record_id": "r1", "title": TITLE, "doi": "10.1000/own"}], host)
        self.assertEqual(rows[0]["abstract_status"], "present")
        self.assertEqual(rows[0]["abstract_provenance"]["matched_by"], "title")
        self.assertEqual(rows[0]["abstract_provenance"]["hit_doi"], "10.1000/other")

    def test_doi_disagreement_with_similar_title_rejects_hit(self) -> None:
        near = TITLE.replace("a", "e", 2)
        host = _host(self.dir / "h.json", [(TITLE, [{"title": near, "abstract": FULL, "doi": "10.1000/other"}])])
        _s, rows = self._enrich([{"record_id": "r1", "title": TITLE, "doi": "10.1000/own"}], host)
        self.assertEqual(rows[0]["abstract_status"], "missing")
        self.assertEqual(rows[0]["abstract_provenance"]["rejected_mismatch"], 1)

    def test_same_doi_other_title_accepted(self) -> None:
        host = _host(self.dir / "h.json", [("q", [{"title": "Another title", "abstract": FULL, "doi": "10.1000/own"}])])
        _s, rows = self._enrich([{"record_id": "r1", "title": TITLE, "identifiers": {"doi": "10.1000/own"}}], host)
        self.assertEqual(rows[0]["abstract_status"], "present")

    def test_truncated_title_matches_by_prefix(self) -> None:
        host = _host(self.dir / "h.json", [(TRUNC.rstrip("…"), [{"title": TRUNC_FULL, "abstract": FULL}])])
        _s, rows = self._enrich([{"record_id": "r1", "title": TRUNC}], host)
        self.assertEqual(rows[0]["abstract"], FULL)

    def test_different_title_is_rejected(self) -> None:
        host = _host(self.dir / "h.json", [("q", [{"title": "Quantum error correction in superconducting qubits", "abstract": FULL}])])
        _s, rows = self._enrich([{"record_id": "r1", "title": TITLE}], host)
        self.assertEqual(rows[0]["abstract_status"], "missing")

    def test_reuse_only_keeps_old_abstract_without_network(self) -> None:
        prior = self.jsonl("prior.jsonl", [{"record_id": "r1", "title": "Earlier paper", "abstract": FULL, "abstract_status": "present"}])
        summary, rows = self._enrich([{"record_id": "r1", "title": "Earlier paper"}, {"record_id": "r2", "title": TITLE}], None, reuse_path=prior)
        self.assertEqual([r["abstract_status"] for r in rows], ["present", "missing"])
        self.assertEqual(rows[0]["abstract_provenance"]["reused_from"], "prior.jsonl")
        self.assertEqual((summary["reused"], summary["attempted"], summary["filled"], summary["missing"]), (1, 1, 0, 1))
        self.assertIsNone(summary["host_results"])
        self.assertEqual(summary["reuse_file"], "prior.jsonl")

    def test_reuse_then_host(self) -> None:
        prior = self.jsonl("prior.jsonl", [{"record_id": "r1", "title": "Earlier paper", "abstract": FULL, "abstract_status": "present"}])
        host = _host(self.dir / "h.json", [(TITLE, [{"title": TITLE, "abstract": FULL}])])
        summary, rows = self._enrich([{"record_id": "r1", "title": "Earlier paper"}, {"record_id": "r2", "title": TITLE}], host, reuse_path=prior)
        self.assertEqual((summary["reused"], summary["attempted"], summary["filled"]), (1, 1, 1))
        self.assertEqual([r["abstract_status"] for r in rows], ["present", "present"])

    def test_reuse_may_be_the_output_file(self) -> None:
        out = self.jsonl("enriched.jsonl", [{"record_id": "r1", "title": TITLE, "abstract": FULL, "abstract_status": "present"}])
        src = self.jsonl("in.jsonl", [{"record_id": "r1", "title": TITLE}])
        summary = lit.enrich_abstracts(src, out, reuse_path=out)
        self.assertEqual(summary["reused"], 1)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8").splitlines()[0])["abstract"], FULL)

    def test_summary_file_written(self) -> None:
        self._enrich([{"record_id": "r1", "title": TITLE}], None)
        data = json.loads((self.dir / "enriched.jsonl.summary.json").read_text(encoding="utf-8"))
        self.assertEqual((data["attempted"], data["filled"], data["reused"]), (1, 0, 0))


class AbstractQueriesTests(Base):
    def test_lists_titles_missing_full_abstracts(self) -> None:
        rows = [
            {"record_id": "a", "title": TITLE},
            {"record_id": "b", "title": "Already complete", "abstract": FULL},
            {"record_id": "c", "title": "  household   food waste separation behavior and the importance of convenience "},
            {"record_id": "d", "title": TRUNC},
            {"record_id": "e", "title": ""},
        ]
        out = self.dir / "q.json"
        summary = lit.abstract_queries(self.jsonl("s.jsonl", rows), out)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["queries"], [TITLE, TRUNC.rstrip("…").strip()])
        self.assertEqual((summary["queries"], summary["no_title"], summary["skipped_reusable"]), (2, 1, 0))

    def test_reuse_skips_already_filled_records(self) -> None:
        prior = self.jsonl("prior.jsonl", [{"record_id": "a", "title": TITLE, "abstract": FULL, "abstract_status": "present"}])
        out = self.dir / "q.json"
        summary = lit.abstract_queries(self.jsonl("s.jsonl", [{"record_id": "a", "title": TITLE}]), out, reuse_path=prior)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["queries"], [])
        self.assertEqual((summary["queries"], summary["skipped_reusable"]), (0, 1))


class CliTests(Base):
    def run_cli(self, *argv: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONPYCACHEPREFIX": str(ROOT / ".bensz-api" / "pycache")}
        return subprocess.run([sys.executable, str(SCRIPTS / "literature.py"), *argv], capture_output=True, text=True, env=env)

    def test_round_trip(self) -> None:
        src = self.jsonl("s.jsonl", [{"record_id": "a", "title": TITLE}])
        q = self.run_cli("abstract-queries", "--input", str(src), "--output", str(self.dir / "q.json"))
        self.assertEqual(q.returncode, 0, q.stderr)
        self.assertEqual(json.loads(q.stdout)["queries"], 1)
        host = _host(self.dir / "h.json", [(TITLE, [{"title": TITLE, "abstract": FULL}])])
        e = self.run_cli("enrich-abstracts", "--input", str(src), "--output", str(self.dir / "o.jsonl"), "--host-results", str(host))
        self.assertEqual(e.returncode, 0, e.stderr)
        self.assertEqual(json.loads(e.stdout)["filled"], 1)
        self.assertEqual(json.loads((self.dir / "o.jsonl").read_text(encoding="utf-8").splitlines()[0])["abstract"], FULL)

    def test_no_offline_switch(self) -> None:
        src = self.jsonl("s.jsonl", [{"record_id": "a", "title": TITLE}])
        r = self.run_cli("enrich-abstracts", "--offline", "--input", str(src), "--output", str(self.dir / "o.jsonl"))
        self.assertEqual(r.returncode, 2)

    def test_bad_inputs_exit_2(self) -> None:
        src = self.jsonl("s.jsonl", [{"record_id": "a", "title": TITLE}])
        bad = self.dir / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        cases = {
            "missing host file": ["enrich-abstracts", "--input", str(src), "--output", str(self.dir / "o.jsonl"), "--host-results", str(self.dir / "absent.json")],
            "invalid host json": ["enrich-abstracts", "--input", str(src), "--output", str(self.dir / "o.jsonl"), "--host-results", str(bad)],
            "queries missing reuse": ["abstract-queries", "--input", str(src), "--output", str(self.dir / "q.json"), "--reuse", str(self.dir / "none.jsonl")],
            "enrich missing reuse": ["enrich-abstracts", "--input", str(src), "--output", str(self.dir / "o2.jsonl"), "--reuse", str(self.dir / "none.jsonl")],
            "missing input": ["abstract-queries", "--input", str(self.dir / "no.jsonl"), "--output", str(self.dir / "q.json")],
        }
        for label, argv in cases.items():
            with self.subTest(label):
                r = self.run_cli(*argv)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("✗", r.stderr)


if __name__ == "__main__":
    unittest.main()
