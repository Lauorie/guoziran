"""gbt7714-nsfc.bst 能排版 bib_resolve 写出的每种条目类型。需要 bibtex，不联网。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BST_DIR = ROOT / "packages/bensz-nsfc/assets/bibtex-style"

sys.path.insert(0, str(ROOT / "skills/nsfc-proposal/scripts"))

import bib_resolve  # noqa: E402
from bib_resolve import WorkMeta  # noqa: E402

TITLES = {
    "article": "Alpha Article Title",
    "inproceedings": "Beta Proceedings Title",
    "incollection": "Gamma Chapter Title",
    "book": "Delta Book Title",
    "misc": "Epsilon Misc Title",
    "phdthesis": "Zeta Doctoral Title",
    "mastersthesis": "Eta Masters Title",
}
VENUES = {"article": "Journal of Test", "inproceedings": "Proceedings of Test", "incollection": "Test Handbook",
          "misc": "Test Venue"}


def _meta(kind: str) -> WorkMeta:
    return WorkMeta(title=TITLES[kind], authors=(("Tester", "Alice"),), journal=VENUES.get(kind), year=2020,
                    volume=None, issue=None, pages=None, doi=None, entry_type=kind, publisher="Test Press")


@unittest.skipUnless(shutil.which("bibtex"), "bibtex not installed")
class BstEntryTypesTest(unittest.TestCase):
    def test_every_entry_type_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            bib = "\n".join(bib_resolve.to_bibtex(_meta(kind), f"key_{kind}") for kind in TITLES)
            (work / "refs.bib").write_text(bib, encoding="utf-8")
            (work / "t.aux").write_text("\\citation{*}\n\\bibstyle{gbt7714-nsfc}\n\\bibdata{refs}\n", encoding="utf-8")
            env = dict(os.environ, BSTINPUTS=f"{BST_DIR}:")
            subprocess.run(["bibtex", "t"], cwd=work, env=env, capture_output=True, check=False, timeout=60)
            blg = (work / "t.blg").read_text(encoding="utf-8", errors="replace")
            bbl = (work / "t.bbl").read_text(encoding="utf-8", errors="replace")
        for kind, title in TITLES.items():
            with self.subTest(kind=kind):
                self.assertNotIn(f"Unsupported entry type for key_{kind}", blg)
                self.assertNotIn(f'Warning--entry type for "key_{kind}"', blg)
                self.assertIn(title, bbl)


if __name__ == "__main__":
    unittest.main()
