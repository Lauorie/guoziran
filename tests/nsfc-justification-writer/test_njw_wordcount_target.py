"""wordcount 的默认字数目标对齐立项依据预算 4500–10000 字，并可读 --info-form。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/nsfc-justification-writer/scripts/run.py"


def run_wordcount(cwd: Path, *args: str) -> dict:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
    env.pop("NSFC_JUSTIFICATION_WRITER_RUNS_DIR", None)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--no-user-override", "wordcount", *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


class WordcountTargetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.proj = self.base / "proj"
        (self.proj / "extraTex").mkdir(parents=True)
        (self.proj / "extraTex" / "1.1.立项依据.tex").write_text("研究背景\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _form(self, text: str) -> Path:
        path = self.base / "form.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_default_matches_budget(self) -> None:
        out = run_wordcount(self.base, "--project-root", str(self.proj))
        self.assertEqual((out["target"], out["tolerance"], out["source"]), (7250, 2750, "config_default"))

    def test_info_form_range_is_used(self) -> None:
        form = self._form("字数限制：4500–10000 字\n")
        out = run_wordcount(self.base, "--project-root", str(self.proj), "--info-form", str(form))
        self.assertEqual((out["target"], out["tolerance"], out["source"]), (7250, 2750, "info_form"))

    def test_info_form_without_word_spec_falls_back(self) -> None:
        form = self._form("项目名称：示例\n")
        out = run_wordcount(self.base, "--project-root", str(self.proj), "--info-form", str(form))
        self.assertEqual((out["target"], out["tolerance"], out["source"]), (7250, 2750, "config_default"))


if __name__ == "__main__":
    unittest.main()
