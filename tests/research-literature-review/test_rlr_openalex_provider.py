from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "research-literature-review"
SEARCH_SCRIPTS = SKILL_ROOT.parent / "research-literature-search" / "scripts"
sys.path.insert(0, str(SEARCH_SCRIPTS))
from candidate_schema import normalize_record  # noqa: E402  (before review scripts: both dirs hold dedupe_papers)

sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import multi_query_search  # noqa: E402
import openalex_provider  # noqa: E402

WORK = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.1000/ABC.123",
    "title": "Deep learning for pulmonary nodule classification",
    "display_name": "Deep learning for pulmonary nodule classification",
    "publication_year": 2020,
    "type": "article",
    "authorships": [{"author": {"display_name": "Wei Zhang"}}, {"author": {"display_name": "Li Na"}}],
    "primary_location": {"source": {"display_name": "Radiology"}, "landing_page_url": "https://example.org/x"},
    "open_access": {"is_oa": True},
    "abstract_inverted_index": {"We": [0], "study": [1], "lung": [2], "nodules": [3], "again": [4]},
}


def _write_queries(path: Path) -> None:
    queries = [{"query": f"query {i}", "rationale": f"reason {i}"} for i in range(1, 6)]
    path.write_text(json.dumps({"queries": queries}), encoding="utf-8")


class OpenAlexConversionTests(unittest.TestCase):
    def test_converted_work_normalizes_to_expected_record(self) -> None:
        # Expected values were taken from normalize_record(WORK, provider="openalex")
        # while research-literature-search still read OpenAlex works directly.
        record = normalize_record(openalex_provider._to_raw(WORK), provider="openalex")
        self.assertEqual(record["title"], "Deep learning for pulmonary nodule classification")
        self.assertEqual(record["authors"], ["Wei Zhang", "Li Na"])
        self.assertEqual(record["year"], 2020)
        self.assertEqual(record["venue"], "Radiology")
        self.assertEqual(record["identifiers"]["doi"], "10.1000/abc.123")
        self.assertEqual(record["sources"][0]["provider_record_id"], "https://openalex.org/W2741809807")
        self.assertEqual(len(record["authorships"]), 2)
        self.assertIsNone(record["url"])
        self.assertEqual(record["abstract"], "We study lung nodules again")
        self.assertEqual(record["abstract_status"], "present")
        self.assertIs(record["publication"]["is_open_access"], True)
        self.assertEqual(record["publication"]["publication_type"], "article")

    def test_open_access_falls_back_to_primary_location(self) -> None:
        work = {"id": "W2", "display_name": "T", "primary_location": {"is_oa": True}}
        record = normalize_record(openalex_provider._to_raw(work), provider="openalex")
        self.assertIs(record["publication"]["is_open_access"], True)

    def test_missing_fields_become_none(self) -> None:
        raw = openalex_provider._to_raw({"id": "W1", "display_name": "Only a title"})
        self.assertEqual(raw["title"], "Only a title")
        self.assertEqual(raw["authors"], [])
        self.assertIsNone(raw["doi"])
        self.assertIsNone(raw["abstract"])
        self.assertIsNone(raw["venue"])
        self.assertIsNone(raw["url"])

    def test_search_returns_generic_fields_and_keeps_request_params(self) -> None:
        response = MagicMock()
        response.json.return_value = {"results": [WORK]}
        session = MagicMock()
        session.get.return_value = response
        rows = openalex_provider.search("q", max_results=5, min_year=2019, max_year=2021, mailto="a@b.c", session=session)
        params = session.get.call_args.kwargs["params"]
        self.assertEqual(params["filter"], "from_publication_date:2019-01-01,to_publication_date:2021-12-31")
        self.assertEqual(params["mailto"], "a@b.c")
        self.assertEqual(rows[0]["doi"], "10.1000/ABC.123")
        self.assertEqual(rows[0]["authors"], ["Wei Zhang", "Li Na"])


class OpenAlexInjectionTests(unittest.TestCase):
    def test_wrapper_uses_local_adapter(self) -> None:
        self.assertIs(multi_query_search.search_openalex, openalex_provider.search)

    def test_in_process_interface_injects_openalex(self) -> None:
        # run_search is stubbed: multi_search reads its bundle through _read_jsonl,
        # which is undefined (existing bug, outside this change).
        fake = MagicMock(return_value=[openalex_provider._to_raw(WORK)])
        captured: dict = {}

        def stub_run_search(**kwargs):
            captured.update(kwargs)
            return {}

        with patch.object(multi_query_search, "search_openalex", fake), patch.object(multi_query_search, "run_search", stub_run_search):
            queries = [{"query": f"query {i}", "rationale": f"reason {i}"} for i in range(1, 6)]
            multi_query_search.multi_search(queries, 5, None, None, None)
        self.assertIs(captured["provider_functions"]["openalex"], fake)
        captured["provider_functions"]["openalex"]("q")
        self.assertTrue(fake.called)

    def test_bundle_dir_cli_injects_openalex(self) -> None:
        self._run_cli(["--provider-order", "openalex"])

    def test_bundle_dir_cli_default_order_calls_openalex(self) -> None:
        # Simulate research-literature-search dropping openalex from its default order.
        with patch("search_runner.DEFAULT_PROVIDER_ORDER", ["semantic_scholar", "crossref"]):
            self._run_cli([])

    def _run_cli(self, extra: list[str]) -> None:
        # Five rows fill max_results_per_query, so no other provider is tried.
        rows_in = [dict(openalex_provider._to_raw(WORK), title=f"{WORK['title']} {i}", doi=None) for i in range(5)]
        fake = MagicMock(return_value=rows_in)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write_queries(base / "queries.json")
            argv = ["multi_query_search.py", "--queries", str(base / "queries.json"), "--output", str(base / "out.jsonl"),
                    "--search-log", str(base / "log.json"), "--bundle-dir", str(base / "bundle"), "--scope-root", str(base),
                    "--max-results-per-query", "5", *extra]
            with patch.object(multi_query_search, "search_openalex", fake), patch.object(sys, "argv", argv):
                code = multi_query_search.main()
            self.assertEqual(code, 0)
            self.assertTrue(fake.called)
            rows = (base / "out.jsonl").read_text(encoding="utf-8")
            self.assertIn(WORK["title"] + " 0", rows)


if __name__ == "__main__":
    unittest.main()
