# tests/research-literature-search/test_rls_enrich_abstracts.py
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/research-literature-search/scripts"))

from candidate_schema import abstract_from_inverted_index  # noqa: E402
from search_runner import enrich_abstracts  # noqa: E402

TITLE = "Peritumoral radiomics for renal mass characterization on CT"
LONG = "This study evaluates a radiomics model built on the peritumoral region of renal masses in a retrospective cohort of patients."
OTHER = "A completely different abstract about liver imaging, written long enough to pass the minimum character threshold for use."


def _run(record: dict, fetchers: dict) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.jsonl", Path(tmp) / "out.jsonl"
        src.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
        summary = enrich_abstracts(src, dst, fetchers=fetchers)
        row = json.loads(dst.read_text(encoding="utf-8").splitlines()[0])
    return summary, row


class EnrichAbstractsMatchTests(unittest.TestCase):
    def test_skips_mismatched_hit_and_takes_matching_one(self) -> None:
        hits = [{"title": "Liver fibrosis staging with ultrasound elastography", "abstract": OTHER},
                {"title": TITLE, "abstract": LONG}]
        summary, row = _run({"title": TITLE}, {"semantic_scholar": lambda q, **k: hits})
        self.assertEqual(row["abstract"], LONG)
        self.assertEqual(row["abstract_status"], "present")
        self.assertEqual(row["abstract_provenance"]["rejected_mismatch"], 1)
        self.assertEqual(summary["filled"], 1)

    def test_all_mismatched_leaves_abstract_missing(self) -> None:
        hits = [{"title": "Liver fibrosis staging", "abstract": OTHER}, {"title": "Another unrelated paper", "abstract": OTHER}]
        fetchers = {"semantic_scholar": lambda q, **k: hits, "openalex": lambda q, **k: hits}
        summary, row = _run({"title": TITLE}, fetchers)
        self.assertEqual(row["abstract_status"], "missing")
        self.assertNotIn("abstract", row)
        self.assertEqual(row["abstract_provenance"]["rejected_mismatch"], 4)
        self.assertEqual(summary["missing"], 1)

    def test_same_doi_accepted_despite_title_difference(self) -> None:
        hits = [{"doi": "10.5555/ABC.123", "title": "Renal mass radiomics, an erratum-free variant title", "abstract": LONG}]
        _, row = _run({"title": TITLE, "doi": "https://doi.org/10.5555/abc.123"}, {"crossref": lambda q, **k: hits})
        self.assertEqual(row["abstract"], LONG)
        self.assertEqual(row["abstract_provenance"]["source"], "crossref")

    def test_existing_abstract_does_not_call_fetchers(self) -> None:
        def boom(q, **k):
            raise AssertionError("fetcher must not be called")
        summary, row = _run({"title": TITLE, "abstract": LONG}, {"crossref": boom, "semantic_scholar": boom, "openalex": boom})
        self.assertEqual(row["abstract_status"], "present")
        self.assertEqual(summary["attempted"], 0)

    def test_openalex_inverted_index_is_rebuilt(self) -> None:
        index: dict[str, list[int]] = {}
        for pos, word in enumerate(LONG.split()):
            index.setdefault(word, []).append(pos)
        hits = [{"title": TITLE, "abstract_inverted_index": index}]
        summary, row = _run({"title": TITLE}, {"openalex": lambda q, **k: hits})
        self.assertEqual(row["abstract"], LONG)
        self.assertEqual(row["abstract_provenance"]["source"], "openalex")
        self.assertEqual(summary["filled"], 1)

    def test_crossref_jats_tags_are_stripped(self) -> None:
        hits = [{"title": TITLE, "doi": "10.5555/x.1", "abstract": f"<jats:title>Abstract</jats:title><jats:p>{LONG}</jats:p>"}]
        _, row = _run({"title": TITLE, "doi": "10.5555/x.1"}, {"crossref": lambda q, **k: hits})
        self.assertNotIn("<", row["abstract"])
        self.assertEqual(row["abstract"], f"Abstract {LONG}")


class InvertedIndexTests(unittest.TestCase):
    def test_rebuilds_in_position_order(self) -> None:
        self.assertEqual(abstract_from_inverted_index({"b": [1], "a": [0]}), "a b")

    def test_empty_or_malformed_gives_empty_string(self) -> None:
        for bad in ({}, None, "x", [1], {"a": "0"}, {"a": [True]}):
            self.assertEqual(abstract_from_inverted_index(bad), "")


if __name__ == "__main__":
    unittest.main()
