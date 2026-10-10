"""bib_refresh：按台账 DOI 重新取 CrossRef 元数据，原 key 重写条目，台账追加 add 事件。不联网。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import bib_refresh  # noqa: E402
from bib_resolve import CROSSREF_WORKS, USER_AGENT, crossref_meta, to_bibtex  # noqa: E402
from citation_ledger import add_event, append_event, audit, load_ledger, register_user_entries  # noqa: E402
from latex_files import bib_entry_texts  # noqa: E402
from proposal_common import proposal_paths  # noqa: E402

KEY = "tester2024peritumoral"
DOI = "10.5555/nsfc.test.001"
DOI_URL = f"{CROSSREF_WORKS}/{DOI}"
TITLE = "Peritumoral texture and invasiveness of test nodules in a multicenter cohort study"
ITEM = {"DOI": "10.5555/NSFC.TEST.001", "title": [TITLE], "author": [{"family": "Tester", "given": "Alice"}],
        "container-title": ["Waste Management &amp; Research"], "issued": {"date-parts": [[2024]]},
        "volume": "7", "issue": "2", "page": "100-110", "type": "journal-article"}
CLEAN = to_bibtex(crossref_meta({**ITEM, "container-title": ["Waste Management & Research"]}), KEY)
OLD = CLEAN.replace("\\&", "\\&amp;")
OTHER = "@article{other2020x,\n  title = {{Other}},\n  year = {2020},\n}\n"
USER = "@article{user2019y,\n  title = {{User paper}},\n  year = {2019},\n  doi = {10.5555/user.1},\n}\n"
ABSTRACT = "This abstract is long enough to be stored in the citation ledger for the refreshed test entry here."
PROVENANCE = {"record_id": "doi:10.5555/nsfc.test.001", "record_title": TITLE, "query_matches": ["q01"],
              "host_tool": "wispaper", "provider": "mcp"}


class FakeResponse:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status_code, self.headers, self._payload = status, {}, payload

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


class RefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "proj"
        (self.root / "references").mkdir(parents=True)
        (self.root / "proposal").mkdir()
        (self.root / "main.tex").write_text("\\input{references/reference.tex}\n", encoding="utf-8")
        (self.root / "references" / "reference.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
        self.bib = self.root / "references" / "refs.bib"
        self.task = base / ".bensz-api" / "task-20261010-1200-test"
        self.ledger = proposal_paths(self.root).ledger
        self.waits: list[float] = []
        self._write_bib(OLD)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_bib(self, entry: str) -> None:
        self.bib.write_text(OTHER + "\n" + entry + "\n" + USER, encoding="utf-8")
        if self.ledger.exists():
            self.ledger.unlink()
        texts = bib_entry_texts([self.bib])
        append_event(self.ledger, add_event("other2020x", source="crossref", entry_text=texts["other2020x"], doi=None,
                                            abstract=None, provenance={"record_id": "r0"}))
        append_event(self.ledger, add_event(KEY, source="crossref", entry_text=texts[KEY], doi=DOI, abstract=ABSTRACT,
                                            provenance=PROVENANCE))
        register_user_entries(self.root, ["user2019y"])

    def _snapshot(self) -> tuple[str, str]:
        return self.bib.read_text(encoding="utf-8"), self.ledger.read_text(encoding="utf-8")

    def _refresh(self, session: FakeSession, *keys: str) -> dict:
        return bib_refresh.refresh(self.root, self.task, list(keys) or [KEY], session=session, sleep=self.waits.append)

    def _main(self, *keys: str) -> int:
        args = ["--project-root", str(self.root), "--task-root", str(self.task)]
        for key in keys:
            args += ["--key", key]
        return bib_refresh.main(args)

    def test_refresh_rewrites_entry_keeps_key_and_passes_audit(self) -> None:
        other_before = bib_entry_texts([self.bib])["other2020x"]
        session = FakeSession({DOI_URL: FakeResponse(200, {"message": ITEM})})
        summary = self._refresh(session)
        self.assertEqual(summary["counts"], {"refreshed": 1, "unchanged": 0, "failed": 0})
        text = self.bib.read_text(encoding="utf-8")
        self.assertIn(f"@article{{{KEY},", text)
        self.assertIn("journal = {Waste Management \\& Research}", text)
        self.assertNotIn("amp;", text)
        self.assertEqual(bib_entry_texts([self.bib])["other2020x"], other_before)
        self.assertEqual(audit(self.root), ([], []))
        record = load_ledger(self.ledger)[KEY]
        self.assertEqual((record["event"], record["reason"], record["abstract"], record["provenance"]),
                         ("add", "refresh", ABSTRACT, PROVENANCE))
        self.assertTrue(summary["backups"])
        self.assertTrue(all(Path(p).is_file() for p in summary["backups"]))
        self.assertTrue((self.task / "nsfc-proposal" / "output" / "bib_refresh.json").is_file())
        url, params, headers = session.calls[0]
        self.assertEqual(headers.get("User-Agent"), USER_AGENT)
        self.assertNotIn("mailto", json.dumps([url, params, headers]))

    def test_unchanged_entry_writes_nothing(self) -> None:
        self._write_bib(CLEAN)
        before = self._snapshot()
        summary = self._refresh(FakeSession({DOI_URL: FakeResponse(200, {"message": ITEM})}))
        self.assertEqual(summary["counts"], {"refreshed": 0, "unchanged": 1, "failed": 0})
        self.assertEqual(summary["backups"], [])
        self.assertEqual(self._snapshot(), before)

    def test_network_failure_leaves_entry_and_ledger(self) -> None:
        before = self._snapshot()
        summary = self._refresh(FakeSession({DOI_URL: requests.ConnectionError("down")}))
        self.assertEqual(summary["counts"], {"refreshed": 0, "unchanged": 0, "failed": 1})
        self.assertIn("CrossRef DOI 查询失败", summary["outcomes"][0]["reason"])
        self.assertEqual(self._snapshot(), before)

    def test_title_mismatch_fails_and_leaves_entry(self) -> None:
        before = self._snapshot()
        other = {**ITEM, "title": ["Cardiac strain imaging in an unrelated cohort of adults"]}
        summary = self._refresh(FakeSession({DOI_URL: FakeResponse(200, {"message": other})}))
        self.assertEqual(summary["outcomes"][0]["status"], "failed")
        self.assertIn("标题", summary["outcomes"][0]["reason"])
        self.assertEqual(self._snapshot(), before)

    def test_cli_exit_codes(self) -> None:
        with mock.patch.object(bib_refresh.requests, "Session", return_value=FakeSession({})):
            self.assertEqual(self._main(KEY), 1)  # CrossRef 404：刷新失败，条目不动
        with mock.patch.object(bib_refresh.requests, "Session", return_value=FakeSession({DOI_URL: FakeResponse(200, {"message": ITEM})})):
            self.assertEqual(self._main(KEY), 0)
        self.assertNotIn("amp;", self.bib.read_text(encoding="utf-8"))

    def test_keys_that_cannot_be_refreshed_exit_2_without_writing(self) -> None:
        before = self._snapshot()
        for bad in ("user2019y", "missing2000z", "other2020x"):  # 申请人登记、不在 .bib、台账无 DOI
            with self.subTest(key=bad):
                self.assertEqual(self._main(KEY, bad), 2)
                self.assertEqual(self._snapshot(), before)
        self.assertFalse((self.task / "nsfc-proposal" / "output" / "bib_refresh.json").exists())

    def test_task_root_must_be_task_dir(self) -> None:
        args = ["--project-root", str(self.root), "--task-root", str(self.root), "--key", KEY]
        self.assertEqual(bib_refresh.main(args), 2)


if __name__ == "__main__":
    unittest.main()
