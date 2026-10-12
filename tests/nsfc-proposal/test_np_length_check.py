"""length_check：只统计被编译的文件、按配置预算判断、报告写到当前目录下的 --out-dir。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/nsfc-proposal/scripts/length_check.py"
TEMPLATE = ROOT / "skills/nsfc-proposal/assets/length_report_template.md"

MAIN_TEX = (
    "\\documentclass{article}\n\\begin{document}\n"
    "\\input{extraTex/1.1.立项依据.tex}\n"
    "% \\input{extraTex/2.1.研究内容.tex}\n"
    "\\end{document}\n"
)


def _make_project(base: Path) -> Path:
    project = base / "proj"
    (project / "extraTex").mkdir(parents=True)
    (project / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (project / "extraTex/1.1.立项依据.tex").write_text(
        "\\section{背景}\n" + "字" * 120 + "% 注释里的字不计\n", encoding="utf-8"
    )
    (project / "extraTex/2.1.研究内容.tex").write_text("字" * 300, encoding="utf-8")
    return project


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )


class LengthCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.project = _make_project(self.tmp)

    def test_template_asset_exists(self) -> None:
        self.assertTrue(TEMPLATE.is_file())
        self.assertIn("{{file_table}}", TEMPLATE.read_text(encoding="utf-8"))

    def test_counts_only_uncommented_includes(self) -> None:
        out = self.tmp / "out"
        cp = _run(["--input", str(self.project), "--out-dir", str(out)], self.tmp)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        report = json.loads((out / "length_report.json").read_text(encoding="utf-8"))
        paths = [f["path"] for f in report["files"]]
        self.assertIn("extraTex/1.1.立项依据.tex", paths)
        self.assertNotIn("extraTex/2.1.研究内容.tex", paths)
        self.assertEqual(report["discovery"]["mode"], "latex_inputs")
        self.assertTrue((out / "length_report.md").is_file())
        self.assertIn("OK: total cjk_chars=", cp.stdout)

    def test_short_justification_is_below_budget(self) -> None:
        out = self.tmp / "out"
        _run(["--input", str(self.project), "--out-dir", str(out)], self.tmp)
        report = json.loads((out / "length_report.json").read_text(encoding="utf-8"))
        item = next(f for f in report["files"] if "立项依据" in f["path"])
        self.assertEqual(item["budget"]["min"], 4500)
        self.assertLess(item["value"], item["budget"]["min"])
        md = (out / "length_report.md").read_text(encoding="utf-8")
        self.assertIn(f"-{4500 - item['value']}", md)

    def test_relative_out_dir_resolves_from_cwd_not_input(self) -> None:
        cwd = self.tmp / "elsewhere"
        cwd.mkdir()
        cp = _run(["--input", str(self.project), "--out-dir", "rel/out"], cwd)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertTrue((cwd / "rel/out/length_report.md").is_file())
        self.assertTrue((cwd / "rel/out/length_report.json").is_file())
        leftovers = [p for p in self.project.rglob("length_report.*")]
        self.assertEqual(leftovers, [])
        self.assertFalse((self.project / "rel").exists())

    def test_out_dir_is_required(self) -> None:
        cp = _run(["--input", str(self.project)], self.tmp)
        self.assertEqual(cp.returncode, 2)
        self.assertIn("--out-dir", cp.stderr)

    def test_config_option_is_gone(self) -> None:
        cp = _run(["--input", str(self.project), "--out-dir", "o", "--config", "x.yaml"], self.tmp)
        self.assertEqual(cp.returncode, 2)

    def test_missing_input_exits_2(self) -> None:
        cp = _run(["--input", str(self.tmp / "nope"), "--out-dir", "o"], self.tmp)
        self.assertEqual(cp.returncode, 2)

    def test_fail_if_exists(self) -> None:
        out = self.tmp / "out"
        args = ["--input", str(self.project), "--out-dir", str(out), "--fail-if-exists"]
        self.assertEqual(_run(args, self.tmp).returncode, 0)
        self.assertEqual(_run(args, self.tmp).returncode, 2)

    def test_script_has_no_sibling_references(self) -> None:
        for name in ("length_check.py", "length_tex.py"):
            text = (SCRIPT.parent / name).read_text(encoding="utf-8")
            self.assertNotIn("nsfc-length-aligner", text)
            self.assertNotIn("output_settings", text)


if __name__ == "__main__":
    unittest.main()
