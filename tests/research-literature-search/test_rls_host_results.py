# tests/research-literature-search/test_rls_host_results.py
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/research-literature-search/scripts"
sys.path.insert(0, str(SCRIPTS))

from providers.host_results import adapt_wispaper, doi_from_urls, load_host_results  # noqa: E402
from search_runner import run_search  # noqa: E402
from validate_bundle import validate_bundle  # noqa: E402

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
QUERIES = [
    "peritumoral radiomics ground-glass nodule invasiveness",
    "ground-glass nodule invasive adenocarcinoma deep learning CT",
    "CT reconstruction kernel radiomics feature reproducibility",
    "ground-glass nodule consolidation tumor ratio invasiveness",
    "minimally invasive adenocarcinoma CT texture analysis",
]


class DoiFromUrlsTest(unittest.TestCase):
    def test_real_wispaper_urls(self) -> None:
        self.assertEqual(doi_from_urls("https://ajronline.org/doi/abs/10.2214/ajr.24.31675"), "10.2214/ajr.24.31675")
        self.assertEqual(doi_from_urls("https://link.springer.com/article/10.1007/s00330-021-07948-0"), "10.1007/s00330-021-07948-0")
        self.assertEqual(doi_from_urls("https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2020.00838/full"), "10.3389/fonc.2020.00838")
        self.assertEqual(doi_from_urls("https://ajronline.org/doi/pdf/10.2214/AJR.24.31675"), "10.2214/ajr.24.31675")

    def test_no_doi(self) -> None:
        self.assertIsNone(doi_from_urls("https://pmc.ncbi.nlm.nih.gov/articles/PMC11388221/", None))


class AdaptWispaperTest(unittest.TestCase):
    def test_snippet_abstract_moves_to_provenance(self) -> None:
        raw = adapt_wispaper(QUICK_PAPER)
        self.assertIsNone(raw["abstract"])
        self.assertIn("abstract_snippet_only", raw["quality_warnings"])
        self.assertTrue(raw["provenance"]["host_abstract_snippet"].startswith("…"))
        self.assertEqual(raw["doi"], "10.1007/s00330-021-07948-0")

    def test_full_abstract_kept_and_relevance_recorded(self) -> None:
        raw = adapt_wispaper(DEEP_PAPER)
        self.assertTrue(raw["abstract"].startswith("Background"))
        self.assertEqual(raw["provenance"]["host_relevance"], "perfect")
        self.assertEqual(raw["doi"], "10.1177/0284185119826536")

    def test_truncated_title_flagged(self) -> None:
        raw = adapt_wispaper(TRUNCATED_PAPER)
        self.assertIn("title_truncated", raw["quality_warnings"])
        self.assertIsNone(raw["doi"])


class HostResultsRunTest(unittest.TestCase):
    def _write(self, tmp: Path, payload: dict) -> Path:
        path = tmp / "host.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _queries(self, tmp: Path) -> Path:
        path = tmp / "queries.json"
        path.write_text(json.dumps({"queries": QUERIES}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_load_rejects_wrong_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"schema": "other", "provider": "wispaper", "queries": []})
            with self.assertRaises(ValueError):
                load_host_results(path)

    def test_load_rejects_unknown_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"schema": "rls.host_results.v1", "provider": "other", "queries": []})
            with self.assertRaises(ValueError):
                load_host_results(path)

    def test_host_results_fill_mcp_slot_and_bundle_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            payload = {"schema": "rls.host_results.v1", "provider": "wispaper",
                       "queries": [{"query": QUERIES[0], "tool": "quick_search", "papers": [QUICK_PAPER, TRUNCATED_PAPER]},
                                   {"query": QUERIES[1], "tool": "deep_search", "papers": [DEEP_PAPER]}]}
            host = load_host_results(self._write(base, payload))
            calls: list[str] = []

            def fake_openalex(query: str, **_: object) -> list[dict]:
                calls.append(query)
                return []

            manifest = run_search(
                topic="GGN invasiveness", query_file=self._queries(base), output_dir=base / "bundle",
                provider_order=["mcp", "openalex"], provider_functions={"openalex": fake_openalex},
                max_results_per_query=10, host_results=host,
            )
            self.assertIn(manifest["status"], {"success", "partial_success"})
            mcp_attempts = [a for a in manifest["attempts"] if a["provider"] == "mcp"]
            self.assertEqual([a["status"] for a in mcp_attempts[:2]], ["success", "success"])
            self.assertEqual(mcp_attempts[0]["host_tool"], "wispaper")
            self.assertEqual(mcp_attempts[2]["status"], "skipped")
            self.assertIn(QUERIES[0], calls)  # 结果不足阈值时继续补充
            self.assertEqual(validate_bundle(base / "bundle"), [])
            rows = [json.loads(line) for line in (base / "bundle" / "candidates_deduped.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 3)
            dois = {r["identifiers"]["doi"] for r in rows}
            self.assertIn("10.1007/s00330-021-07948-0", dois)

    def test_without_host_results_mcp_is_skipped_as_before(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            manifest = run_search(
                topic="GGN", query_file=self._queries(base), output_dir=base / "bundle",
                provider_order=["mcp", "openalex"],
                provider_functions={"openalex": lambda q, **_: [{"title": f"paper for {q}", "year": 2020}]},
                max_results_per_query=5,
            )
            mcp = [a for a in manifest["attempts"] if a["provider"] == "mcp"]
            self.assertTrue(mcp and all(a["status"] == "skipped" and a["reason"] == "host tool required" for a in mcp))

    def test_injected_provider_outside_supported_set_is_called(self) -> None:
        calls: list[str] = []

        def fake(query: str, **_: object) -> list[dict]:
            calls.append(query)
            return [{"title": f"custom paper for {query}", "year": 2021}]

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            manifest = run_search(
                topic="GGN", query_file=self._queries(base), output_dir=base / "bundle",
                provider_order=["custom_source"],
                provider_functions={"custom_source": fake},
                max_results_per_query=5,
            )
            self.assertTrue(calls)
            attempts = [a for a in manifest["attempts"] if a["provider"] == "custom_source"]
            self.assertTrue(attempts and all(a["status"] == "success" for a in attempts))
            lines = (base / "bundle" / "candidates_normalized.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertTrue(any("custom paper for" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
