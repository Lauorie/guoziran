"""chapter_check：各章的确定性检查。移植自研究内容、研究基础两个写作 skill 的检查器测试。不联网。"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
SCRIPT = SCRIPTS / "chapter_check.py"
sys.path.insert(0, str(SCRIPTS))

from chapter_check import count_risks  # noqa: E402
from proposal_common import load_config  # noqa: E402

CLEAN_RESEARCH = "\\justifying\n针对第一个研究目标，本项目比较瘤内模型与临床基线（实验占比 50\\%）。\n"
CLEAN_INNOVATION = "\\justifying\n与现有路线相比，本项目检验对应关系的成立条件。\n"
CLEAN_YEARLY = "第一年：建立队列。\n第二年：完成建模。\n第三年：外部验证。\n"
CONDITIONS = "已具备的条件：实验室。尚缺的条件及解决途径：无。\n"
RISKS = "风险一：甲；应对：乙。\n风险二：丙；应对：丁。\n风险三：戊；应对：己。\n"
FOUR_YEARS = "".join(f"\\textbf{{第{i}年}}：任务{i}。\n" for i in range(1, 5))
THREE_YEARS = "".join(f"\\textbf{{第{i}年}}：任务{i}。\n" for i in range(1, 4))
SHOUCI_PHRASES = ["首次提出", "首次发现", "首次实现", "首次揭示", "首次构建", "首次建立", "国内首次", "国际首次", "世界首次"]


def write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def make_project(base: Path, **files: str) -> Path:
    """按配置的默认文件名建项目；参数名为章节键：research / innovation / yearly / foundation / conditions。"""
    names = {"research": "2.1.研究内容", "innovation": "2.2.特色与创新", "yearly": "2.3.年度研究计划",
             "foundation": "3.1.研究基础", "conditions": "3.2.工作条件", "justification": "1.1.立项依据"}
    defaults = {"research": CLEAN_RESEARCH, "innovation": CLEAN_INNOVATION, "yearly": CLEAN_YEARLY,
                "foundation": RISKS, "conditions": CONDITIONS, "justification": "立项依据正文。\n"}
    root = base / "proj"
    for key, name in names.items():
        write(root, f"extraTex/{name}.tex", files.get(key, defaults[key]))
    return root


def run_check(project: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
    return subprocess.run([sys.executable, str(SCRIPT), "--project-root", str(project), *args], env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=60)


def out(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout + proc.stderr


def load_module():
    spec = importlib.util.spec_from_file_location("np_chapter_check_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenericRulesTest(unittest.TestCase):
    def test_clean_body_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp)), "--section", "研究内容", "--section", "特色与创新", "--section", "立项依据")
            self.assertEqual(proc.returncode, 0, out(proc))

    def test_missing_and_empty_files_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), research="% 只有注释\n\n")
            (root / "extraTex/2.2.特色与创新.tex").unlink()
            proc = run_check(root, "--section", "研究内容", "--section", "特色与创新")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("ERROR extraTex/2.1.研究内容.tex:", out(proc))
            self.assertIn("ERROR extraTex/2.2.特色与创新.tex:", out(proc))

    def test_leaked_subgoal_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), research="对应 S1 的任务是建立队列。\n"), "--section", "研究内容")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("S1", out(proc))

    def test_subgoal_id_inside_comment_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), research=CLEAN_RESEARCH + "% 内部规划：S1 S2 S3\n"), "--section", "研究内容")
            self.assertEqual(proc.returncode, 0, out(proc))

    def test_medical_s_tokens_are_not_ids(self) -> None:
        body = ("\\justifying\n纳入 L5–S1 与 L5-S1 节段、T12–S2 范围的病例；检测血清 S100β 与 S100 蛋白，"
                "分析 S1P 通路与 S1 受体激动剂的作用。\n")
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), research=body), "--section", "研究内容")
            self.assertEqual(proc.returncode, 0, out(proc))

    def test_brief_examples_l5_s1_and_s100_beta_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), research="病变位于 L5–S1，检测 S100β。\n"), "--section", "研究内容")
            self.assertEqual(proc.returncode, 0, out(proc))

    def test_leak_next_to_allowed_token_is_still_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), research="L5–S1 节段的数据对应 S2 的任务。\n"), "--section", "研究内容")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("S2", out(proc))
            self.assertNotIn("S1", out(proc).split("内部编号")[1])

    def test_allowed_tokens_come_from_config(self) -> None:
        tokens = load_config()["chapter_checks"]["allowed_s_tokens"]
        for token in ("L5-S1", "L5–S1", "S100", "S100β", "S1P"):
            self.assertIn(token, tokens)
        module = load_module()
        self.assertEqual(module.find_leaked_ids("对应 S3 区段", ["S3 区段"]), [])
        self.assertEqual(module.find_leaked_ids("对应 S3 区段", []), ["S3"])

    def test_risk_phrase_is_warning_except_in_innovation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), research="本项目填补空白。\n", innovation="本项目国内首创。领先于现有路线。\n")
            proc = run_check(root, "--section", "研究内容")
            self.assertEqual(proc.returncode, 0, out(proc))
            self.assertIn("WARN extraTex/2.1.研究内容.tex:", out(proc))
            proc = run_check(root, "--section", "特色与创新")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("ERROR extraTex/2.2.特色与创新.tex:", out(proc))

    def test_phrase_inside_longer_phrase_reported_once(self) -> None:
        module = load_module()
        found = module.find_risk_phrases("本项目国际领先。", ["领先", "国际领先"])
        self.assertEqual(found, ["国际领先"])
        found = module.find_risk_phrases("国际领先的方法，也领先于同类。", ["领先", "国际领先"])
        self.assertEqual(sorted(found), ["国际领先", "领先"])
        self.assertEqual(module.find_risk_phrases("领先领先", ["领先"]), ["领先"])

    def test_shouci_plain_usage_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), research="被试首次测试前完成问卷。本研究首次提出该框架。\n")
            res = run_check(root, "--section", "研究内容")
            self.assertIn("首次提出", out(res))
            self.assertNotIn("「首次」", out(res))
        self.assertTrue(set(SHOUCI_PHRASES) <= set(load_config()["chapter_checks"]["risk_phrases"]))

    def test_nonstandard_placeholders_are_errors(self) -> None:
        for legacy in ("[请补充：X]", "[需补充：X]", "[待补充：X]"):
            with self.subTest(legacy=legacy), tempfile.TemporaryDirectory() as tmp:
                proc = run_check(make_project(Path(tmp), foundation=RISKS + legacy + "\n"), "--section", "研究基础")
                self.assertEqual(proc.returncode, 1)
                self.assertIn("【待补充：", out(proc))

    def test_standard_placeholder_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), foundation=RISKS + "【待补充：项目组成员及分工】\n"), "--section", "研究基础")
            self.assertEqual(proc.returncode, 0, out(proc))


class YearlyPlanTest(unittest.TestCase):
    def test_missing_year_header_fails_with_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), yearly="第一年：建立队列。\n"), "--section", "年度研究计划")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("ERROR extraTex/2.3.年度研究计划.tex: 缺少第2年/第二年的年度标题（研究期限 3 年）", out(proc))

    def test_general_requires_fourth_year(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), yearly=THREE_YEARS), "--section", "年度研究计划", "--project-type", "面上项目")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("缺少第4年/第四年的年度标题（研究期限 4 年）", out(proc))

    def test_general_four_years_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), yearly=FOUR_YEARS), "--section", "年度研究计划", "--project-type", "面上项目")
            self.assertEqual(proc.returncode, 0, out(proc))

    def test_general_project_with_fifth_year_fails(self) -> None:
        yearly = FOUR_YEARS + "\\textbf{第五年}：收尾。\n"
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), yearly=yearly), "--section", "年度研究计划", "--project-type", "面上项目")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("超出研究期限 4 年", out(proc))
            self.assertIn("第5年", out(proc))

    def test_young_default_three_years(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), yearly=THREE_YEARS), "--section", "年度研究计划")
            self.assertEqual(proc.returncode, 0, out(proc))
            self.assertIn("WARN", out(proc))  # 没有项目类型：按默认年数并给警告

    def test_extra_year_beyond_duration_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), yearly=FOUR_YEARS), "--section", "年度研究计划", "--years", "3")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("第4年", out(proc))

    def test_far_year_narrative_is_not_reported(self) -> None:
        yearly = THREE_YEARS + "第十年随访评估远期结局。\n"
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), yearly=yearly), "--section", "年度研究计划", "--years", "3")
            self.assertEqual(proc.returncode, 0, out(proc))

    def test_year_spellings_accepted(self) -> None:
        yearly = "第一年：任务。\n第 2 年：任务。\n第三年：任务。\n第四年：任务。\n第五年：任务。\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), yearly=yearly)
            proc = run_check(root, "--section", "年度研究计划", "--project-type", "国家自然科学基金重点项目")
            self.assertEqual(proc.returncode, 0, out(proc))
            proc = run_check(root, "--section", "年度研究计划", "--project-type", "地区科学基金项目")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("第5年", out(proc))

    def test_year_du_headers_count(self) -> None:
        yearly = "".join(f"\\subsubsubsection{{第{cn}年度（{2026 + i}.01–{2026 + i}.12）}}\n任务。\n"
                         for i, cn in enumerate("一二三四", start=1))
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), yearly=yearly), "--section", "年度研究计划", "--project-type", "面上项目")
            self.assertEqual(proc.returncode, 0, out(proc))
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), yearly="第1年度：任务。\n第 2 年度：任务。\n第三年度：任务。\n第4年度：任务。\n")
            proc = run_check(root, "--section", "年度研究计划", "--years", "3")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("第4年", out(proc))
            self.assertNotIn("缺少", out(proc))

    def test_unmatched_type_uses_default_and_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp), yearly=THREE_YEARS), "--section", "年度研究计划", "--project-type", "联合基金")
            self.assertEqual(proc.returncode, 0, out(proc))
            self.assertIn("WARN", out(proc))
            self.assertIn("assumptions.md", out(proc))

    def test_project_type_falls_back_to_scientific_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), yearly=THREE_YEARS)
            write(root, "proposal/scientific_case.yaml", yaml.safe_dump({"project": {"type": "面上项目"}}, allow_unicode=True))
            proc = run_check(root, "--section", "年度研究计划")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("研究期限 4 年", out(proc))
            # --years 优先于科学论证里的项目类型
            self.assertEqual(run_check(root, "--section", "年度研究计划", "--years", "3").returncode, 0)

    def test_years_and_type_are_exclusive_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), yearly=THREE_YEARS)
            self.assertEqual(run_check(root, "--section", "年度研究计划", "--years", "3", "--project-type", "面上项目").returncode, 2)
            self.assertEqual(run_check(root, "--section", "年度研究计划", "--years", "0").returncode, 2)
            self.assertEqual(run_check(root, "--section", "年度研究计划", "--years", "6").returncode, 2)


class FoundationRulesTest(unittest.TestCase):
    def run_foundation(self, foundation: str, conditions: str = CONDITIONS) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), foundation=foundation, conditions=conditions)
            return run_check(root, "--section", "研究基础", "--section", "工作条件")

    def test_numbered_risks_in_running_text_count(self) -> None:
        text = "\\subsubsection{风险与应对}\n风险一：数据不足；应对：扩大来源。\n风险二：进度延迟；应对：预留缓冲。\n风险三：设备故障；应对：备用设备。\n"
        proc = self.run_foundation(text)
        self.assertEqual(proc.returncode, 0, out(proc))

    def test_arabic_numbers_count(self) -> None:
        proc = self.run_foundation("风险 1：甲；应对：乙。\n风险 2：丙；预案：丁。\n风险 3：戊；替代：己。\n")
        self.assertEqual(proc.returncode, 0, out(proc))

    def test_single_risk_heading_still_fails(self) -> None:
        proc = self.run_foundation("\\subsubsection{风险与应对}\n数据可能不足，应对是扩大来源。\n")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("风险条目 0 条", out(proc))  # 「风险与应对」是章节标题，不是一条风险

    def test_two_ordinal_headings_under_section_title_count_two(self) -> None:
        head = "\\subsubsection{研究风险的应对措施}\n"
        two = head + "\\subsubsubsection{风险一：数据不足}\n应对：扩大来源。\n\\subsubsubsection{风险二：进度延迟}\n应对：预留缓冲。\n"
        self.assertEqual(count_risks(two), 2)
        proc = self.run_foundation(two)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("风险条目 2 条", out(proc))
        three = two + "\\subsubsubsection{风险三：设备故障}\n应对：备用设备。\n"
        self.assertEqual(count_risks(three), 3)
        self.assertEqual(self.run_foundation(three).returncode, 0)

    def test_labelled_risk_lines_count(self) -> None:
        plain = "技术风险：甲；应对：乙。\n进度风险：丙；应对：丁。\n资源风险：戊；应对：己。\n"
        self.assertEqual(count_risks(plain), 3)
        items = "".join(f"\\item \\textbf{{{k}风险}}：甲；应对：乙。\n" for k in ("技术", "进度", "资源"))
        self.assertEqual(count_risks(items), 3)
        self.assertEqual(self.run_foundation(plain).returncode, 0)

    def test_same_ordinal_in_heading_and_body_is_one_item(self) -> None:
        text = "\\subsubsubsection{风险一：数据不足}\n如上所述，风险1 的应对是扩大来源。\n风险二：甲；应对：乙。\n风险三：丙；应对：丁。\n"
        self.assertEqual(count_risks(text), 3)

    def test_section_title_alone_counts_zero(self) -> None:
        self.assertEqual(count_risks("\\subsubsection{研究风险的应对措施}\n本项目总体可控。\n"), 0)

    def test_missing_risk_word_fails(self) -> None:
        proc = self.run_foundation("预实验结果良好。\n")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("风险", out(proc))

    def test_missing_response_keywords_warns(self) -> None:
        proc = self.run_foundation("风险一：甲。\n风险二：乙。\n风险三：丙。\n")
        self.assertEqual(proc.returncode, 0, out(proc))
        self.assertIn("WARN extraTex/3.1.研究基础.tex:", out(proc))

    def test_min_risks_comes_from_config(self) -> None:
        self.assertEqual(load_config()["chapter_checks"]["min_risks"], 3)

    def test_conditions_warnings(self) -> None:
        proc = self.run_foundation(RISKS, conditions="实验室面积 80 平方米。\n")
        self.assertEqual(proc.returncode, 0, out(proc))
        self.assertIn("WARN extraTex/3.2.工作条件.tex:", out(proc))
        self.assertEqual(out(proc).count("WARN extraTex/3.2.工作条件.tex:"), 2)
        clean = self.run_foundation(RISKS, conditions="已具备实验室。目前缺少动物房，将借用公共平台。\n")
        self.assertNotIn("WARN", out(clean))


class AbstractSectionTest(unittest.TestCase):
    def test_abstract_errors_and_warnings_are_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            write(root, "NSFC-ABSTRACTS.md", "# 中文摘要\n正文\n")
            proc = run_check(root, "--section", "摘要")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("ERROR NSFC-ABSTRACTS.md:", out(proc))


class SectionResolutionTest(unittest.TestCase):
    def test_unknown_section_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_check(make_project(Path(tmp)), "--section", "不存在")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("不存在", out(proc))

    def test_section_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_check(make_project(Path(tmp))).returncode, 2)

    def test_bad_project_root_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_check(Path(tmp) / "none", "--section", "研究内容").returncode, 2)

    def test_plan_entry_with_section_decides_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            write(root, "extraTex/custom.tex", "对应 S1 的任务。\n")
            write(root, "proposal/section_plan.yaml", yaml.safe_dump(
                {"files": [{"file": "extraTex/custom.tex", "section": "研究内容"}]}, allow_unicode=True))
            proc = run_check(root, "--section", "研究内容")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("extraTex/custom.tex", out(proc))

    def test_legacy_plan_with_only_writer_is_found_by_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            write(root, "proposal/section_plan.yaml", yaml.safe_dump({"files": [
                {"file": "proposal/ai_declaration.md", "writer": "nsfc-research-content-writer"},
                {"file": "extraTex/2.1.研究内容.tex", "writer": "nsfc-research-content-writer"}]}, allow_unicode=True))
            write(root, "proposal/ai_declaration.md", "\n")
            proc = run_check(root, "--section", "生成式人工智能使用说明", "--section", "研究内容")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("ERROR proposal/ai_declaration.md:", out(proc))
            self.assertNotIn("extraTex/2.1.研究内容.tex", out(proc))

    def test_plan_without_entry_falls_back_to_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), research="对应 S1 的任务。\n")
            write(root, "proposal/section_plan.yaml", yaml.safe_dump({"files": []}))
            proc = run_check(root, "--section", "研究内容")
            self.assertIn("extraTex/2.1.研究内容.tex", out(proc))
            self.assertEqual(proc.returncode, 1)


class JsonOutputTest(unittest.TestCase):
    def test_json_has_errors_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp), research="对应 S1 的任务，国内首创。\n")
            proc = run_check(root, "--section", "研究内容", "--json")
            self.assertEqual(proc.returncode, 1)
            data = json.loads(proc.stdout)
            self.assertEqual(set(data), {"errors", "warnings"})
            self.assertTrue(any("S1" in e for e in data["errors"]))
            self.assertTrue(any("国内首创" in w for w in data["warnings"]))


if __name__ == "__main__":
    unittest.main()
