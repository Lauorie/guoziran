"""研究基础检查：「风险一」「风险 2」一类写法计入风险条目。"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/nsfc-research-foundation-writer/scripts/check_project_outputs.py"
CONDITIONS = "已具备的条件：实验室。尚缺的条件及解决途径：无。\n"


def run_check(foundation: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        extra = Path(tmp) / "extraTex"
        extra.mkdir()
        (extra / "3.1.研究基础.tex").write_text(foundation, encoding="utf-8")
        (extra / "3.2.工作条件.tex").write_text(CONDITIONS, encoding="utf-8")
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(SCRIPT), "--project-root", tmp], env=env,
                              capture_output=True, text=True, timeout=60)


class RiskCountTest(unittest.TestCase):
    def test_numbered_risks_in_running_text_count(self) -> None:
        text = "\\subsubsection{风险与应对}\n风险一：数据不足；应对：扩大来源。\n风险二：进度延迟；应对：预留缓冲。\n风险三：设备故障；应对：备用设备。\n"
        proc = run_check(text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_arabic_numbers_count(self) -> None:
        proc = run_check("风险 1：甲；应对：乙。\n风险 2：丙；预案：丁。\n风险 3：戊；替代：己。\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_single_risk_heading_still_fails(self) -> None:
        proc = run_check("\\subsubsection{风险与应对}\n数据可能不足，应对是扩大来源。\n")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("< 3 risk items", proc.stderr)


if __name__ == "__main__":
    unittest.main()
