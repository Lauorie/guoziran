"""研究期限按项目类型取年数；年度计划检查按年数核对；「首次」不误报。"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "nsfc-research-content-writer"
CHECKER = SKILL / "scripts" / "check_project_outputs.py"
SHOUCI_PHRASES = ["首次提出", "首次发现", "首次实现", "首次揭示", "首次构建", "首次建立", "国内首次", "国际首次", "世界首次"]


def _load_plan_years():
    spec = importlib.util.spec_from_file_location("plan_years", SKILL / "scripts" / "plan_years.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DurationYearsTest(unittest.TestCase):
    def test_keywords(self):
        py = _load_plan_years()
        cases = {
            "国家自然科学基金面上项目": (4, True),
            "面上项目": (4, True),
            "青年科学基金项目（C类）": (3, True),
            "地区科学基金项目": (4, True),
            "重点项目": (5, True),
            "青年科学基金项目（A类）": (5, True),
            "国家杰出青年科学基金": (5, True),
            "青年科学基金项目（B类）": (3, True),
            "重点支持领域的面上项目": (4, True),
            "重大项目": (5, True),
            "": (3, False),
            "联合基金": (3, False),
        }
        for text, expected in cases.items():
            self.assertEqual(py.duration_years(text), expected, text)

    def test_years_out_of_range_is_config_error(self):
        py = _load_plan_years()
        config = {"yearly_plan": {"duration_by_keyword": [["面上", 6]], "default_years": 3, "max_years": 5}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.yaml"
            path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
            with self.assertRaises(ValueError):
                py.duration_years("面上项目", path)

    def test_config_lists(self):
        config = yaml.safe_load((SKILL / "config.yaml").read_text(encoding="utf-8"))
        phrases = config["checks"]["risk_phrases"]
        self.assertNotIn("首次", phrases)
        for phrase in SHOUCI_PHRASES + ["领先", "填补空白", "突破性", "国际领先", "世界领先"]:
            self.assertIn(phrase, phrases)
        self.assertEqual(config["quality_contract"]["yearly_plan_must_include"][0], "按研究期限分年任务（不跨年）")


def _project(tmp: Path, yearly: str) -> Path:
    (tmp / "extraTex").mkdir()
    (tmp / "extraTex" / "2.1.研究内容.tex").write_text("\\subsubsection{研究内容}\n研究内容正文。\n", encoding="utf-8")
    (tmp / "extraTex" / "2.2.特色与创新.tex").write_text("创新正文。\n", encoding="utf-8")
    (tmp / "extraTex" / "2.3.年度研究计划.tex").write_text(yearly, encoding="utf-8")
    return tmp


FOUR_YEARS = "".join(f"\\textbf{{第{i}年}}：任务{i}。\n" for i in range(1, 5))
THREE_YEARS = "".join(f"\\textbf{{第{i}年}}：任务{i}。\n" for i in range(1, 4))


class CheckerYearsTest(unittest.TestCase):
    def run_checker(self, root: Path, *extra: str) -> subprocess.CompletedProcess:
        # 字节码写到 .bensz-api/pycache，不在 skills/ 下留 __pycache__（与 test_nrcw_checker.py 一致）
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(CHECKER), "--project-root", str(root), *extra],
                              capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)

    def test_general_requires_fourth_year(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), THREE_YEARS)
            res = self.run_checker(root, "--project-type", "面上项目")
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("第4年", res.stdout + res.stderr)

    def test_general_four_years_passes(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), FOUR_YEARS)
            res = self.run_checker(root, "--project-type", "面上项目")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_young_default_three_years(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), THREE_YEARS)
            res = self.run_checker(root)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_extra_year_beyond_duration_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), FOUR_YEARS)
            res = self.run_checker(root, "--years", "3")
            self.assertIn("第4年", res.stdout + res.stderr)
            self.assertNotEqual(res.returncode, 0)  # 与缺年份一致，按 ERROR 处理

    def test_year_spellings_accepted(self):
        yearly = "第一年：任务。\n第 2 年：任务。\n第三年：任务。\n第四年：任务。\n第五年：任务。\n"
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), yearly)
            res = self.run_checker(root, "--project-type", "国家自然科学基金重点项目")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), yearly)
            res = self.run_checker(root, "--project-type", "地区科学基金项目")
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("第5年", res.stderr)

    def test_year_du_not_counted_as_year(self):
        # 「第N年度」不算第N年的标题
        yearly = "第一年度：任务。\n第2年度：任务。\n第三年：任务。\n"
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), yearly)
            res = self.run_checker(root)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("第1年", res.stderr)
            self.assertIn("第2年", res.stderr)
            self.assertNotIn("第3年", res.stderr)
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), THREE_YEARS + "第4年度经费另行说明。\n")
            res = self.run_checker(root, "--years", "3")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_unmatched_type_uses_default_and_warns(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), THREE_YEARS)
            res = self.run_checker(root, "--project-type", "联合基金")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn("assumptions.md", res.stderr)

    def test_years_and_type_are_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), THREE_YEARS)
            self.assertEqual(self.run_checker(root, "--years", "3", "--project-type", "面上项目").returncode, 2)
            self.assertEqual(self.run_checker(root, "--years", "0").returncode, 2)
            self.assertEqual(self.run_checker(root, "--years", "6").returncode, 2)

    def test_shouci_plain_usage_not_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), THREE_YEARS)
            (root / "extraTex" / "2.1.研究内容.tex").write_text("被试首次测试前完成问卷。本研究首次提出该框架。\n", encoding="utf-8")
            res = self.run_checker(root)
            out = res.stdout + res.stderr
            self.assertIn("首次提出", out)
            self.assertNotIn("'首次'", out)


if __name__ == "__main__":
    unittest.main()
