from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "skills/nsfc-research-content-writer/scripts/check_project_outputs.py"

CLEAN_RESEARCH = "\\justifying\n针对第一个研究目标，本项目比较瘤内模型与临床基线（实验占比 50\\%）。\n"
CLEAN_INNOVATION = "\\justifying\n与现有路线相比，本项目检验对应关系的成立条件。\n"
CLEAN_YEARLY = "第一年：建立队列。\n第二年：完成建模。\n第三年：外部验证。\n"


def make_project(base: Path, research: str = CLEAN_RESEARCH, innovation: str = CLEAN_INNOVATION, yearly: str = CLEAN_YEARLY) -> Path:
    extra = base / "proj" / "extraTex"
    extra.mkdir(parents=True)
    (extra / "2.1.研究内容.tex").write_text(research, encoding="utf-8")
    (extra / "2.2.特色与创新.tex").write_text(innovation, encoding="utf-8")
    (extra / "2.3.年度研究计划.tex").write_text(yearly, encoding="utf-8")
    return base / "proj"


def run_checker(project: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
    return subprocess.run([sys.executable, str(CHECKER), "--project-root", str(project), "--no-risk-scan"],
                          env=env, capture_output=True, text=True, timeout=60)


class CheckerTest(unittest.TestCase):
    def test_clean_body_without_subgoal_ids_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_checker(make_project(Path(tmp)))
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_leaked_subgoal_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_checker(make_project(Path(tmp), research="对应 S1 的任务是建立队列。\n"))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("S1", proc.stderr)

    def test_subgoal_id_inside_comment_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_checker(make_project(Path(tmp), research=CLEAN_RESEARCH + "% 内部规划：S1 S2 S3\n"))
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_year_header_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_checker(make_project(Path(tmp), yearly="第一年：建立队列。\n"))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("第2年", proc.stderr)


if __name__ == "__main__":
    unittest.main()
