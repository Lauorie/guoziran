from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/nsfc-justification-writer/scripts/run.py"
SKILL_DIR = "nsfc-justification-writer"


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
    env.pop("NSFC_JUSTIFICATION_WRITER_RUNS_DIR", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--no-user-override", *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


class TaskRootTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_task_root_fixes_runs_dir(self) -> None:
        task = self.base / ".bensz-api" / "task-20261009-1200-demo"
        proc = run_cli(self.base, "--task-root", str(task), "init", "--run-id", "init_20261009120000")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((task / SKILL_DIR / "init_20261009120000" / "inputs" / "info_form.md").is_file())

    def test_task_root_requires_task_prefix(self) -> None:
        proc = run_cli(self.base, "--task-root", str(self.base / "elsewhere"), "init")
        self.assertEqual(proc.returncode, 2)

    def test_diff_locates_run_in_earlier_task_dir(self) -> None:
        project = self.base / "proj"
        target = project / "extraTex" / "1.1.立项依据.tex"
        target.parent.mkdir(parents=True)
        target.write_text("新正文\n", encoding="utf-8")
        backup = (self.base / ".bensz-api" / "task-20261009-1159-nsfc-justification-writer" / SKILL_DIR
                  / "auto_20261009115900" / "backup" / "extraTex" / "1.1.立项依据.tex")
        backup.parent.mkdir(parents=True)
        backup.write_text("旧正文\n", encoding="utf-8")
        proc = run_cli(self.base, "diff", "--project-root", str(project), "--run-id", "auto_20261009115900")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("-旧正文", proc.stdout)
        self.assertIn("+新正文", proc.stdout)

    def test_list_runs_aggregates_task_dirs(self) -> None:
        for task, run in (("task-20261009-1100-a", "auto_20261009110000"), ("task-20261009-1130-b", "auto_20261009113000")):
            runs_root = self.base / ".bensz-api" / task / SKILL_DIR
            (runs_root / run / "backup").mkdir(parents=True)
            (runs_root / "log").mkdir(parents=True)
        proc = run_cli(self.base, "list-runs")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(lines, ["auto_20261009113000", "auto_20261009110000"])


if __name__ == "__main__":
    unittest.main()
