"""plan_years：研究期限按项目类型取年数，年数表只在 nsfc-proposal 的 config.yaml。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import plan_years  # noqa: E402


def _write_config(directory: str, yearly: object) -> Path:
    path = Path(directory) / "config.yaml"
    path.write_text(yaml.safe_dump({"yearly_plan": yearly}, allow_unicode=True), encoding="utf-8")
    return path


class DurationYearsTest(unittest.TestCase):
    def test_default_config_lives_in_nsfc_proposal(self) -> None:
        self.assertEqual(plan_years.DEFAULT_CONFIG.parent, ROOT / "skills" / "nsfc-proposal")
        self.assertTrue(plan_years.DEFAULT_CONFIG.is_file())

    def test_keywords(self) -> None:
        cases = {
            "国家自然科学基金面上项目": (4, True),
            "面上项目": (4, True),
            "青年科学基金项目（C类）": (3, True),
            "地区科学基金项目": (4, True),
            "重点项目": (5, True),
            "青年科学基金项目（A类）": (5, True),
            "青年科学基金项目（A 类）": (5, True),
            "青年科学基金项目（Ａ类）": (5, True),
            "国家杰出青年科学基金": (5, True),
            "青年科学基金项目（B类）": (3, True),
            "重点支持领域的面上项目": (4, True),
            "重大项目": (5, True),
            "": (3, False),
            "联合基金": (3, False),
        }
        for text, expected in cases.items():
            self.assertEqual(plan_years.duration_years(text), expected, text)

    def test_unmatched_type_uses_default_and_reports_unmatched(self) -> None:
        self.assertEqual(plan_years.duration_years("联合基金"), (3, False))
        self.assertEqual(plan_years.duration_years(None), (3, False))  # type: ignore[arg-type]

    def test_keywords_in_table_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = _write_config(d, {"duration_by_keyword": [["Ａ 类", 5]], "default_years": 3, "max_years": 5})
            self.assertEqual(plan_years.duration_years("青年科学基金项目（A类）", path), (5, True))
            self.assertEqual(plan_years.duration_years("  ", path), (3, False))

    def test_normalize_type(self) -> None:
        self.assertEqual(plan_years.normalize_type("（Ａ 类）"), plan_years.normalize_type("(A类)"))

    def test_years_out_of_range_is_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = _write_config(d, {"duration_by_keyword": [["面上", 6]], "default_years": 3, "max_years": 5})
            with self.assertRaises(ValueError):
                plan_years.duration_years("面上项目", path)

    def test_bad_config_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            for bad in (None, {"duration_by_keyword": [], "default_years": 3, "max_years": 5},
                        {"duration_by_keyword": [["面上"]], "default_years": 3, "max_years": 5},
                        {"duration_by_keyword": [["面上", 4]], "default_years": 9, "max_years": 5}):
                path = _write_config(d, bad)
                with self.assertRaises(ValueError, msg=str(bad)):
                    plan_years.load_yearly_plan(path)
            with self.assertRaises(ValueError):
                plan_years.load_yearly_plan(Path(d) / "missing.yaml")

    def test_year_label(self) -> None:
        self.assertEqual(plan_years.year_label(4), "第4年/第四年")
        self.assertEqual(plan_years.year_label(11), "第11年")
        self.assertEqual(plan_years.CN_NUMERALS, "一二三四五六七八九十")


if __name__ == "__main__":
    unittest.main()
