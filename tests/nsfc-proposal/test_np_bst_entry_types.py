"""gbt7714-nsfc.bst 能排版 bib_resolve 写出的每种条目类型。需要 bibtex，不联网。"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BST_DIR = ROOT / "packages/bensz-nsfc/assets/bibtex-style"

ENTRIES = {
    "article": ("Alpha Article Title", "journal = {Journal of Test}"),
    "inproceedings": ("Beta Proceedings Title", "booktitle = {Proceedings of Test}"),
    "incollection": ("Gamma Chapter Title", "booktitle = {Test Handbook}, publisher = {Test Press}"),
    "book": ("Delta Book Title", "publisher = {Test Press}"),
    "misc": ("Epsilon Misc Title", "howpublished = {Test Venue}"),
    "phdthesis": ("Zeta Doctoral Title", "school = {Test University}"),
    "mastersthesis": ("Eta Masters Title", "school = {Test University}"),
}


@unittest.skipUnless(shutil.which("bibtex"), "bibtex not installed")
class BstEntryTypesTest(unittest.TestCase):
    def test_every_entry_type_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            bib = "".join(f"@{kind}{{key_{kind},\n  author = {{Tester, Alice}},\n  title = {{{title}}},\n"
                          f"  year = {{2020}},\n  {extra},\n}}\n" for kind, (title, extra) in ENTRIES.items())
            (work / "refs.bib").write_text(bib, encoding="utf-8")
            (work / "t.aux").write_text("\\citation{*}\n\\bibstyle{gbt7714-nsfc}\n\\bibdata{refs}\n", encoding="utf-8")
            env = dict(os.environ, BSTINPUTS=f"{BST_DIR}:")
            subprocess.run(["bibtex", "t"], cwd=work, env=env, capture_output=True, check=False, timeout=60)
            blg = (work / "t.blg").read_text(encoding="utf-8", errors="replace")
            bbl = (work / "t.bbl").read_text(encoding="utf-8", errors="replace")
        for kind, (title, _) in ENTRIES.items():
            with self.subTest(kind=kind):
                self.assertNotIn(f"Unsupported entry type for key_{kind}", blg)
                self.assertNotIn(f'Warning--entry type for "key_{kind}"', blg)
                self.assertIn(title, bbl)


if __name__ == "__main__":
    unittest.main()
