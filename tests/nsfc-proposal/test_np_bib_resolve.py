from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import bib_resolve  # noqa: E402
from bib_resolve import CROSSREF_WORKS, OPENALEX_WORKS, USER_AGENT, WorkMeta, crossref_meta, make_bibkey, openalex_meta, run, title_matches, to_bibtex  # noqa: E402

TITLE_1 = "Peritumoral texture and invasiveness of test nodules in a multicenter cohort study"
CROSSREF_ITEM_1 = {
    "DOI": "10.5555/NSFC.TEST.001", "title": [TITLE_1],
    "author": [{"family": "Tester", "given": "Alice"}, {"family": "Example", "given": "Bob"}],
    "container-title": ["Journal of Test Imaging"], "issued": {"date-parts": [[2024]]},
    "volume": "7", "issue": "2", "page": "100-110", "type": "journal-article",
}
OPENALEX_ITEM_3 = {
    "title": "Reconstruction kernels & texture stability in test scans", "doi": "https://doi.org/10.5555/nsfc.test.003",
    "publication_year": 2022, "authorships": [{"author": {"display_name": "Carol Sample"}}],
    "primary_location": {"source": {"display_name": "Test Physics Letters"}},
    "biblio": {"volume": "3", "issue": None, "first_page": "11", "last_page": "19"},
}


class FakeResponse:
    def __init__(self, status: int, payload: Any = None, headers: dict | None = None) -> None:
        self.status_code = status
        self.headers = headers or {}
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """按 URL 返回固定响应；未登记的 URL 返回 404；登记为异常时抛出。"""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict, dict]] = []

    def get(self, url: str, params: Any = None, headers: Any = None, timeout: Any = None) -> FakeResponse:
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        value = self.routes.get(url)
        if isinstance(value, Exception):
            raise value
        return value if value is not None else FakeResponse(404)


class SequenceSession(FakeSession):
    """同一 URL 依次返回列表中的响应或抛出其中的异常；用尽后重复最后一项；未登记的 URL 返回 404。"""

    def get(self, url: str, params: Any = None, headers: Any = None, timeout: Any = None) -> FakeResponse:
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        queue = self.routes.get(url)
        if not queue:
            return FakeResponse(404)
        value = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(value, Exception):
            raise value
        return value


def doi_url(doi: str) -> str:
    return f"{CROSSREF_WORKS}/{doi}"


class ResolveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "proj"
        (self.root / "references").mkdir(parents=True)
        (self.root / "proposal").mkdir()
        (self.root / "main.tex").write_text("\\input{references/reference.tex}\n", encoding="utf-8")
        (self.root / "references" / "reference.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
        self.bib = self.root / "references" / "refs.bib"
        self.bib.write_text("@article{old2020,\n  title = {Old},\n}\n", encoding="utf-8")
        (self.root / "proposal" / "literature_leads.md").write_text("# 文献线索\n\n## 检索式\n\n## 未核实线索\n", encoding="utf-8")
        self.task = base / ".bensz-api" / "task-20261009-1200-test"
        self.records = base / "selected.jsonl"
        self.waits: list[float] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _records(self, *rows: dict) -> Path:
        self.records.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return self.records

    def _run(self, session: FakeSession, *rows: dict) -> dict:
        return run(self.root, self._records(*rows), self.task, session=session, sleep=self.waits.append)

    def test_doi_record_added_with_backup(self) -> None:
        session = FakeSession({doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1})})
        summary = self._run(session, {"record_id": "r1", "title": TITLE_1, "year": 2024, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["counts"], {"added": 1, "exists": 0, "unresolved": 0})
        self.assertEqual(summary["outcomes"][0]["bibkey"], "tester2024peritumoral")
        text = self.bib.read_text(encoding="utf-8")
        self.assertIn("@article{tester2024peritumoral,", text)
        self.assertIn("author = {Tester, Alice and Example, Bob}", text)
        self.assertIn("pages = {100--110}", text)
        self.assertIn("doi = {10.5555/nsfc.test.001}", text)
        self.assertTrue(Path(summary["backup"]).is_file())
        self.assertTrue((self.task / "nsfc-proposal" / "output" / "bib_resolve.json").is_file())

    def test_existing_doi_reuses_key_without_request(self) -> None:
        self.bib.write_text("@article{mine2024,\n  doi = {https://doi.org/10.5555/NSFC.TEST.001},\n}\n", encoding="utf-8")
        before = self.bib.read_text(encoding="utf-8")
        session = FakeSession({})
        summary = self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["outcomes"][0]["status"], "exists")
        self.assertEqual(summary["outcomes"][0]["bibkey"], "mine2024")
        self.assertEqual(session.calls, [])
        self.assertEqual(self.bib.read_text(encoding="utf-8"), before)
        self.assertIsNone(summary["backup"])

    def test_truncated_title_matches_by_fragment(self) -> None:
        session = FakeSession({CROSSREF_WORKS: FakeResponse(200, {"message": {"items": [CROSSREF_ITEM_1]}})})
        summary = self._run(session, {"record_id": "r2", "title": "… texture and invasiveness of test nodules in a multicenter cohort …", "year": 2024})
        self.assertEqual(summary["outcomes"][0]["status"], "added")
        self.assertEqual(summary["outcomes"][0]["source"], "crossref")

    def test_openalex_fallback(self) -> None:
        unrelated = dict(CROSSREF_ITEM_1, title=["Something else entirely about cardiac imaging"])
        session = FakeSession({
            CROSSREF_WORKS: FakeResponse(200, {"message": {"items": [unrelated]}}),
            OPENALEX_WORKS: FakeResponse(200, {"results": [OPENALEX_ITEM_3]}),
        })
        summary = self._run(session, {"record_id": "r3", "title": "Reconstruction kernels & texture stability in test scans", "year": 2022})
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["source"]), ("added", "openalex"))
        text = self.bib.read_text(encoding="utf-8")
        self.assertIn("title = {{Reconstruction kernels \\& texture stability in test scans}}", text)
        self.assertIn("author = {Sample, Carol}", text)
        self.assertIn("doi = {10.5555/nsfc.test.003}", text)

    def _openalex_only_routes(self) -> dict:
        unrelated = dict(CROSSREF_ITEM_1, title=["Something else entirely about cardiac imaging"])
        return {
            CROSSREF_WORKS: FakeResponse(200, {"message": {"items": [unrelated]}}),
            OPENALEX_WORKS: FakeResponse(200, {"results": [OPENALEX_ITEM_3]}),
        }

    def test_openalex_doi_goes_back_to_crossref_for_metadata(self) -> None:
        routes = self._openalex_only_routes()
        authoritative = {"DOI": "10.5555/NSFC.TEST.003", "title": [OPENALEX_ITEM_3["title"]],
                         "author": [{"family": "Sample", "given": "Carol"}], "container-title": ["Test Physics Letters"],
                         "issued": {"date-parts": [[2023]]}, "type": "journal-article"}
        routes[doi_url("10.5555/nsfc.test.003")] = FakeResponse(200, {"message": authoritative})
        summary = self._run(FakeSession(routes), {"record_id": "r3", "title": OPENALEX_ITEM_3["title"], "year": 2022})
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["source"]), ("added", "crossref"))
        self.assertIn("year = {2023}", self.bib.read_text(encoding="utf-8"))

    def test_openalex_doi_crossref_404_keeps_openalex_metadata(self) -> None:
        summary = self._run(FakeSession(self._openalex_only_routes()), {"record_id": "r3", "title": OPENALEX_ITEM_3["title"], "year": 2022})
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["source"]), ("added", "openalex"))
        self.assertIn("year = {2022}", self.bib.read_text(encoding="utf-8"))

    def test_network_failure_goes_to_leads_and_bib_untouched(self) -> None:
        before = self.bib.read_text(encoding="utf-8")
        error = requests.ConnectionError("offline")
        session = FakeSession({doi_url("10.5555/nsfc.test.001"): error, CROSSREF_WORKS: error, OPENALEX_WORKS: error})
        summary = self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["counts"]["unresolved"], 1)
        self.assertIn("ConnectionError", summary["outcomes"][0]["reason"])
        self.assertEqual(self.bib.read_text(encoding="utf-8"), before)
        self.assertIsNone(summary["backup"])
        leads = (self.root / "proposal" / "literature_leads.md").read_text(encoding="utf-8")
        self.assertIn("- [unverified] " + TITLE_1, leads)

    def test_server_error_does_not_stop_other_records(self) -> None:
        session = FakeSession({
            doi_url("10.5555/nsfc.test.009"): FakeResponse(503),
            CROSSREF_WORKS: FakeResponse(503),
            OPENALEX_WORKS: FakeResponse(503),
            doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1}),
        })
        summary = self._run(session,
                            {"record_id": "bad", "title": "Unreachable test paper title for server error", "identifiers": {"doi": "10.5555/nsfc.test.009"}},
                            {"record_id": "good", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["counts"], {"added": 1, "exists": 0, "unresolved": 1})

    def test_append_keeps_entries_separated_without_trailing_newline(self) -> None:
        self.bib.write_text("@article{old2020,\n  title = {Old},\n}", encoding="utf-8")
        session = FakeSession({doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1})})
        self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertIn("}\n\n@article{tester2024peritumoral,", self.bib.read_text(encoding="utf-8"))

    def test_doi_with_mismatched_title_is_unresolved(self) -> None:
        session = FakeSession({doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1})})
        summary = self._run(session, {"record_id": "r4", "title": "A completely different study of liver lesions in rats", "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["outcomes"][0]["status"], "unresolved")
        self.assertIn("不符", summary["outcomes"][0]["reason"])

    def test_requests_carry_no_personal_identity(self) -> None:
        session = FakeSession({CROSSREF_WORKS: FakeResponse(200, {"message": {"items": []}})})
        self._run(session, {"record_id": "r5", "title": "Some test title that will not match anything at all"})
        for _, params, headers in session.calls:
            self.assertEqual(headers.get("User-Agent"), USER_AGENT)
            self.assertNotIn("mailto", json.dumps([params, headers]))

    def test_rate_limit_then_success_is_added(self) -> None:
        url = doi_url("10.5555/nsfc.test.001")
        session = SequenceSession({url: [FakeResponse(429), FakeResponse(200, {"message": CROSSREF_ITEM_1})]})
        summary = self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["counts"], {"added": 1, "exists": 0, "unresolved": 0})
        self.assertEqual(self.waits, [2.0])

    def test_persistent_503_is_unresolved_with_status_in_reason(self) -> None:
        url = doi_url("10.5555/nsfc.test.001")
        responses = [FakeResponse(503)] * 4
        session = SequenceSession({url: responses, CROSSREF_WORKS: [FakeResponse(404)], OPENALEX_WORKS: [FakeResponse(404)]})
        summary = self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["counts"]["unresolved"], 1)
        self.assertIn("503", summary["outcomes"][0]["reason"])
        self.assertEqual(self.waits, [2.0, 4.0, 8.0])
        self.assertEqual(sum(1 for c in session.calls if c[0] == url), 4)

    def test_retry_after_header_sets_the_wait(self) -> None:
        url = doi_url("10.5555/nsfc.test.001")
        session = SequenceSession({url: [FakeResponse(429, headers={"Retry-After": "5"}), FakeResponse(200, {"message": CROSSREF_ITEM_1})]})
        self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(self.waits, [5.0])

    def test_retry_after_over_a_minute_falls_back_to_backoff(self) -> None:
        url = doi_url("10.5555/nsfc.test.001")
        session = SequenceSession({url: [FakeResponse(429, headers={"Retry-After": "600"}), FakeResponse(200, {"message": CROSSREF_ITEM_1})]})
        self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(self.waits, [2.0])

    def test_timeout_is_retried(self) -> None:
        url = doi_url("10.5555/nsfc.test.001")
        session = SequenceSession({url: [requests.Timeout("slow"), FakeResponse(200, {"message": CROSSREF_ITEM_1})]})
        summary = self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(summary["counts"]["added"], 1)

    def test_404_is_not_retried(self) -> None:
        session = SequenceSession({})
        self._run(session, {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}})
        self.assertEqual(self.waits, [])

    def test_dry_run_writes_own_summary_and_keeps_real_one(self) -> None:
        row = {"record_id": "r1", "title": TITLE_1, "identifiers": {"doi": "10.5555/nsfc.test.001"}}
        session = FakeSession({doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1})})
        out = self.task / "nsfc-proposal" / "output"
        self._run(session, row)
        before = (out / "bib_resolve.json").read_text(encoding="utf-8")
        run(self.root, self._records(row), self.task, session=session, sleep=self.waits.append, dry_run=True)
        self.assertEqual((out / "bib_resolve.json").read_text(encoding="utf-8"), before)
        dry = json.loads((out / "bib_resolve.dryrun.json").read_text(encoding="utf-8"))
        self.assertTrue(dry["dry_run"])
        self.assertEqual(dry["counts"]["exists"], 1)


class HelperTest(unittest.TestCase):
    def test_crossref_book_chapter_becomes_incollection(self) -> None:
        item = {"type": "book-chapter", "title": ["Divergent Thinking as a Process"], "author": [{"family": "Doe", "given": "Jane"}],
                "container-title": ["Handbook of Test Methods"], "publisher": "Test Press", "page": "3-16",
                "issued": {"date-parts": [[2023]]}, "DOI": "10.1000/ch1"}
        meta = crossref_meta(item)
        self.assertEqual((meta.entry_type, meta.publisher), ("incollection", "Test Press"))
        entry = to_bibtex(meta, "k")
        self.assertTrue(entry.startswith("@incollection{k,"))
        self.assertIn("booktitle = {Handbook of Test Methods}", entry)
        self.assertIn("publisher = {Test Press}", entry)
        self.assertNotIn("howpublished", entry)

    def test_crossref_book_and_other_types(self) -> None:
        book = crossref_meta({"type": "monograph", "title": ["A Book"], "publisher": "P", "issued": {"date-parts": [[2020]]}})
        self.assertEqual(book.entry_type, "book")
        self.assertIn("publisher = {P}", to_bibtex(book, "b"))
        other = crossref_meta({"type": "dataset", "title": ["Some Data"], "container-title": ["Data Hub"], "publisher": "Hub Inc"})
        entry = to_bibtex(other, "d")
        self.assertTrue(entry.startswith("@misc{d,"))
        self.assertIn("publisher = {Hub Inc}", entry)
        self.assertIn("howpublished = {Data Hub}", entry)

    def test_chapter_without_container_or_publisher_does_not_fail(self) -> None:
        meta = crossref_meta({"type": "book-chapter", "title": ["Lonely Chapter"], "issued": {"date-parts": [[2021]]}})
        entry = to_bibtex(meta, "c")
        self.assertTrue(entry.startswith("@incollection{c,"))
        self.assertNotIn("booktitle", entry)
        self.assertNotIn("publisher", entry)

    def test_openalex_book_chapter(self) -> None:
        item = {"title": "Chapter T", "type": "book-chapter", "publication_year": 2019,
                "primary_location": {"source": {"display_name": "Book B", "host_organization_name": "Pub P"}}}
        meta = openalex_meta(item)
        self.assertEqual((meta.entry_type, meta.journal, meta.publisher), ("incollection", "Book B", "Pub P"))

    def test_article_entry_ignores_publisher(self) -> None:
        item = {"type": "journal-article", "title": ["T"], "container-title": ["J"], "publisher": "Elsevier"}
        self.assertNotIn("publisher", to_bibtex(crossref_meta(item), "a"))

    def test_bibkey_collision_and_escape(self) -> None:
        meta = WorkMeta(title="The & test", authors=(("Tëster", "Ann"),), journal="J % Test", year=2024, volume=None, issue=None, pages=None, doi=None)
        taken = {"tester2024test"}
        self.assertEqual(make_bibkey(meta, taken), "tester2024testa")
        entry = to_bibtex(meta, "k")
        self.assertIn("title = {{The \\& test}}", entry)
        self.assertIn("journal = {J \\% Test}", entry)
        self.assertNotIn("doi =", entry)

    def test_title_matching(self) -> None:
        self.assertTrue(title_matches("Peritumoral texture and invasiveness", "Peritumoral Texture and Invasiveness.", 0.92))
        self.assertFalse(title_matches("Peritumoral texture and invasiveness", "Cardiac strain imaging", 0.92))
        self.assertFalse(title_matches("… short …", "Anything with short in it", 0.92))  # 片段不足 20 字符时不匹配

    def test_escape_markup_and_special_chars(self) -> None:
        meta = WorkMeta(title="Effect of x<sub>2</sub> when p<0.05 and n>3 {unbalanced", authors=(("Test", "Author"),), journal=None, year=2024, volume=None, issue=None, pages=None, doi=None)
        entry = to_bibtex(meta, "k")
        self.assertIn("x2", entry)
        self.assertIn("p<0.05 and n>3", entry)
        self.assertIn(r"\{unbalanced", entry)
        open_count = entry.count("{") - entry.count(r"\{")
        close_count = entry.count("}") - entry.count(r"\}")
        self.assertEqual(open_count, close_count)

    def test_escape_tilde_caret_backslash(self) -> None:
        meta = WorkMeta(title=r"Test ~ caret ^ and backslash \ in title", authors=(("Test", "Author"),), journal=None, year=2024, volume=None, issue=None, pages=None, doi=None)
        entry = to_bibtex(meta, "k")
        self.assertIn(r"\textasciitilde{}", entry)
        self.assertIn(r"\textasciicircum{}", entry)
        self.assertIn(r"\textbackslash{}", entry)

    def test_html_entities_are_decoded_before_latex_escape(self) -> None:
        self.assertEqual(bib_resolve._escape("Waste Management &amp; Research"), r"Waste Management \& Research")
        self.assertEqual(bib_resolve._escape("Memory &amp;amp; Cognition"), r"Memory \& Cognition")
        self.assertEqual(bib_resolve._escape("&lt;i&gt;In vivo&lt;/i&gt; tests of &#39;x&#39;"), "In vivo tests of 'x'")
        self.assertEqual(bib_resolve._escape("Rate &lt; 5 &amp; 10%"), r"Rate < 5 \& 10\%")

    def test_crossref_journal_with_entity_renders_plain_ampersand(self) -> None:
        item = {"type": "journal-article", "title": ["T"], "container-title": ["Accident Analysis &amp; Prevention"]}
        entry = to_bibtex(crossref_meta(item), "a")
        self.assertIn(r"journal = {Accident Analysis \& Prevention}", entry)
        self.assertNotIn("amp;", entry)

    def test_title_matching_ignores_entities(self) -> None:
        self.assertTrue(title_matches("Habits &amp; goals in daily recycling behaviour", "Habits & Goals in Daily Recycling Behaviour", 0.92))

class CliTest(unittest.TestCase):
    def test_task_root_must_be_task_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
            records = Path(tmp) / "r.jsonl"
            records.write_text("", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(SCRIPTS / "bib_resolve.py"), "--project-root", tmp, "--records", str(records),
                                   "--task-root", str(Path(tmp) / "notatask")], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 2)

    def test_task_root_parent_must_be_bensz_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
            records = Path(tmp) / "r.jsonl"
            records.write_text("", encoding="utf-8")
            bad_task = Path(tmp) / "other" / "task-20261009-0000-test"
            proc = subprocess.run([sys.executable, str(SCRIPTS / "bib_resolve.py"), "--project-root", tmp, "--records", str(records),
                                   "--task-root", str(bad_task)], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
