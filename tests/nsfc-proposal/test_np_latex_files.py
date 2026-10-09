from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/nsfc-proposal/scripts"))

from latex_files import normalize_doi, read_bib_index, relpath, scan_latex_tree  # noqa: E402
from proposal_common import ProposalError, append_under_heading, project_path, split_latex_comment  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class SplitCommentTest(unittest.TestCase):
    def test_escaped_percent_is_not_comment(self) -> None:
        self.assertEqual(split_latex_comment("占比 50\\% 的病例 % 待补"), ("占比 50\\% 的病例 ", " 待补"))

    def test_double_backslash_then_percent_is_comment(self) -> None:
        self.assertEqual(split_latex_comment("换行\\\\% 注释"), ("换行\\\\", " 注释"))

    def test_no_comment(self) -> None:
        self.assertEqual(split_latex_comment("正文"), ("正文", ""))


class LatexTreeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        write(self.root / "main.tex",
              "\\input{extraTex/@config.tex}\n"
              "\\input{extraTex/1.1.立项依据.tex}\n"
              "% \\input{extraTex/old.tex}\n"
              "\\input{references/reference.tex}\n"
              "\\input{../../outside}\n")
        write(self.root / "extraTex" / "@config.tex", "% config\n")
        write(self.root / "extraTex" / "1.1.立项依据.tex", "正文\n")
        write(self.root / "extraTex" / "old.tex", "旧\n")
        write(self.root / "references" / "reference.tex", "\\bibliography{references/myexample}\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_follows_inputs_and_finds_bib_in_input_file(self) -> None:
        tree = scan_latex_tree(self.root)
        self.assertEqual([relpath(self.root, p) for p in tree.tex_files],
                         ["main.tex", "extraTex/@config.tex", "extraTex/1.1.立项依据.tex", "references/reference.tex"])
        self.assertEqual([relpath(self.root, p) for p in tree.bib_files], ["references/myexample.bib"])

    def test_comma_list_and_addbibresource(self) -> None:
        write(self.root / "references" / "reference.tex",
              "\\bibliography{refs/a, refs/b.bib}\n\\addbibresource[label=x]{refs/c.bib}\n")
        tree = scan_latex_tree(self.root)
        self.assertEqual([relpath(self.root, p) for p in tree.bib_files], ["refs/a.bib", "refs/b.bib", "refs/c.bib"])

    def test_missing_main_tex(self) -> None:
        (self.root / "main.tex").unlink()
        with self.assertRaises(ProposalError):
            scan_latex_tree(self.root)

    def test_real_nsfc_young_template(self) -> None:
        template = ROOT / "projects" / "NSFC_Young"
        tree = scan_latex_tree(template)
        compiled = {relpath(template, p) for p in tree.tex_files}
        self.assertIn("extraTex/1.1.立项依据.tex", compiled)
        self.assertNotIn("extraTex/4.5.生成式人工智能.tex", compiled)
        self.assertEqual([relpath(template, p) for p in tree.bib_files], ["references/myexample.bib"])


class BibIndexTest(unittest.TestCase):
    def test_keys_and_doi_spellings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bib = write(Path(tmp) / "refs.bib",
                        "@comment{ignored, text}\n"
                        "@ARTICLE{John1997,\n  DOI = {https://doi.org/10.1007/S00330-021-07948-0},\n}\n"
                        "@article{yang2019computerized,\n  doi = \"10.1177/0284185119826536\",\n}\n"
                        "@article{nodoi2020,\n  title = {No DOI},\n}\n"
                        "@article{under2021,\n  doi = {10.1000/abc\\_def},\n}")
            index = read_bib_index([bib, Path(tmp) / "absent.bib"])
            self.assertEqual(index.keys, frozenset({"John1997", "yang2019computerized", "nodoi2020", "under2021"}))
            self.assertEqual(index.doi_keys["10.1007/s00330-021-07948-0"], "John1997")
            self.assertIn("10.1177/0284185119826536", index.dois)
            self.assertIn("10.1000/abc_def", index.dois)

    def test_normalize_doi(self) -> None:
        self.assertEqual(normalize_doi("https://dx.doi.org/10.3389/FONC.2020.00838."), "10.3389/fonc.2020.00838")
        self.assertEqual(normalize_doi("doi: 10.2214/AJR.24.31675"), "10.2214/ajr.24.31675")
        self.assertIsNone(normalize_doi(""))


class ProjectPathTest(unittest.TestCase):
    def test_escape_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProposalError):
                project_path(Path(tmp), "../etc/passwd")


class AppendUnderHeadingTest(unittest.TestCase):
    def test_appends_in_order_under_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "a.md", "# 标题\n\n## 确认点状态\n\n## AI 拟定项\n")
            append_under_heading(path, "## 确认点状态", "- 第一条")
            append_under_heading(path, "## 确认点状态", "- 第二条")
            self.assertEqual(path.read_text(encoding="utf-8"),
                             "# 标题\n\n## 确认点状态\n\n- 第一条\n- 第二条\n\n## AI 拟定项\n")

    def test_creates_missing_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "a.md", "# 标题\n")
            append_under_heading(path, "## 未核实线索", "- [unverified] X")
            self.assertEqual(path.read_text(encoding="utf-8"), "# 标题\n\n## 未核实线索\n\n- [unverified] X\n")


if __name__ == "__main__":
    unittest.main()
