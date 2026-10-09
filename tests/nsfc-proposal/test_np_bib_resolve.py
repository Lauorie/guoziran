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
from bib_resolve import CROSSREF_WORKS, OPENALEX_WORKS, USER_AGENT, WorkMeta, make_bibkey, run, title_matches, to_bibtex  # noqa: E402

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
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status_code = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

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

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _records(self, *rows: dict) -> Path:
        self.records.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return self.records

    def _run(self, session: FakeSession, *rows: dict) -> dict:
        return run(self.root, self._records(*rows), self.task, session=session)

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


class HelperTest(unittest.TestCase):
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
