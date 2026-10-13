"""abstract_check：摘要文件的格式与长度检查。不联网。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
SCRIPT = SCRIPTS / "abstract_check.py"
sys.path.insert(0, str(SCRIPTS))

import abstract_check  # noqa: E402
from proposal_common import load_config  # noqa: E402

ZH = "肿瘤免疫治疗在多数实体瘤中应答率偏低。本项目拟建立可解释的联合特征，并在前瞻性队列中验证“应答判据”。预期阐明关键机制。"
EN = "Immunotherapy response remains low in most solid tumors. This project builds interpretable features and validates them."
FIELD = "肿瘤微环境免疫调控与免疫治疗反应预测"


def title_block(count: int = 5, reason: bool = True, en: bool = True, recommended: bool = True, recommended_en: bool = True) -> str:
    lines = []
    if recommended:
        lines.append("推荐标题：可解释特征驱动的免疫治疗反应预测")
    if recommended_en:
        lines.append("Recommended Title: Interpretable Feature-driven Prediction of Immunotherapy Response")
    for i in range(1, count + 1):
        item = f"{i}) 候选标题{i}"
        if reason:
            item += " —— 理由：对象与终点清楚"
        if en:
            item += f" / EN: Candidate Title {i}"
        lines.append(item)
    return "\n".join(lines)


def abstract(zh: str = ZH, en: str = EN, title: str | None = None, field: str = FIELD, blank_before_en: bool = False) -> str:
    title = title_block() if title is None else title
    gap = "\n\n" if blank_before_en else "\n"
    return f"# 标题建议\n{title}\n\n# 中文摘要\n{zh}{gap}# English Abstract\n{en}\n\n# 主要研究领域\n{field}\n"


def check(text: str) -> dict:
    return abstract_check.check_text(text, load_config())


def run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, input=stdin, capture_output=True,
                          text=True, encoding="utf-8", timeout=60)


class AbstractCheckTest(unittest.TestCase):
    def assertHas(self, result: dict, key: str, needle: str) -> None:
        self.assertTrue(any(needle in m for m in result[key]), f"{key} 中没有「{needle}」：{result[key]}")

    def assertNoError(self, result: dict, needle: str) -> None:
        self.assertFalse(any(needle in m for m in result["errors"]), result["errors"])

    def test_complete_sample_passes(self) -> None:
        result = check(abstract())
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["counts"]["zh_chars"], len(ZH))

    # 标题齐全与顺序
    def test_missing_heading_is_error(self) -> None:
        result = check(abstract().replace("# 主要研究领域\n", ""))
        self.assertHas(result, "errors", "# 主要研究领域")

    def test_wrong_order_is_error(self) -> None:
        text = f"# 中文摘要\n{ZH}\n# 标题建议\n{title_block()}\n\n# English Abstract\n{EN}\n\n# 主要研究领域\n{FIELD}\n"
        self.assertHas(check(text), "errors", "顺序")

    def test_bracket_markers_are_not_recognised(self) -> None:
        text = f"[ZH]\n{ZH}\n[/ZH]\n[EN]\n{EN}\n[/EN]\n"
        result = check(text)
        self.assertHas(result, "errors", "# 中文摘要")
        self.assertHas(result, "errors", "# English Abstract")

    # 长度
    def test_chinese_limit_counts_punctuation_after_whitespace_collapse(self) -> None:
        self.assertEqual(check(abstract(zh="甲" * 400))["errors"], [])
        over = check(abstract(zh="甲" * 401))
        self.assertHas(over, "errors", "中文摘要")
        self.assertEqual(over["counts"]["zh_chars"], 401)
        punct = check(abstract(zh="甲，" * 200 + "。"))
        self.assertEqual(punct["counts"]["zh_chars"], 401)
        self.assertHas(punct, "errors", "超过")

    def test_whitespace_runs_collapse_to_one_space(self) -> None:
        zh = "甲" * 200 + "\n\n   \t" + "乙" * 198  # 折叠后 200 + 1 + 198 = 399
        result = check(abstract(zh=zh))
        self.assertEqual(result["counts"]["zh_chars"], 399)
        self.assertNoError(result, "超过")

    def test_english_limit(self) -> None:
        self.assertEqual(check(abstract(en="a" * 4000))["errors"], [])
        self.assertHas(check(abstract(en="a" * 4001)), "errors", "English Abstract")

    # 引号
    def test_ascii_double_quote_is_error(self) -> None:
        self.assertHas(check(abstract(zh='提出"应答判据"。')), "errors", "ASCII")

    def test_curly_double_quotes_pass(self) -> None:
        self.assertEqual(check(abstract(zh="提出“应答判据”。"))["errors"], [])

    def test_other_quote_code_points_are_errors(self) -> None:
        for ch in ("＂", "〝", "〞", "「", "」", "『", "』"):
            with self.subTest(code=hex(ord(ch))):
                self.assertHas(check(abstract(zh=f"提出{ch}应答判据。")), "errors", "引号")

    def test_single_quotes_are_not_checked(self) -> None:
        self.assertEqual(check(abstract(zh="提出‘应答判据’与'判据'。"))["errors"], [])

    def test_quotes_in_english_abstract_are_allowed(self) -> None:
        self.assertEqual(check(abstract(en='We define "response" here.'))["errors"], [])

    # 千分位逗号
    def test_thousands_separator_is_error(self) -> None:
        for zh in ("纳入 1,000 例患者。", "纳入 1，000 例患者。"):
            with self.subTest(zh=zh):
                self.assertHas(check(abstract(zh=zh)), "errors", "千分位")

    def test_plain_numbers_and_list_commas_pass(self) -> None:
        self.assertEqual(check(abstract(zh="纳入 1000 例，其中 2 组，3 组为对照。"))["errors"], [])

    # Markdown 标记
    def test_markdown_marks_in_chinese_abstract(self) -> None:
        for zh in ("**重点**内容。", "__重点__内容。", "第一句。\n## 小节\n第二句。"):
            with self.subTest(zh=zh):
                self.assertHas(check(abstract(zh=zh)), "errors", "Markdown")

    # 标题建议
    def test_title_candidates_below_config_count(self) -> None:
        self.assertHas(check(abstract(title=title_block(count=4))), "errors", "候选")
        self.assertNoError(check(abstract(title=title_block(count=6))), "候选")

    def test_title_candidate_needs_reason_and_en(self) -> None:
        self.assertHas(check(abstract(title=title_block(reason=False))), "errors", "理由")
        self.assertHas(check(abstract(title=title_block(en=False))), "errors", "EN:")

    def test_recommended_titles_required(self) -> None:
        self.assertHas(check(abstract(title=title_block(recommended=False))), "errors", "推荐标题：")
        self.assertHas(check(abstract(title=title_block(recommended_en=False))), "errors", "Recommended Title:")

    # 主要研究领域
    def test_field_length_counts_han_characters_only(self) -> None:
        self.assertEqual(check(abstract(field="甲" * 25 + " ABC-123"))["errors"], [])
        over = check(abstract(field="甲" * 26))
        self.assertHas(over, "errors", "主要研究领域")
        self.assertEqual(over["counts"]["field_chars"], 26)

    def test_field_must_be_one_sentence(self) -> None:
        self.assertHas(check(abstract(field="肿瘤免疫。免疫治疗。")), "errors", "一句")
        self.assertHas(check(abstract(field="肿瘤免疫\n免疫治疗")), "errors", "一句")
        self.assertEqual(check(abstract(field="- 肿瘤免疫治疗"))["errors"], [])

    def test_empty_field_is_error(self) -> None:
        self.assertHas(check(abstract(field="")), "errors", "主要研究领域")

    # 空行
    def test_blank_line_before_english_heading_warns(self) -> None:
        result = check(abstract(blank_before_en=True))
        self.assertEqual(result["errors"], [])
        self.assertHas(result, "warnings", "空行")


class AbstractCliTest(unittest.TestCase):
    def test_cli_exit_codes_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.md"
            good.write_text(abstract(), encoding="utf-8")
            bad = Path(tmp) / "bad.md"
            bad.write_text(abstract(zh='提出"判据"。'), encoding="utf-8")
            self.assertEqual(run_cli(str(good)).returncode, 0)
            proc = run_cli(str(bad))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("ERROR", proc.stdout + proc.stderr)
            data = json.loads(run_cli(str(bad), "--json").stdout)
            self.assertTrue(data["errors"])
            self.assertEqual(data["warnings"], [])
            self.assertEqual(run_cli(str(Path(tmp) / "none.md")).returncode, 2)

    def test_cli_reads_stdin(self) -> None:
        self.assertEqual(run_cli("-", stdin=abstract()).returncode, 0)
        self.assertEqual(run_cli("-", stdin="").returncode, 1)


if __name__ == "__main__":
    unittest.main()
