"""文献池：wispaper 宿主结果适配、去重、pool 命令。不联网。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import literature_records as lr  # noqa: E402

# 2026-10-09 对肺结节题目实测的 wispaper 返回（节选、字段原样）
QUICK_PAPER = {
    "abstract": "… region to distinguish the invasiveness of pulmonary nodules, to predict … compared to peritumoral radiomics 2 mm from the nodule. …",
    "arxiv_id": None,
    "authors": ["L Wu", "C Gao", "J Ye", "J Tao", "N Wang", "P Pang", "P Xiang"],
    "citations": 40, "doi": None, "flags": {"perfect": False}, "paper_id": None, "pdf_url": None,
    "source_url": "https://link.springer.com/article/10.1007/s00330-021-07948-0",
    "title": "The value of various peritumoral radiomic features in differentiating the invasiveness of adenocarcinoma manifesting as ground-glass nodules",
    "url": "https://link.springer.com/article/10.1007/s00330-021-07948-0", "venue": None, "year": 2021,
}
DEEP_PAPER = {
    "abstract": "Background Differentiating histological invasiveness of lung adenocarcinoma that manifest as pure ground-glass nodules (pGGNs) is challenging. Purpose To investigate the value of computerized texture analysis.",
    "arxiv_id": None,
    "authors": ["Yang Yang", "Wei-Wei Wang", "Yan Ren"],
    "doi": "10.1177/0284185119826536", "flags": {"no": False, "partial": False, "perfect": True},
    "paper_id": None, "pdf_url": None,
    "source_url": "https://journals.sagepub.com/doi/abs/10.1177/0284185119826536",
    "title": "Computerized texture analysis predicts histological invasiveness within lung adenocarcinoma manifesting as pure ground-glass nodules",
    "url": "https://journals.sagepub.com/doi/abs/10.1177/0284185119826536",
    "venue": "Acta radiologica (Stockholm, Sweden : 1987)", "year": 2019,
}
TRUNCATED_PAPER = {
    "abstract": "… intratumoral and peritumoral radiomics combined with computed tomography (CT) features …",
    "authors": ["Y Wang", "D Lyu"], "doi": None, "flags": {"perfect": False}, "pdf_url": None,
    "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11388221/",
    "title": "… radiomics combined with computed tomography features for predicting the invasiveness of lung adenocarcinoma presenting as a subpleural ground-glass …",
    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11388221/", "venue": None, "year": 2024,
}
Q1, Q2, Q3 = "peritumoral radiomics ground-glass nodule invasiveness", "ground-glass nodule deep learning CT", "texture analysis adenocarcinoma"


def host_payload(entries: list[tuple[str, list[dict]]]) -> dict:
    return {"schema": "rls.host_results.v1", "provider": "wispaper",
            "queries": [{"query": q, "tool": "quick_search", "papers": papers} for q, papers in entries]}


class DoiFromUrlsTest(unittest.TestCase):
    def test_real_wispaper_urls(self) -> None:
        self.assertEqual(lr.doi_from_urls("https://ajronline.org/doi/abs/10.2214/ajr.24.31675"), "10.2214/ajr.24.31675")
        self.assertEqual(lr.doi_from_urls("https://link.springer.com/article/10.1007/s00330-021-07948-0"), "10.1007/s00330-021-07948-0")
        self.assertEqual(lr.doi_from_urls("https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2020.00838/full"), "10.3389/fonc.2020.00838")
        self.assertEqual(lr.doi_from_urls("https://ajronline.org/doi/pdf/10.2214/AJR.24.31675"), "10.2214/ajr.24.31675")

    def test_no_doi(self) -> None:
        self.assertIsNone(lr.doi_from_urls("https://pmc.ncbi.nlm.nih.gov/articles/PMC11388221/", None))


class AdaptWispaperTest(unittest.TestCase):
    def test_snippet_abstract_moves_to_provenance(self) -> None:
        raw = lr.adapt_wispaper(QUICK_PAPER)
        self.assertIsNone(raw["abstract"])
        self.assertIn("abstract_snippet_only", raw["quality_warnings"])
        self.assertTrue(raw["provenance"]["host_abstract_snippet"].startswith("…"))
        self.assertEqual(raw["doi"], "10.1007/s00330-021-07948-0")

    def test_full_abstract_kept_and_relevance_recorded(self) -> None:
        raw = lr.adapt_wispaper(DEEP_PAPER)
        self.assertTrue(raw["abstract"].startswith("Background"))
        self.assertEqual(raw["provenance"]["host_relevance"], "perfect")

    def test_truncated_title_flagged(self) -> None:
        raw = lr.adapt_wispaper(TRUNCATED_PAPER)
        self.assertIn("title_truncated", raw["quality_warnings"])
        self.assertIsNone(raw["doi"])


class NormalizeAndDedupeTest(unittest.TestCase):
    def test_record_fields_for_bib_resolve(self) -> None:
        rec = lr.normalize_record(lr.adapt_wispaper(DEEP_PAPER), query_id=Q1, rank=1, fallback_index=1)
        self.assertEqual(rec["schema_version"], "rls.paper.v1")
        self.assertEqual(rec["identifiers"]["doi"], "10.1177/0284185119826536")
        self.assertEqual(rec["doi"], "10.1177/0284185119826536")
        self.assertEqual(rec["record_id"], "doi:10.1177/0284185119826536")
        self.assertEqual((rec["year"], rec["abstract_status"]), (2019, "present"))
        self.assertEqual(rec["query_matches"], [Q1])
        self.assertEqual(lr.validate_candidate(rec), [])

    def test_title_record_id_is_deterministic(self) -> None:
        a = lr.normalize_record(lr.adapt_wispaper(TRUNCATED_PAPER), query_id=Q1, rank=1, fallback_index=3)
        b = lr.normalize_record(lr.adapt_wispaper(TRUNCATED_PAPER), query_id=Q2, rank=5, fallback_index=3)
        self.assertTrue(a["record_id"].startswith("title:"))
        self.assertEqual(a["record_id"], b["record_id"])

    def test_snippet_stays_out_of_abstract(self) -> None:
        rec = lr.normalize_record(lr.adapt_wispaper(QUICK_PAPER), query_id=Q1)
        self.assertIsNone(rec["abstract"])
        self.assertEqual(rec["abstract_status"], "missing")
        self.assertIn("missing_abstract", rec["quality_warnings"])
        self.assertTrue(rec["provenance"]["host_abstract_snippet"].startswith("…"))

    def test_empty_title_rejected(self) -> None:
        with self.assertRaises(ValueError):
            lr.normalize_record({"title": "  "})

    def test_dedupe_by_doi_then_title_year(self) -> None:
        a = lr.normalize_record(lr.adapt_wispaper(DEEP_PAPER), query_id="a", fallback_index=1)
        b = lr.normalize_record(lr.adapt_wispaper({**DEEP_PAPER, "abstract": None}), query_id="b", fallback_index=2)
        other = dict(DEEP_PAPER, doi=None, url=None, source_url=None, year=2020, title=DEEP_PAPER["title"].upper())
        c = lr.normalize_record(lr.adapt_wispaper(other), query_id="c", fallback_index=3)
        far = dict(other, year=2015)
        d = lr.normalize_record(lr.adapt_wispaper(far), query_id="d", fallback_index=4)
        out, edges = lr.dedupe_records([a, b, c, d])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["query_matches"], ["a", "b", "c"])
        self.assertEqual([e["reason"] for e in edges], ["same_doi", "fuzzy_title_year"])


class HostLoadTest(unittest.TestCase):
    def _write(self, payload: dict) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "host.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_rejects_wrong_schema_and_provider(self) -> None:
        with self.assertRaises(ValueError):
            lr.load_host_results(self._write({"schema": "other", "provider": "wispaper", "queries": []}))
        with self.assertRaises(ValueError):
            lr.load_host_results(self._write({"schema": "rls.host_results.v1", "provider": "other", "queries": []}))

    def test_groups_by_query(self) -> None:
        got = lr.load_host_results(self._write(host_payload([(Q1, [QUICK_PAPER]), (Q2, [])])))
        self.assertEqual(list(got), [Q1, Q2])
        self.assertEqual(len(got[Q1]), 1)


class PoolCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "nsfc-proposal/output/wispaper").mkdir(parents=True)

    def host(self, name: str, entries: list[tuple[str, list[dict]]]) -> Path:
        path = self.root / f"nsfc-proposal/output/wispaper/{name}_host.json"
        path.write_text(json.dumps(host_payload(entries), ensure_ascii=False), encoding="utf-8")
        return path

    def run_cli(self, *argv: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONPYCACHEPREFIX": str(ROOT / ".bensz-api" / "pycache")}
        return subprocess.run([sys.executable, str(SCRIPTS / "literature.py"), "pool", "--task-root", str(self.root), *argv],
                              capture_output=True, text=True, env=env)

    def pool_dir(self, name: str) -> Path:
        return self.root / "nsfc-proposal/output/literature" / name

    def rows(self, name: str) -> list[dict]:
        text = (self.pool_dir(name) / "candidates.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def manifest(self, name: str) -> dict:
        return json.loads((self.pool_dir(name) / "manifest.json").read_text(encoding="utf-8"))

    def test_two_hosts_merge_one_doi_one_row(self) -> None:
        a = self.host("a", [(Q1, [DEEP_PAPER, QUICK_PAPER])])
        self.host("b", [(Q2, [dict(DEEP_PAPER, abstract=None)])])
        r = self.run_cli("--name", "a", "--name", "b")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.rows("a")
        self.assertEqual(len(rows), 2)
        deep = next(x for x in rows if x["identifiers"]["doi"] == "10.1177/0284185119826536")
        self.assertEqual(deep["query_matches"], sorted([Q1, Q2]))
        m = self.manifest("a")
        self.assertEqual((m["schema"], m["status"], m["max_per_query"]), ("nsfc-proposal.literature_pool.v1", "success", 20))
        self.assertEqual((m["counts"]["before_dedupe"], m["counts"]["after_dedupe"]), (3, 2))
        self.assertEqual([h["name"] for h in m["hosts"]], ["a", "b"])
        self.assertEqual(len(m["hosts"][0]["sha256"]), 64)
        self.assertEqual({q["query"]: q["papers"] for q in m["queries"]}, {Q1: 2, Q2: 1})
        self.assertTrue(a.is_file())

    def test_out_name_and_max_per_query(self) -> None:
        self.host("a", [(Q1, [DEEP_PAPER, QUICK_PAPER, TRUNCATED_PAPER])])
        r = self.run_cli("--name", "a", "--out", "pool1", "--max-per-query", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.rows("pool1")), 2)
        q = self.manifest("pool1")["queries"][0]
        self.assertEqual((q["papers"], q["used"]), (3, 2))
        self.assertEqual(self.manifest("pool1")["max_per_query"], 2)

    def test_one_empty_query_is_partial_success(self) -> None:
        self.host("a", [(Q1, [DEEP_PAPER]), (Q2, [])])
        r = self.run_cli("--name", "a")
        self.assertEqual(r.returncode, 0, r.stderr)
        m = self.manifest("a")
        self.assertEqual(m["status"], "partial_success")
        self.assertEqual(m["empty_queries"], [Q2])
        self.assertIn(Q2, r.stderr)

    def test_all_empty_is_failed_exit_1_with_empty_candidates(self) -> None:
        self.host("a", [(Q1, []), (Q2, [])])
        r = self.run_cli("--name", "a")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.manifest("a")["status"], "failed")
        self.assertEqual((self.pool_dir("a") / "candidates.jsonl").read_text(encoding="utf-8"), "")
        self.assertEqual(sorted(p.name for p in self.pool_dir("a").iterdir()), ["candidates.jsonl", "manifest.json"])

    def test_out_outside_task_root_is_usage_error(self) -> None:
        self.host("a", [(Q1, [DEEP_PAPER])])
        for bad in ("../x", "a/b", "a\\b", ".."):
            with self.subTest(bad):
                r = self.run_cli("--name", "a", "--out", bad)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("✗", r.stderr)
        self.assertFalse((self.root / "nsfc-proposal/output/x").exists())
        self.assertFalse((self.root / "x").exists())

    def test_bad_name_is_usage_error(self) -> None:
        r = self.run_cli("--name", "../a")
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_missing_host_file_is_usage_error(self) -> None:
        r = self.run_cli("--name", "nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("nope_host.json", r.stderr)

    def test_wrong_schema_is_usage_error(self) -> None:
        path = self.root / "nsfc-proposal/output/wispaper/bad_host.json"
        path.write_text(json.dumps({"schema": "other", "provider": "wispaper", "queries": []}), encoding="utf-8")
        r = self.run_cli("--name", "bad")
        self.assertEqual(r.returncode, 2)
        self.assertIn("schema", r.stderr)

    def test_missing_task_root_is_usage_error(self) -> None:
        env = {**os.environ, "PYTHONPYCACHEPREFIX": str(ROOT / ".bensz-api" / "pycache")}
        r = subprocess.run([sys.executable, str(SCRIPTS / "literature.py"), "pool", "--task-root", str(self.root / "none"), "--name", "a"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2)

    def test_rerun_is_stable_for_record_ids(self) -> None:
        self.host("a", [(Q1, [QUICK_PAPER, TRUNCATED_PAPER, DEEP_PAPER])])
        self.run_cli("--name", "a")
        first = [r["record_id"] for r in self.rows("a")]
        self.run_cli("--name", "a")
        self.assertEqual(first, [r["record_id"] for r in self.rows("a")])

    def test_snippet_abstract_not_stored_as_abstract(self) -> None:
        self.host("a", [(Q1, [QUICK_PAPER])])
        self.run_cli("--name", "a")
        row = self.rows("a")[0]
        self.assertIsNone(row["abstract"])
        self.assertEqual(row["abstract_status"], "missing")
        self.assertTrue(row["provenance"]["host_abstract_snippet"].startswith("…"))
        for key in ("record_id", "title", "authors", "year", "publication", "sources", "query_matches", "quality_warnings", "provenance"):
            self.assertIn(key, row)
        self.assertEqual(row["identifiers"]["doi"], "10.1007/s00330-021-07948-0")


if __name__ == "__main__":
    unittest.main()
