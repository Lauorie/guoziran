from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-ref-alignment/scripts"
sys.path.insert(0, str(SCRIPTS))

from bib_utils import BibEntry  # noqa: E402
from run_ref_alignment import _entry_digest  # noqa: E402


def _venue(entry_type: str, **fields: str) -> str:
    entry = BibEntry(key="k", entry_type=entry_type, fields=fields, source="refs.bib")
    return _entry_digest(entry, Path("."), {})["venue"]


class EntryDigestVenueTest(unittest.TestCase):
    def test_thesis_venue_is_school(self) -> None:
        self.assertEqual(_venue("phdthesis", school="Test University", title="T"), "Test University")

    def test_journal_comes_first(self) -> None:
        self.assertEqual(_venue("article", journal="Journal of Test", school="X", title="T"), "Journal of Test")


if __name__ == "__main__":
    unittest.main()
