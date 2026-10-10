"""refs、review、coach 的 --out 指向不存在的目录时，先建目录再写。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/nsfc-justification-writer/scripts/run.py"


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
    env.pop("NSFC_JUSTIFICATION_WRITER_RUNS_DIR", None)
    return subprocess.run([sys.executable, str(SCRIPT), "--no-user-override", *args],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=120)


class OutDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.proj = self.base / "proj"
        (self.proj / "extraTex").mkdir(parents=True)
        (self.proj / "extraTex" / "1.1.立项依据.tex").write_text("\\subsubsection{研究背景}\n正文。\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_out_creates_missing_directories(self) -> None:
        for command in ("coach", "review", "refs"):
            with self.subTest(command=command):
                out = self.base / "out" / command / "nested" / f"{command}.md"
                proc = run_cli(self.base, command, "--project-root", str(self.proj), "--out", str(out))
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertTrue(out.is_file())
                self.assertIn("已输出", proc.stdout)

    def test_out_into_existing_directory_still_works(self) -> None:
        out = self.base / "coach.md"
        proc = run_cli(self.base, "coach", "--project-root", str(self.proj), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
