"""占位写法统一为【待补充：……】，旧写法由检查脚本提示。"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/nsfc-research-foundation-writer"
SCRIPT = SKILL / "scripts/check_project_outputs.py"
CONDITIONS = "已具备的条件：实验室。尚缺的条件及解决途径：无。\n"
RISKS = "风险一：甲；应对：乙。\n风险二：丙；应对：丁。\n风险三：戊；应对：己。\n"


def run_check(foundation: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        extra = Path(tmp) / "extraTex"
        extra.mkdir()
        (extra / "3.1.研究基础.tex").write_text(foundation, encoding="utf-8")
        (extra / "3.2.工作条件.tex").write_text(CONDITIONS, encoding="utf-8")
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(SCRIPT), "--project-root", tmp], env=env,
                              capture_output=True, text=True, timeout=60)


class PlaceholderStyleTest(unittest.TestCase):
    def test_skill_md_uses_new_style(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("[需补充：", text)
        self.assertNotIn("[请补充：", text)
        self.assertIn("【待补充：", text)

    def test_new_placeholder_is_reported(self) -> None:
        proc = run_check(RISKS + "【待补充：项目组成员及分工】\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("【待补充：", proc.stderr)
        self.assertNotIn("instead of", proc.stderr)

    def test_old_placeholder_points_to_new_style(self) -> None:
        proc = run_check(RISKS + "[请补充：X]\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("use 【待补充：...】 instead of", proc.stderr)

    def test_clean_text_has_no_placeholder_warning(self) -> None:
        proc = run_check(RISKS)
        self.assertNotIn("placeholder", proc.stderr)


if __name__ == "__main__":
    unittest.main()
