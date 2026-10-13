from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import List, Optional, Tuple
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-ref-alignment/scripts"
sys.path.insert(0, str(SCRIPTS))

import online_verify  # noqa: E402


def _recorder(response: Tuple[Optional[dict], Optional[str]], urls: List[str]):
    def fake(url: str, timeout_s: int = 20) -> Tuple[Optional[dict], Optional[str]]:
        urls.append(url)
        return response

    return fake


class CrossrefOnlyTest(unittest.TestCase):
    def test_crossref_hit_is_ok(self) -> None:
        urls: List[str] = []
        fake = _recorder(({"message": {"title": ["Some title"]}}, None), urls)
        with mock.patch.object(online_verify, "_http_get_json", fake):
            res = online_verify.check_doi_online("10.1000/x", "Some title")
        self.assertTrue(res.ok)
        self.assertEqual(res.crossref_title, "Some title")
        self.assertTrue(urls)
        for url in urls:
            self.assertTrue(url.startswith("https://api.crossref.org/"), url)

    def test_crossref_failure_is_not_ok(self) -> None:
        urls: List[str] = []
        fake = _recorder((None, "HTTP 404"), urls)
        with mock.patch.object(online_verify, "_http_get_json", fake):
            res = online_verify.check_doi_online("10.1000/x", "Some title")
        self.assertFalse(res.ok)
        self.assertTrue(urls)
        for url in urls:
            self.assertTrue(url.startswith("https://api.crossref.org/"), url)
        self.assertEqual([k for k in res.to_dict() if k.startswith("openalex")], [])
        self.assertIn("crossref", res.error)

    def test_sources_do_not_mention_openalex(self) -> None:
        for name in ("online_verify.py", "run_ref_alignment.py"):
            text = (SCRIPTS / name).read_text(encoding="utf-8").lower()
            self.assertNotIn("openalex", text, name)


if __name__ == "__main__":
    unittest.main()
