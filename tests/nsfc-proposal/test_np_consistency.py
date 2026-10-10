# tests/nsfc-proposal/test_np_consistency.py
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from case import init_proposal  # noqa: E402
from citation_ledger import add_event, append_event, register_user_entries  # noqa: E402
from consistency_check import check_project  # noqa: E402
from latex_files import bib_entry_texts  # noqa: E402
from proposal_common import load_config, proposal_paths, write_yaml  # noqa: E402
from test_np_validate import valid_case, valid_evidence  # noqa: E402

BODY_11 = "\n".join([
    "\\justifying",
    "本项目界定的多模态影像信息\\cite{wu2021value,missing2020}。",
    "占比 50\\% 的病例接受手术。",
    "【待补充：预实验结果】",
    "【待补充：合作医院名称】",
    "% 待补文献：瘤周研究综述",
    "对应 Q1 的研究任务。",
    "采用 T1 加权序列作参照。",
]) + "\n"


def build(base: Path, *, body_11: str = BODY_11, terms: list | None = None, ledger: bool = True) -> Path:
    """搭一个最小项目；ledger 为 True 时，wu2021value 在台账中有 add 记录（无摘要），与 init 之后 bib_resolve 写入的状态相同。"""
    root = base / "proj"
    (root / "extraTex").mkdir(parents=True)
    (root / "references").mkdir()
    (root / "main.tex").write_text("\\input{extraTex/1.1.立项依据.tex}\n\\input{references/reference.tex}\n", encoding="utf-8")
    (root / "references" / "reference.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
    (root / "references" / "refs.bib").write_text("@article{wu2021value,\n  title = {X},\n}\n", encoding="utf-8")
    (root / "extraTex" / "1.1.立项依据.tex").write_text(body_11, encoding="utf-8")
    (root / "extraTex" / "2.1.研究内容.tex").write_text("研究内容正文。\n", encoding="utf-8")
    case = valid_case()
    case["version"] = 2
    if terms is not None:
        case["terms"] = terms
    write_yaml(root / "proposal" / "scientific_case.yaml", case)
    write_yaml(root / "proposal" / "evidence_map.yaml", valid_evidence())
    write_yaml(root / "proposal" / "section_plan.yaml", {"version": 1, "files": [
        {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "written_with_case_version": 1},
        {"file": "extraTex/2.1.研究内容.tex", "writer": "nsfc-research-content-writer", "written_with_case_version": 2},
        {"file": "NSFC-ABSTRACTS.md", "writer": "nsfc-abstract", "written_with_case_version": None},
    ]})
    (root / "proposal" / "assumptions.md").write_text("# 假设与待核实清单\n\n## 占位清单\n\n- extraTex/1.1.立项依据.tex：【待补充：预实验结果】\n", encoding="utf-8")
    if ledger:
        text = bib_entry_texts([root / "references" / "refs.bib"])["wu2021value"]
        append_event(proposal_paths(root).ledger, add_event(
            "wu2021value", source="crossref", entry_text=text, doi=None, abstract=None, provenance={"record_id": "r0"}))
    return root


class ConsistencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_errors_and_reviews(self) -> None:
        report = check_project(build(self.base))
        errors = {(f.kind, f.detail if f.kind != "hidden_placeholder" else f.line) for f in report.errors}
        self.assertEqual(errors, {
            ("missing_bibkey", "missing2020"),
            ("placeholder_unlisted", "【待补充：合作医院名称】"),
            ("hidden_placeholder", 6),
            ("stale_section", "依据第 1 版科学论证，当前为第 2 版"),
        })
        reviews = {(f.kind, f.detail) for f in report.needs_review}
        self.assertIn(("internal_id", "Q1"), reviews)
        self.assertIn(("internal_id", "T1"), reviews)
        self.assertIn(("file_not_compiled", "main.tex 未引用该文件，内容不会进入 PDF"), reviews)
        self.assertEqual(len(report.placeholders), 2)

    def test_escaped_percent_is_not_flagged(self) -> None:
        report = check_project(build(self.base, body_11="占比 50\\% 待补数据 多模态。\n"))
        self.assertFalse([f for f in report.errors if f.kind == "hidden_placeholder"])

    def test_real_comment_after_escaped_percent_is_flagged(self) -> None:
        report = check_project(build(self.base, body_11="占比 50\\% 多模态 % 待补文献\n"))
        hidden = [f for f in report.errors if f.kind == "hidden_placeholder"]
        self.assertEqual([f.line for f in hidden], [1])

    def test_unused_term(self) -> None:
        report = check_project(build(self.base, terms=[{"term": "影像基因组", "definition": "X", "source": "user"}]))
        self.assertIn(("term_unused", "影像基因组"), {(f.kind, f.detail) for f in report.errors})

    def test_cli_exit_codes_and_json(self) -> None:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        bad_root = build(self.base)
        proc = subprocess.run([sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(bad_root), "--json"],
                              env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(json.loads(proc.stdout)["placeholders"]), 2)
        clean = build(self.base / "clean", body_11="多模态影像信息\\cite{wu2021value}。\n【待补充：预实验结果】\n")
        write_yaml(clean / "proposal" / "section_plan.yaml", {"version": 1, "files": [
            {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "written_with_case_version": 2}]})
        ok = subprocess.run([sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(clean)],
                            env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def _build_numbers(self) -> Path:
        root = build(self.base, body_11="最佳瘤周宽度 2–10 mm，共纳入 120 例。 % 注释里的 99 mm\n多模态影像信息。\n")
        (root / "extraTex" / "2.1.研究内容.tex").write_text("最佳宽度 0–3 mm。\n", encoding="utf-8")
        return root

    def test_numbers_listed_per_file(self) -> None:
        report = check_project(self._build_numbers())
        mm = [f for f in report.numbers if f.detail.endswith("mm")]
        self.assertEqual({(f.file, f.detail) for f in mm}, {("extraTex/1.1.立项依据.tex", "2–10 mm"), ("extraTex/2.1.研究内容.tex", "0–3 mm")})
        self.assertTrue(all(f.kind == "number" for f in report.numbers))
        self.assertIn("120 例", {f.detail for f in report.numbers})

    def test_numbers_in_latex_comment_are_ignored(self) -> None:
        report = check_project(self._build_numbers())
        self.assertFalse([f for f in report.numbers if "99" in f.detail])

    def test_numbers_latex_percent_range_and_tilde(self) -> None:
        body = "约 95\\% 的患者。\n宽度 2--10 mm。\n层厚 10~mm。\n共 3 例如下。\n年龄 5 个别。\n"
        details = [f.detail for f in check_project(build(self.base, body_11=body)).numbers]
        self.assertIn("95\\%", details)
        self.assertEqual([d for d in details if "10" in d and "mm" in d and d.startswith("2")], ["2--10 mm"])
        self.assertNotIn("10 mm", details)
        self.assertIn("10~mm", details)
        self.assertFalse([d for d in details if d.startswith(("3 ", "5 "))])

    def test_cli_numbers_flag_keeps_exit_code(self) -> None:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        root = self._build_numbers()
        cmd = [sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(root)]
        plain = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        with_numbers = subprocess.run(cmd + ["--numbers"], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(with_numbers.returncode, plain.returncode)
        self.assertNotIn("## 数值清单", plain.stdout)
        self.assertIn("## 数值清单", with_numbers.stdout)
        self.assertIn("### mm", with_numbers.stdout)
        as_json = subprocess.run(cmd + ["--json"], env=env, capture_output=True, text=True, timeout=60)
        self.assertTrue(json.loads(as_json.stdout)["numbers"])


ABSTRACT = "We report an AUC of 0.86 and sensitivity of 95% in 1,200 patients, with a margin of 5 mm in the test cohort."


def kinds(findings: list) -> set[str]:
    return {f.kind for f in findings}


class LedgerConsistencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _ledgered(self, body: str, abstract: str | None = ABSTRACT, key: str = "wu2021value") -> Path:
        self.count = getattr(self, "count", 0) + 1
        root = build(self.base / f"n{self.count}", body_11=body, ledger=False)
        text = bib_entry_texts([root / "references" / "refs.bib"])[key]
        append_event(proposal_paths(root).ledger, add_event(
            key, source="crossref", entry_text=text, doi=None, abstract=abstract, provenance={"record_id": "r1"}))
        return root

    def test_no_ledger_is_an_error_and_other_checks_run(self) -> None:
        report = check_project(build(self.base, ledger=False))
        self.assertIn("no_citation_ledger", kinds(report.errors))
        self.assertNotIn("no_citation_ledger", kinds(report.needs_review))
        self.assertIn("missing_bibkey", kinds(report.errors))
        self.assertFalse(kinds(report.errors) & {"cite_not_in_ledger", "bib_entry_modified"})

    def test_no_ledger_cli_exits_1(self) -> None:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        root = build(self.base, body_11="多模态影像信息\\cite{wu2021value}。\n【待补充：预实验结果】\n", ledger=False)
        write_yaml(root / "proposal" / "section_plan.yaml", {"version": 1, "files": [
            {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "written_with_case_version": 2}]})
        cmd = [sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(root)]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual([f["kind"] for f in json.loads(subprocess.run(cmd + ["--json"], env=env, capture_output=True, text=True,
                                                                         timeout=60).stdout)["errors"]], ["no_citation_ledger"])
        self.assertIn("没有引用台账", proc.stdout.split("## 需要复核")[0])

    def test_handwritten_entry_not_in_ledger(self) -> None:
        root = self._ledgered("研究表明\\cite{wu2021value,hand2024}。\n")
        bib = root / "references" / "refs.bib"
        bib.write_text(bib.read_text(encoding="utf-8") + "\n@article{hand2024,\n  title = {H},\n}\n", encoding="utf-8")
        report = check_project(root)
        self.assertEqual([(f.kind, f.detail) for f in report.errors if f.kind == "cite_not_in_ledger"], [("cite_not_in_ledger", "hand2024")])
        self.assertNotIn("no_citation_ledger", kinds(report.needs_review))

    def test_not_in_ledger_reported_once_per_key(self) -> None:
        root = build(self.base, body_11="甲\\cite{wu2021value}。\n乙\\cite{wu2021value}。\n", ledger=False)
        (proposal_paths(root).ledger).write_text("", encoding="utf-8")
        self.assertEqual(len([f for f in check_project(root).errors if f.kind == "cite_not_in_ledger"]), 1)

    def test_modified_entry(self) -> None:
        root = self._ledgered("多模态\\cite{wu2021value}。\n")
        bib = root / "references" / "refs.bib"
        bib.write_text(bib.read_text(encoding="utf-8").replace("{X}", "{Y}"), encoding="utf-8")
        report = check_project(root)
        self.assertEqual([f.detail for f in report.errors if f.kind == "bib_entry_modified"], ["wu2021value"])

    def test_unmodified_entry_is_clean(self) -> None:
        report = check_project(self._ledgered("多模态\\cite{wu2021value}。\n"))
        self.assertFalse(kinds(report.errors) & {"cite_not_in_ledger", "bib_entry_modified"})

    def test_register_user_entry_is_accepted(self) -> None:
        root = build(self.base, body_11="多模态\\cite{wu2021value}。\n", ledger=False)
        register_user_entries(root, ["wu2021value"])
        self.assertFalse(kinds(check_project(root).errors) & {"cite_not_in_ledger", "bib_entry_modified"})

    def test_dropped_entry_cited_is_error(self) -> None:
        root = self._ledgered("多模态\\cite{wu2021value}。\n")
        append_event(proposal_paths(root).ledger, {"event": "drop", "bibkey": "wu2021value", "time": "t", "reason": "r"})
        self.assertIn("cite_not_in_ledger", kinds(check_project(root).errors))

    def _number_details(self, body: str, abstract: str | None = ABSTRACT) -> list[str]:
        report = check_project(self._ledgered(body, abstract))
        return [f.detail for f in report.needs_review if f.kind == "number_not_in_evidence"]

    def test_decimal_not_in_abstract_is_flagged(self) -> None:
        details = self._number_details("某研究报道 AUC 为 0.91\\cite{wu2021value}。\n")
        self.assertEqual(len(details), 1)
        self.assertTrue(details[0].startswith("0.91："))
        self.assertIn("某研究报道", details[0])

    def test_decimal_in_abstract_is_not_flagged(self) -> None:
        self.assertEqual(self._number_details("某研究报道 AUC 为 0.86\\cite{wu2021value}。\n"), [])

    def test_prefix_of_longer_number_is_not_a_match(self) -> None:
        self.assertEqual(len(self._number_details("某研究报道 AUC 为 0.8\\cite{wu2021value}。\n")), 1)

    def test_escaped_percent_matches_plain_percent(self) -> None:
        self.assertEqual(self._number_details("灵敏度达 95\\%\\cite{wu2021value}。\n"), [])
        self.assertEqual(len(self._number_details("灵敏度达 96\\%\\cite{wu2021value}。\n")), 1)

    def test_thousands_separator_and_unit_integer(self) -> None:
        self.assertEqual(self._number_details("共纳入 1200 例\\cite{wu2021value}，边界 5 mm。\n"), [])
        self.assertEqual(len(self._number_details("共纳入 800 例\\cite{wu2021value}。\n")), 1)

    def test_year_is_not_a_number_to_check(self) -> None:
        self.assertEqual(self._number_details("2021 年的研究\\cite{wu2021value}。\n"), [])
        self.assertEqual(self._number_details("自 1998年起\\cite{wu2021value}。\n"), [])

    def test_thousands_separator_in_sentence(self) -> None:
        for abstract in ("The cohort had 1200 patients in total, enrolled over a long period at several centers.",
                         "The cohort had 1,200 patients in total, enrolled over a long period at several centers."):
            self.assertEqual(self._number_details("共纳入 1,200 例\\cite{wu2021value}。\n", abstract), [])
        details = self._number_details("共纳入 1,200 例\\cite{wu2021value}。\n", "Only 90 patients were enrolled in a small single center pilot study.")
        self.assertEqual(len(details), 1)
        self.assertTrue(details[0].startswith("1200："), details)
        self.assertEqual(self._number_details("共纳入 1{,}200 例\\cite{wu2021value}，1\\,200 例。\n",
                                              "A total of 1200 patients were enrolled across all of the participating centers."), [])

    def test_fullwidth_percent_and_ci_suffix(self) -> None:
        self.assertEqual(self._number_details("灵敏度达 95％\\cite{wu2021value}。\n"), [])
        self.assertEqual(len(self._number_details("灵敏度达 97％\\cite{wu2021value}。\n")), 1)
        self.assertEqual(self._number_details("灵敏度 95\\%CI 见\\cite{wu2021value}。\n"), [])
        details = self._number_details("灵敏度 97\\%CI\\cite{wu2021value}。\n")
        self.assertTrue(details and details[0].startswith("97%："), details)

    def test_range_with_percent_keeps_leading_decimal_plain(self) -> None:
        details = self._number_details("AUC 0.91 至 95\\%\\cite{wu2021value}。\n", "AUC 0.91 was reported in an earlier version of this study.")
        self.assertEqual([d.split("：")[0] for d in details], ["95%"])

    def test_percent_range_leading_decimal_by_connector(self) -> None:
        from consistency_check import sentence_numbers
        self.assertEqual(sentence_numbers("AUC 0.5-0.7%\\cite{k}"), ["0.5%", "0.7%"])
        self.assertEqual(sentence_numbers("AUC 0.5～0.7%\\cite{k}"), ["0.5%", "0.7%"])
        self.assertEqual(sentence_numbers("AUC 0.5至0.7%\\cite{k}"), ["0.5", "0.7%"])
        self.assertEqual(sentence_numbers("AUC 0.5到0.7%\\cite{k}"), ["0.5", "0.7%"])

    def test_abstract_space_thousands_separators(self) -> None:
        for sep in (" ", "\u2009", "\u202f", "\u00a0"):
            abstract = f"We enrolled 50{sep}132 asymptomatic adults in the screening programme over several years."
            self.assertEqual(self._number_details("共纳入 50132 名\\cite{wu2021value}。\n", abstract), [], repr(sep))
        wrong = "We enrolled 50 133 asymptomatic adults in the screening programme over several years."
        self.assertEqual(len(self._number_details("共纳入 50132 名\\cite{wu2021value}。\n", wrong)), 1)
        year = "In 2021 132 asymptomatic adults were enrolled in the screening programme over several years."
        self.assertEqual(len(self._number_details("共纳入 2021132 名\\cite{wu2021value}。\n", year)), 1)

    def test_decimal_equivalence_ignores_trailing_zeros(self) -> None:
        a = "The model reached an AUC of 0.620 in the validation cohort of the multicentre study."
        self.assertEqual(self._number_details("AUC 为 0.62\\cite{wu2021value}。\n", a), [])
        self.assertEqual(len(self._number_details("AUC 为 0.623\\cite{wu2021value}。\n", a)), 1)
        self.assertEqual(len(self._number_details("AUC 为 0.6\\cite{wu2021value}。\n", "AUC was 0.62 in the validation cohort of the multicentre study.")), 1)
        b = "The model reached an AUC of 0.62 in the validation cohort of the multicentre study."
        self.assertEqual(self._number_details("AUC 为 0.620\\cite{wu2021value}。\n", b), [])

    def test_space_thousands_is_read_both_ways(self) -> None:
        one = "Treatment groups 1 100 patients were compared in the screening programme over many years."
        self.assertEqual(self._number_details("共 100 名\\cite{wu2021value}。\n", one), [])
        self.assertEqual(self._number_details("共 1100 名\\cite{wu2021value}。\n", one), [])
        two = "We enrolled 50 132 adults in the screening programme over many years of follow up."
        self.assertEqual(self._number_details("共 50132 名\\cite{wu2021value}。\n", two), [])
        self.assertEqual(self._number_details("共 132 名\\cite{wu2021value}。\n", two), [])

    def test_trailing_zeros_need_a_decimal_point(self) -> None:
        table = "See Table 2 for the effect sizes reported across the multicentre validation cohort of this study."
        self.assertEqual(len(self._number_details("效应量为 2.0\\cite{wu2021value}。\n", table)), 1)
        a = "The hazard ratio was 2.50 across the multicentre validation cohort of this study as reported."
        self.assertEqual(self._number_details("风险比 2.5\\cite{wu2021value}。\n", a), [])
        b = "The hazard ratio was 2.5 across the multicentre validation cohort of this study as reported."
        self.assertEqual(self._number_details("风险比 2.50\\cite{wu2021value}。\n", b), [])
        c = "The hazard ratio was 2.00 across the multicentre validation cohort of this study as reported."
        self.assertEqual(self._number_details("风险比 2.0\\cite{wu2021value}。\n", c), [])

    def test_hyphenated_number_words_and_no_one(self) -> None:
        a = "A two-year follow up of the multicentre validation cohort was completed for this study as planned."
        self.assertEqual(self._number_details("随访 2 年\\cite{wu2021value}。\n", a), [])
        b = "One of the models was retained in the multicentre validation cohort of this study as planned."
        self.assertEqual(len(self._number_details("共 1 个模型\\cite{wu2021value}。\n", b)), 1)

    def test_english_number_words_in_abstract(self) -> None:
        a = "Only six features were retained after selection in the final model of the multicentre study."
        self.assertEqual(self._number_details("只有 6 个特征\\cite{wu2021value}。\n", a), [])
        self.assertEqual(len(self._number_details("只有 7 个特征\\cite{wu2021value}。\n", a)), 1)
        self.assertEqual(self._number_details("共 20 项\\cite{wu2021value}。\n", "TWENTY items were retained after selection in the final model of the study."), [])

    def test_percent_words_in_abstract(self) -> None:
        a = ("Energy use fell by 10–20 percent in treated households, sorting accuracy rose 7 percentage points, "
             "and contamination dropped 3.5 per cent, from 12 to 15 percent of bins over the study.")
        self.assertEqual(self._number_details("用电量下降10\\%至20\\%\\cite{wu2021value}。\n", a), [])
        self.assertEqual(self._number_details("正确率提高7个百分点\\cite{wu2021value}。\n", a), [])
        self.assertEqual(self._number_details("混投下降3.5\\%\\cite{wu2021value}。\n", a), [])
        self.assertEqual(self._number_details("占比由12\\%升至15\\%\\cite{wu2021value}。\n", a), [])
        self.assertEqual(len(self._number_details("用电量下降30\\%\\cite{wu2021value}。\n", a)), 1)
        self.assertEqual(len(self._number_details("正确率提高7\\%\\cite{wu2021value}。\n", a)), 1)

    def test_number_in_text_reads_percent_words(self) -> None:
        from consistency_check import number_in_text
        text = "Rates rose by 10-20 Percent and by 4.5 per cent; another arm gained 6 percentage-points."
        for value in ("10%", "20%", "4.5%"):
            self.assertTrue(number_in_text(value, text), value)
        self.assertFalse(number_in_text("6%", text))
        self.assertFalse(number_in_text("45%", text))
        self.assertTrue(number_in_text("10%", "Use fell by ten percent overall."))

    def test_month_after_year_is_not_extracted(self) -> None:
        from consistency_check import sentence_numbers
        self.assertEqual(sentence_numbers("2021年3月的研究\\cite{k}"), [])
        self.assertEqual(sentence_numbers("随访 3月\\cite{k}"), ["3"])

    def test_latex_lengths_are_not_extracted(self) -> None:
        from consistency_check import sentence_numbers
        self.assertEqual(sentence_numbers("\\hspace{1.5em}\\vspace{2.5pt}\\kern 0.5ex 结果\\cite{k}"), [])
        self.assertEqual(sentence_numbers("AUC 为 0.5\\cite{k}"), ["0.5"])

    def test_figure_width_is_not_a_cited_number(self) -> None:
        from consistency_check import sentence_numbers
        block = (
            "\\begin{figure}\n\\centering\n\\includegraphics*[width=0.95\\textwidth]{a.png}\n"
            "\\caption{研究框架图}\n\\end{figure}\n既往研究报告 AUC 为 0.86\\cite{k}"
        )
        self.assertEqual(sentence_numbers(block), ["0.86"])
        self.assertEqual(sentence_numbers("宽 0.95\\linewidth 与 0.9\\columnwidth 的版面\\cite{k}"), [])
        self.assertEqual(sentence_numbers("\\includegraphics[width=0.95\n\\textwidth]{a.png}\\cite{k}"), [])

    def test_cite_key_digits_are_ignored(self) -> None:
        self.assertEqual(self._number_details("AUC 为 0.86\\cite{wu2021value}。\n"), [])

    def test_number_in_sentence_without_cite_is_ignored(self) -> None:
        self.assertEqual(self._number_details("本项目拟纳入 300 例。AUC 为 0.86\\cite{wu2021value}。\n"), [])

    def test_number_is_checked_per_sentence(self) -> None:
        details = self._number_details("AUC 为 0.86\\cite{wu2021value}；另一结果 0.5 未引用。\n")
        self.assertEqual(details, [])

    def test_any_cited_abstract_is_enough(self) -> None:
        root = self._ledgered("AUC 为 0.77\\cite{wu2021value,other2020}。\n")
        bib = root / "references" / "refs.bib"
        bib.write_text(bib.read_text(encoding="utf-8") + "\n@article{other2020,\n  title = {O},\n}\n", encoding="utf-8")
        text = bib_entry_texts([bib])["other2020"]
        append_event(proposal_paths(root).ledger, add_event("other2020", source="openalex", entry_text=text, doi=None,
                                                              abstract="The AUC was 0.77 overall.", provenance={}))
        self.assertNotIn("number_not_in_evidence", kinds(check_project(root).needs_review))

    def test_no_abstract_at_all_gets_own_review_kind(self) -> None:
        report = check_project(self._ledgered("AUC 为 0.91\\cite{wu2021value}。无数字句\\cite{wu2021value}。\n", abstract=None))
        found = [f for f in report.needs_review if f.kind == "no_abstract_for_numbers"]
        self.assertEqual(len(found), 1)
        self.assertNotIn("number_not_in_evidence", kinds(report.needs_review))

    def test_no_number_checks_without_ledger(self) -> None:
        report = check_project(build(self.base, body_11="AUC 为 0.91\\cite{wu2021value}。\n", ledger=False))
        self.assertFalse(kinds(report.needs_review) & {"number_not_in_evidence", "no_abstract_for_numbers"})

    def test_cli_exit_code_follows_errors(self) -> None:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        root = self._ledgered("多模态\\cite{wu2021value}。\n")
        write_yaml(root / "proposal" / "section_plan.yaml", {"version": 1, "files": [
            {"file": "extraTex/1.1.立项依据.tex", "writer": "w", "written_with_case_version": 2}]})
        cmd = [sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(root)]
        self.assertEqual(subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60).returncode, 0)
        bib = root / "references" / "refs.bib"
        bib.write_text(bib.read_text(encoding="utf-8").replace("{X}", "{Z}"), encoding="utf-8")
        bad = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("手改", bad.stdout)


class MultiLineCiteTest(unittest.TestCase):
    """跨行的 \\cite：key 列表或右花括号在下一行，引用句跨行。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _report(self, body: str, abstract: str | None = None):
        self.count = getattr(self, "count", 0) + 1
        root = build(self.base / f"n{self.count}", body_11=body)
        if abstract is not None:
            text = bib_entry_texts([root / "references" / "refs.bib"])["wu2021value"]
            append_event(proposal_paths(root).ledger, add_event(
                "wu2021value", source="crossref", entry_text=text, doi=None, abstract=abstract, provenance={}))
        return check_project(root)

    def _missing(self, report) -> list[tuple[str, int]]:
        return [(f.detail, f.line) for f in report.errors if f.kind == "missing_bibkey"]

    def test_key_list_continues_on_next_line(self) -> None:
        report = self._report("多模态影像信息。\n已有研究\\cite{wu2021value,\n  fake2099}。\n")
        self.assertEqual(self._missing(report), [("fake2099", 2)])
        self.assertEqual(report.citations["extraTex/1.1.立项依据.tex"], 2)

    def test_key_starts_on_next_line(self) -> None:
        report = self._report("多模态影像信息。\n灵敏度达 95\\%\\cite{\nfake2098}。\n")
        self.assertEqual(self._missing(report), [("fake2098", 2)])

    def test_comment_inside_cite_is_stripped(self) -> None:
        report = self._report("多模态\\cite{wu2021value,% 第二篇\n  fake2097}。\n")
        self.assertEqual(self._missing(report), [("fake2097", 1)])

    def test_unledgered_key_on_next_line(self) -> None:
        root = build(self.base, body_11="多模态\\cite{wu2021value,\nhand2024}。\n")
        bib = root / "references" / "refs.bib"
        bib.write_text(bib.read_text(encoding="utf-8") + "\n@article{hand2024,\n  title = {H},\n}\n", encoding="utf-8")
        found = [(f.detail, f.line) for f in check_project(root).errors if f.kind == "cite_not_in_ledger"]
        self.assertEqual(found, [("hand2024", 1)])

    def _number_findings(self, body: str) -> list:
        return [f for f in self._report(body, ABSTRACT).needs_review if f.kind == "number_not_in_evidence"]

    def test_number_and_cite_on_different_lines(self) -> None:
        self.assertEqual(self._number_findings("多模态。某研究报道灵敏度达\n95\\%\\cite{wu2021value}。\n"), [])
        found = self._number_findings("多模态。\n某研究报道灵敏度达 96\\%\n\\cite{wu2021value}。\n")
        self.assertEqual([(f.detail.split("：")[0], f.line) for f in found], [("96%", 2)])

    def test_comment_line_does_not_end_the_sentence(self) -> None:
        found = self._number_findings("多模态。灵敏度达 96\\%\n% 出处见下\n\\cite{wu2021value}。\n")
        self.assertEqual([f.detail.split("：")[0] for f in found], ["96%"])

    def test_blank_line_ends_the_sentence(self) -> None:
        self.assertEqual(self._number_findings("共纳入 800 例\n\n多模态影像信息\\cite{wu2021value}。\n"), [])


class TemplateBibTest(unittest.TestCase):
    """projects/NSFC_Young 的副本：模板自带的示例文献在 init 之后仍未入账，引用它们报 cite_not_in_ledger。"""

    def test_template_sample_entries_cannot_be_cited_after_init(self) -> None:
        template = ROOT / "projects" / "NSFC_Young"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            shutil.copytree(template / "extraTex", root / "extraTex")
            shutil.copytree(template / "references", root / "references")
            shutil.copy2(template / "main.tex", root / "main.tex")
            body = root / "extraTex" / "1.1.立项依据.tex"
            body.write_text(body.read_text(encoding="utf-8") + "\n职业发展理论\\cite{Smith1900}。\n", encoding="utf-8")
            result = init_proposal(root, title="T", project_type="青年科学基金")
            self.assertTrue(any("未入引用台账" in w and "Smith1900" in w for w in result.warnings), result.warnings)
            report = check_project(root)
            flagged = {f.detail for f in report.errors if f.kind == "cite_not_in_ledger"}
            self.assertIn("Smith1900", flagged)
            self.assertTrue({"Smith2020", "Super1957", "Johnson2019"} <= flagged, flagged)
            env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
            proc = subprocess.run([sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(root)],
                                  env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("Smith1900", proc.stdout)


class ProcessTextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _hits(self, body: str) -> list:
        self.count = getattr(self, "count", 0) + 1
        return [f for f in check_project(build(self.base / f"n{self.count}", body_11=body)).needs_review if f.kind == "process_text_in_body"]

    def test_default_patterns_come_from_config(self) -> None:
        self.assertIn("经核实", load_config()["consistency"]["process_text_patterns"])

    def test_body_text_is_flagged_with_hit_and_sentence(self) -> None:
        hits = self._hits("多模态影像信息。\n这一推测没有经核实的文献支持。\n")
        self.assertEqual(len(hits), 1)
        self.assertEqual((hits[0].file, hits[0].line), ("extraTex/1.1.立项依据.tex", 2))
        self.assertIn("经核实", hits[0].detail)
        self.assertIn("这一推测没有经核实的文献支持", hits[0].detail)

    def test_text_inside_placeholder_is_not_flagged(self) -> None:
        self.assertEqual(self._hits("多模态。【待补充：经检索核实的文献】\n"), [])

    def test_text_in_latex_comment_is_not_flagged(self) -> None:
        self.assertEqual(self._hits("多模态。 % 此处未经核实，见 assumptions.md\n"), [])

    def test_text_after_placeholder_on_same_line_is_flagged(self) -> None:
        self.assertEqual(len(self._hits("【待补充：预实验结果】已见台账记录。\n")), 1)

    def test_markdown_file_scanned_in_full(self) -> None:
        root = build(self.base, body_11="多模态。\n")
        (root / "NSFC-ABSTRACTS.md").write_text("<!-- 见 evidence_map.yaml -->\n摘要正文。\n", encoding="utf-8")
        hits = [f for f in check_project(root).needs_review if f.kind == "process_text_in_body"]
        self.assertEqual([(f.file, f.line) for f in hits], [("NSFC-ABSTRACTS.md", 1)])

    def test_patterns_are_configurable(self) -> None:
        root = build(self.base, body_11="多模态。\n这里有哨兵词。\n")
        config = {"consistency": {"process_text_patterns": ["哨兵词"]}}
        hits = [f for f in check_project(root, config).needs_review if f.kind == "process_text_in_body"]
        self.assertEqual(len(hits), 1)
        self.assertEqual([f for f in check_project(root, {"consistency": {}}).needs_review if f.kind == "process_text_in_body"], [])

    def test_ai_declaration_is_exempt_but_body_is_not(self) -> None:
        wording = "本稿经核实的文献均已入台账。\n"
        root = build(self.base, body_11="多模态。\n" + wording)
        (root / "proposal" / "ai_declaration.md").write_text(wording, encoding="utf-8")
        write_yaml(root / "proposal" / "section_plan.yaml", {"version": 1, "files": [
            {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "written_with_case_version": 2},
            {"file": "proposal/ai_declaration.md", "writer": "nsfc-proposal", "written_with_case_version": None}]})
        hits = [f for f in check_project(root).needs_review if f.kind == "process_text_in_body"]
        self.assertEqual([f.file for f in hits], ["extraTex/1.1.立项依据.tex"])

    def test_process_wording_from_e2e_is_flagged(self) -> None:
        for sentence in ("建议申请人在补充时优先给出论文。", "以下各处保留占位，由申请人按实际情况补充；不补充的条目应在提交前删去。",
                         "申请人提出的原始口径是三年。"):
            self.assertGreaterEqual(len(self._hits(f"多模态。\n{sentence}\n")), 1, sentence)

    def test_wording_meant_for_the_applicant_is_flagged(self) -> None:
        for sentence in ("这些论文将在正式申请书中按三类列出。", "正式稿中补全设备型号。", "请申请人补充合作单位名称。"):
            self.assertGreaterEqual(len(self._hits(f"多模态。\n{sentence}\n")), 1, sentence)


class NonstandardPlaceholderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _root(self, abstracts: str, body_11: str = "多模态影像信息\\cite{wu2021value}。\n") -> Path:
        self.count = getattr(self, "count", 0) + 1
        root = build(self.base / f"n{self.count}", body_11=body_11)
        (root / "NSFC-ABSTRACTS.md").write_text(abstracts, encoding="utf-8")
        write_yaml(root / "proposal" / "section_plan.yaml", {"version": 1, "files": [
            {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "written_with_case_version": 2},
            {"file": "NSFC-ABSTRACTS.md", "writer": "nsfc-abstract", "written_with_case_version": None}]})
        return root

    def _errors(self, root: Path) -> list:
        return [f for f in check_project(root).errors if f.kind == "placeholder_nonstandard"]

    def test_snippet_comes_from_the_scanned_occurrence(self) -> None:
        root = self._root("【待补充：见 [TBD later] 说明】然后 [TBD later] 才是占位。\n")
        found = self._errors(root)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].detail.startswith("[TBD later] 才是"), found[0].detail)

    def test_english_bracket_placeholder_is_an_error(self) -> None:
        root = self._root("Prior work [to be supplied: prior findings] shows.\n")
        found = self._errors(root)
        self.assertEqual([(f.file, f.line) for f in found], [("NSFC-ABSTRACTS.md", 1)])
        self.assertIn("[to be supplied: prior findings]", found[0].detail)
        self.assertIn("【待补充", found[0].detail)
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        proc = subprocess.run([sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(root)],
                              env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("占位写法不规范", proc.stdout)

    def test_standard_listed_placeholder_is_clean(self) -> None:
        root = self._root("前期结果【待补充：预实验结果】已有报道。\n")
        self.assertEqual(self._errors(root), [])

    def test_latex_comment_is_left_to_hidden_placeholder(self) -> None:
        root = self._root("摘要。\n", body_11="多模态影像信息\\cite{wu2021value}。 % [TBD later\n")
        self.assertEqual(self._errors(root), [])

    def test_other_variants_and_config(self) -> None:
        for text in ("数据量 [TBD]。", "结果［待补充］。", "样本 XXX 例。", "【请补充：样本量】"):
            self.assertEqual(len(self._errors(self._root(text + "\n"))), 1, text)
        self.assertEqual(self._errors(self._root("尺码 XXXL 的口罩。\n")), [])
        self.assertIn("XXX", "".join(load_config()["consistency"]["nonstandard_placeholder_patterns"]))

    def _ai_declaration_root(self, text: str) -> Path:
        root = self._root("摘要。\n")
        (root / "proposal" / "ai_declaration.md").write_text(text, encoding="utf-8")
        write_yaml(root / "proposal" / "section_plan.yaml", {"version": 1, "files": [
            {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "written_with_case_version": 2},
            {"file": "proposal/ai_declaration.md", "writer": "nsfc-proposal", "written_with_case_version": None}]})
        return root

    def test_placeholder_format_reference_is_exempt_in_ai_declaration(self) -> None:
        for text in ("未提供的内容以【待补充：……】标出。\n", "格式为【待补充：...】。\n", "格式为【待补充：  】。\n"):
            report = check_project(self._ai_declaration_root(text))
            self.assertEqual([f for f in report.errors if f.kind == "placeholder_unlisted"], [], text)
            self.assertEqual([f for f in report.placeholders if f.file == "proposal/ai_declaration.md"], [], text)
            self.assertEqual([f for f in report.needs_review if f.kind == "empty_placeholder"], [], text)

    def test_empty_placeholder_in_writing_sections_goes_to_needs_review(self) -> None:
        for text in ("未提供的内容以【待补充：……】标出。\n", "格式为【待补充：...】。\n", "格式为【待补充：  】。\n"):
            report = check_project(self._root(text))
            reviews = [f for f in report.needs_review if f.kind == "empty_placeholder"]
            self.assertEqual([f.file for f in reviews], ["NSFC-ABSTRACTS.md"], text)
            self.assertIn("没有写明要补什么", reviews[0].detail)
            self.assertEqual([f for f in report.errors if f.kind == "placeholder_unlisted"], [], text)
            self.assertEqual([f for f in report.placeholders if f.file == "NSFC-ABSTRACTS.md"], [], text)
        tex = check_project(self._root("摘要。\n", body_11="多模态影像信息\\cite{wu2021value}。【待补充：……】\n"))
        self.assertEqual([f.file for f in tex.needs_review if f.kind == "empty_placeholder"], ["extraTex/1.1.立项依据.tex"])

    def test_real_unlisted_placeholder_still_errors(self) -> None:
        root = self._root("前期结果【待补充：未列入的条目】。\n")
        self.assertEqual([f.detail for f in check_project(root).errors if f.kind == "placeholder_unlisted"],
                         ["【待补充：未列入的条目】"])


class CitationCountTest(unittest.TestCase):
    """立项依据引用的不同文献数与下限（literature.min_distinct_refs_justification）。"""

    BODY = "\n".join([
        "已有研究报告了该现象\\cite{wu2021value}。",
        "另一项研究给出相反结果\\cite{wu2021value,lee2022}。",
        "% 注释里的引用\\cite{ghost2020}",
    ]) + "\n"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = build(Path(self.tmp.name), body_11=self.BODY)
        bib = self.root / "references" / "refs.bib"
        bib.write_text(bib.read_text(encoding="utf-8") + "@article{lee2022,\n  title = {Y},\n}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _report(self, floor: int):
        return check_project(self.root, {"literature": {"min_distinct_refs_justification": floor}})

    def test_distinct_keys_counted_and_below_floor_flagged(self) -> None:
        report = self._report(3)
        self.assertEqual(report.citations["extraTex/1.1.立项依据.tex"], 2)
        self.assertEqual(report.to_dict()["citations"]["extraTex/1.1.立项依据.tex"], 2)
        few = [f for f in report.needs_review if f.kind == "few_citations"]
        self.assertEqual(len(few), 1)
        self.assertIn("2", few[0].detail)
        self.assertIn("3", few[0].detail)

    def test_at_floor_is_clean(self) -> None:
        self.assertEqual([f for f in self._report(2).needs_review if f.kind == "few_citations"], [])

    def test_commented_cite_not_counted(self) -> None:
        self.assertEqual(self._report(3).citations["extraTex/1.1.立项依据.tex"], 2)

    def test_missing_config_key_uses_default_floor(self) -> None:
        report = check_project(self.root, {"literature": {}})
        self.assertEqual([f.kind for f in report.needs_review if f.kind == "few_citations"], ["few_citations"])
        self.assertIn("30", [f for f in report.needs_review if f.kind == "few_citations"][0].detail)

    def test_other_writers_never_flagged(self) -> None:
        report = self._report(99)
        flagged = [f.file for f in report.needs_review if f.kind == "few_citations"]
        self.assertEqual(flagged, ["extraTex/1.1.立项依据.tex"])
        self.assertEqual(report.citations["extraTex/2.1.研究内容.tex"], 0)

    def test_default_config_has_floor(self) -> None:
        self.assertEqual(load_config()["literature"]["min_distinct_refs_justification"], 30)


class MissingFigureFileTest(unittest.TestCase):
    """\\includegraphics 指向的文件不存在时报 missing_figure_file。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = build(Path(self.tmp.name), body_11="多模态影像信息\\cite{wu2021value}。\n【待补充：预实验结果】\n")
        write_yaml(self.root / "proposal" / "section_plan.yaml", {"version": 1, "files": [
            {"file": "extraTex/1.1.立项依据.tex", "writer": "nsfc-justification-writer", "written_with_case_version": 2},
            {"file": "extraTex/2.1.研究内容.tex", "writer": "nsfc-research-content-writer", "written_with_case_version": 2}]})
        (self.root / "figures" / "nsfc-proposal").mkdir(parents=True)

    def body(self, text: str) -> None:
        (self.root / "extraTex" / "2.1.研究内容.tex").write_text(text, encoding="utf-8")

    def missing(self) -> list:
        return [f for f in check_project(self.root).errors if f.kind == "missing_figure_file"]

    def test_missing_file_is_error_and_cli_exits_1(self) -> None:
        self.body("研究内容。\n\\begin{figure}[htbp]\n\\includegraphics[width=\\linewidth]{figures/nsfc-proposal/fig9.png}\n\\end{figure}\n")
        [finding] = self.missing()
        self.assertEqual((finding.file, finding.line), ("extraTex/2.1.研究内容.tex", 3))
        self.assertIn("figures/nsfc-proposal/fig9.png", finding.detail)
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        cmd = [sys.executable, str(SCRIPTS / "consistency_check.py"), "--project-root", str(self.root)]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("图片文件不存在", proc.stdout)
        (self.root / "figures" / "nsfc-proposal" / "fig9.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        self.assertEqual(self.missing(), [])
        ok = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_extensionless_path_tries_known_extensions(self) -> None:
        self.body("\\includegraphics{figures/nsfc-proposal/fig2}\n")
        self.assertEqual(len(self.missing()), 1)
        for ext in (".jpeg", ".jpg", ".pdf", ".png"):
            target = self.root / "figures" / "nsfc-proposal" / f"fig2{ext}"
            target.write_bytes(b"x")
            self.assertEqual(self.missing(), [], ext)
            target.unlink()

    def test_commented_and_cross_line_includegraphics(self) -> None:
        self.body("% \\includegraphics{figures/nsfc-proposal/old.png}\n"
                  "图示 \\includegraphics[\n  width=0.95\\textwidth]{figures/nsfc-proposal/new.png}\n")
        [finding] = self.missing()
        self.assertEqual(finding.line, 2)
        self.assertIn("new.png", finding.detail)

    def test_figure_path_is_not_process_text(self) -> None:
        (self.root / "figures" / "nsfc-proposal" / "fig1-framework.png").write_bytes(b"x")
        self.body("\\begin{figure}[htbp]\n  \\includegraphics[width=0.95\\textwidth]{figures/nsfc-proposal/fig1-framework.png}\n"
                  "  \\caption{研究框架。}\n  \\label{fig:np-framework}\n\\end{figure}\n如图~\\ref{fig:np-framework}所示。\n")
        report = check_project(self.root)
        self.assertEqual(self.missing(), [])
        self.assertEqual([f for f in report.needs_review if f.kind == "process_text_in_body"], [])
        self.body("草稿见 proposal/assumptions.md。\n")
        self.assertTrue([f for f in check_project(self.root).needs_review if f.kind == "process_text_in_body"])

    def test_star_space_and_split_forms(self) -> None:
        forms = {
            "split": "图示\n\\includegraphics[width=0.95\\textwidth]\n  {figures/nsfc-proposal/fig5.png}\n",
            "space": "图示\n\\includegraphics [width=0.95\\textwidth] {figures/nsfc-proposal/fig5.png}\n",
            "star": "图示\n\\includegraphics*{figures/nsfc-proposal/fig5.png}\n",
        }
        target = self.root / "figures" / "nsfc-proposal" / "fig5.png"
        for label, text in forms.items():
            self.body(text)
            target.unlink(missing_ok=True)
            report = check_project(self.root)
            missing = [f for f in report.errors if f.kind == "missing_figure_file"]
            self.assertEqual([(f.line, "fig5.png" in f.detail) for f in missing], [(2, True)], label)
            self.assertEqual([f for f in report.needs_review if f.kind == "process_text_in_body"], [], label)
            target.write_bytes(b"x")
            report = check_project(self.root)
            self.assertEqual([f for f in report.errors if f.kind == "missing_figure_file"], [], label)
            self.assertEqual([f for f in report.needs_review if f.kind == "process_text_in_body"], [], label)

    def test_split_command_keeps_real_process_text(self) -> None:
        (self.root / "figures" / "nsfc-proposal" / "fig6.png").write_bytes(b"x")
        self.body("\\includegraphics[width=\\linewidth]\n{figures/nsfc-proposal/fig6.png}经核实的文献表明。\n")
        hits = [f for f in check_project(self.root).needs_review if f.kind == "process_text_in_body"]
        self.assertEqual([(f.line, "经核实" in f.detail, "proposal/" in f.detail) for f in hits], [(2, True, False)])

    def test_path_outside_project_root_is_reported(self) -> None:
        (self.root.parent / "outside.png").write_bytes(b"x")
        self.body("\\includegraphics{../outside.png}\n")
        [finding] = self.missing()
        self.assertIn("../outside.png", finding.detail)


if __name__ == "__main__":
    unittest.main()
