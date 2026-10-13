# tests/research-literature-search/test_rls_enrich_abstracts.py
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/research-literature-search/scripts"))

from search_runner import enrich_abstracts  # noqa: E402

TITLE = "Peritumoral radiomics for renal mass characterization on CT"
LONG = "This study evaluates a radiomics model built on the peritumoral region of renal masses in a retrospective cohort of patients."
OTHER = "A completely different abstract about liver imaging, written long enough to pass the minimum character threshold for use."


def _run(record: dict, fetchers: dict, **kwargs) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.jsonl", Path(tmp) / "out.jsonl"
        src.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
        offline = {name: (lambda q, **k: []) for name in ("crossref", "semantic_scholar")}
        summary = enrich_abstracts(src, dst, fetchers={**offline, **fetchers}, **kwargs)
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

    def test_injected_extra_fetcher_is_tried_by_title_after_builtin_sources(self) -> None:
        calls: list[str] = []

        def extra(query: str, **_k: object) -> list:
            calls.append(query)
            return [{"title": TITLE, "abstract": LONG}]
        _, row = _run({"title": TITLE, "doi": "10.5555/q.1"}, {"extra_source": extra})
        self.assertEqual(calls, [TITLE])
        self.assertEqual(row["abstract"], LONG)
        self.assertEqual(row["abstract_provenance"]["source"], "extra_source")

    def test_all_mismatched_leaves_abstract_missing(self) -> None:
        hits = [{"title": "Liver fibrosis staging", "abstract": OTHER}, {"title": "Another unrelated paper", "abstract": OTHER}]
        fetchers = {"semantic_scholar": lambda q, **k: hits, "crossref": lambda q, **k: hits}
        summary, row = _run({"title": TITLE, "doi": "10.5555/zz.9"}, fetchers)
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
        summary, row = _run({"title": TITLE, "abstract": LONG}, {"crossref": boom, "semantic_scholar": boom})
        self.assertEqual(row["abstract_status"], "present")
        self.assertEqual(summary["attempted"], 0)

    def test_crossref_jats_tags_are_stripped(self) -> None:
        hits = [{"title": TITLE, "doi": "10.5555/x.1", "abstract": f"<jats:title>Abstract</jats:title><jats:p>{LONG}</jats:p>"}]
        _, row = _run({"title": TITLE, "doi": "10.5555/x.1"}, {"crossref": lambda q, **k: hits})
        self.assertNotIn("<", row["abstract"])
        self.assertEqual(row["abstract"], f"Abstract {LONG}")

    def test_rate_limited_fetcher_is_retried(self) -> None:
        calls: list[str] = []
        waits: list[float] = []

        def flaky(q, **k):
            calls.append(q)
            if len(calls) == 1:
                raise RuntimeError("HTTP 429 Too Many Requests")
            return [{"title": TITLE, "abstract": LONG}]
        _, row = _run({"title": TITLE}, {"semantic_scholar": flaky}, sleep=waits.append)
        self.assertEqual(row["abstract"], LONG)
        self.assertEqual(len(calls), 2)
        self.assertEqual(waits, [2.0])

    def test_doi_or_count_ending_in_5xx_is_not_a_rate_limit(self) -> None:
        for message in ("no match for 10.5555/abc.503", "returned 500 items", "bad payload"):
            calls: list[str] = []

            def broken(q, _m=message, **k):
                calls.append(q)
                raise ValueError(_m)
            waits: list[float] = []
            _run({"title": TITLE}, {"semantic_scholar": broken}, sleep=waits.append)
            self.assertEqual((len(calls), waits), (1, []), message)

    def test_explicit_status_forms_are_retried(self) -> None:
        for message in ("HTTP 503 Service Unavailable", "status code 502", "Status: 429"):
            waits: list[float] = []
            state = {"n": 0}

            def flaky(q, _m=message, **k):
                state["n"] += 1
                if state["n"] == 1:
                    raise RuntimeError(_m)
                return []
            _run({"title": TITLE}, {"semantic_scholar": flaky}, sleep=waits.append)
            self.assertEqual(waits, [2.0], message)

    def test_comparison_signs_in_plain_abstracts_survive(self) -> None:
        text = "Sensitivity <90% and specificity >80% were seen in the retrospective renal mass cohort of this study."
        for fetchers in ({"semantic_scholar": lambda q, **k: [{"title": TITLE, "abstract": text}]},
                         {"crossref": lambda q, **k: [{"title": TITLE, "doi": "10.5555/x.1", "abstract": text}]}):
            _, row = _run({"title": TITLE, "doi": "10.5555/x.1"}, fetchers)
            self.assertEqual(row.get("abstract"), text)

    def test_other_errors_are_not_retried(self) -> None:
        calls: list[str] = []
        waits: list[float] = []

        def broken(q, **k):
            calls.append(q)
            raise ValueError("bad payload")
        _, row = _run({"title": TITLE}, {"semantic_scholar": broken}, sleep=waits.append)
        self.assertEqual(len(calls), 1)
        self.assertEqual(waits, [])
        self.assertEqual(row["abstract_status"], "missing")


class _StatusError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__("request failed")
        self.status_code = status


class _ResponseError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__("request failed")
        self.response = type("Resp", (), {"status_code": status})()


def _run_many(records: list[dict], fetchers: dict, **kwargs) -> tuple[dict, list[dict]]:
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.jsonl", Path(tmp) / "out.jsonl"
        src.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
        offline = {name: (lambda q, **k: []) for name in ("crossref", "semantic_scholar")}
        summary = enrich_abstracts(src, dst, fetchers={**offline, **fetchers}, **kwargs)
        rows = [json.loads(line) for line in dst.read_text(encoding="utf-8").splitlines()]
    return summary, rows


class EnrichExhaustedProviderTests(unittest.TestCase):
    RECORDS = [{"title": f"{TITLE} part {n}"} for n in (1, 2, 3)]

    def test_rate_limited_provider_is_skipped_for_later_records(self) -> None:
        for make_error in (lambda: RuntimeError("HTTP 429 Too Many Requests"), lambda: _StatusError(429), lambda: _ResponseError(429)):
            with self.subTest(error=type(make_error()).__name__):
                calls = {"semantic_scholar": 0}

                def semantic(q, _make=make_error, **k):
                    calls["semantic_scholar"] += 1
                    raise _make()
                waits: list[float] = []
                summary, rows = _run_many(self.RECORDS, {"semantic_scholar": semantic}, retries=2, sleep=waits.append)
                self.assertEqual(calls, {"semantic_scholar": 3})
                self.assertEqual(waits, [2.0, 4.0])
                self.assertEqual(summary["exhausted_providers"], ["semantic_scholar"])
                self.assertEqual(rows[0]["abstract_provenance"]["attempts"][-1]["status"], "error")
                for row in rows[1:]:
                    self.assertIn({"source": "semantic_scholar", "status": "skipped_exhausted"}, row["abstract_provenance"]["attempts"])

    def test_server_error_is_not_counted_as_exhausted(self) -> None:
        calls: list[str] = []

        def semantic(q, **k):
            calls.append(q)
            raise RuntimeError("HTTP 500 Internal Server Error")
        summary, rows = _run_many(self.RECORDS[:2], {"semantic_scholar": semantic}, retries=2, sleep=lambda s: None)
        self.assertEqual(len(calls), 6)
        self.assertEqual(summary["exhausted_providers"], [])
        for row in rows:
            self.assertNotIn("skipped_exhausted", [a["status"] for a in row["abstract_provenance"]["attempts"]])

    def test_no_failures_gives_empty_exhausted_list(self) -> None:
        summary, _ = _run_many(self.RECORDS[:1], {})
        self.assertEqual(summary["exhausted_providers"], [])

    def test_filled_attempt_count_excludes_skipped_providers(self) -> None:
        def crossref(q, **k):
            raise RuntimeError("HTTP 429 Too Many Requests")
        semantic = lambda q, **k: [{"title": q, "abstract": LONG}]  # noqa: E731
        records = [{**r, "doi": "10.5555/a.1"} for r in self.RECORDS[:2]]
        summary, rows = _run_many(records, {"crossref": crossref, "semantic_scholar": semantic}, sleep=lambda s: None)
        self.assertEqual(summary["exhausted_providers"], ["crossref"])
        self.assertEqual([row["abstract_provenance"]["attempts"] for row in rows], [2, 1])

    def test_only_first_status_in_message_counts(self) -> None:
        calls: list[str] = []

        def semantic(q, **k):
            calls.append(q)
            raise RuntimeError("HTTP 503 Service Unavailable after HTTP 429")
        summary, _ = _run_many(self.RECORDS[:2], {"semantic_scholar": semantic}, retries=2, sleep=lambda s: None)
        self.assertEqual(len(calls), 6)
        self.assertEqual(summary["exhausted_providers"], [])


SCRIPT = ROOT / "skills/research-literature-search/scripts/search_runner.py"


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class EnrichReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src, self.prior, self.dst = self.base / "in.jsonl", self.base / "prior.jsonl", self.base / "out.jsonl"
        _write_rows(self.src, [{"record_id": "doi:10.5555/a", "title": TITLE},
                               {"record_id": "title:other", "title": "Another paper about household sorting habits"}])
        self.calls: list[str] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _fetchers(self) -> dict:
        def fetch(q, **k):
            self.calls.append(q)
            return []
        return {name: fetch for name in ("crossref", "semantic_scholar")}

    def test_prior_abstract_reused_by_record_id_without_request(self) -> None:
        _write_rows(self.prior, [{"record_id": "doi:10.5555/a", "title": TITLE, "abstract": LONG, "abstract_status": "present",
                                  "abstract_provenance": {"source": "semantic_scholar", "method": "post_selection"}}])
        summary = enrich_abstracts(self.src, self.dst, fetchers=self._fetchers(), reuse_path=self.prior)
        rows = _read_rows(self.dst)
        self.assertEqual((rows[0]["abstract"], rows[0]["abstract_status"]), (LONG, "present"))
        self.assertEqual(rows[0]["abstract_provenance"], {"source": "semantic_scholar", "method": "post_selection", "reused_from": "prior.jsonl"})
        self.assertNotIn(TITLE, self.calls)
        self.assertEqual((summary["reused"], summary["attempted"], summary["reuse_file"]), (1, 1, "prior.jsonl"))

    def test_prior_without_usable_abstract_is_not_reused(self) -> None:
        _write_rows(self.prior, [{"record_id": "doi:10.5555/a", "title": TITLE, "abstract": None, "abstract_status": "missing"},
                                 {"record_id": "title:other", "abstract": "too short", "abstract_status": "present"}])
        summary = enrich_abstracts(self.src, self.dst, fetchers=self._fetchers(), reuse_path=self.prior)
        self.assertEqual((summary["reused"], summary["attempted"]), (0, 2))
        self.assertIn(TITLE, self.calls)

    def test_reuse_file_may_be_the_output_file(self) -> None:
        _write_rows(self.dst, [{"record_id": "doi:10.5555/a", "title": TITLE, "abstract": LONG, "abstract_status": "present"}])
        summary = enrich_abstracts(self.src, self.dst, fetchers=self._fetchers(), reuse_path=self.dst)
        rows = _read_rows(self.dst)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["abstract"], LONG)
        self.assertEqual(summary["reused"], 1)

    def test_without_reuse_summary_reports_zero(self) -> None:
        summary = enrich_abstracts(self.src, self.dst, fetchers=self._fetchers())
        self.assertEqual((summary["reused"], summary["reuse_file"]), (0, None))

    def test_cli_missing_reuse_file_exits_2(self) -> None:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        proc = subprocess.run([sys.executable, str(SCRIPT), "enrich-abstracts", "--input", str(self.src), "--output", str(self.dst),
                               "--reuse", str(self.base / "missing.jsonl")], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertFalse(self.dst.exists())


if __name__ == "__main__":
    unittest.main()
