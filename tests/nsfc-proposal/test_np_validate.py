from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

from case_validate import validate_all, validate_case, validate_evidence, validate_plan  # noqa: E402
from proposal_common import write_yaml  # noqa: E402


def valid_case() -> dict:
    return {
        "version": 1, "status": "draft",
        "project": {"type": "青年科学基金", "title": "基于多模态影像深度学习的肺磨玻璃结节浸润性预测研究", "sections": ["立项依据", "研究内容", "研究基础"]},
        "research_object": {"object": "持续存在的肺磨玻璃结节", "target_population": "低剂量 CT 筛查发现 GGN 的人群",
                            "sample_source": "手术切除并有病理诊断的病例", "sample_vs_target_gap": "手术病例偏向高风险结节",
                            "bias_handling": "说明外推边界", "source": "ai_proposed"},
        "terms": [{"term": "多模态", "definition": "同一次 CT 中瘤内、瘤周、影像组学与深度特征及临床语义信息", "source": "ai_proposed"}],
        "importance": [{"text": "GGN 检出增多", "claim_ids": ["C1"]}],
        "gaps": [{"id": "G1", "text": "瘤周信息的独立贡献未量化", "claim_ids": ["C2"]}],
        "mainstream_routes": [{"name": "影像组学", "limitation": "多为单中心", "claim_ids": ["C2"]}],
        "questions": [{"id": "Q1", "text": "瘤周纹理是否提供独立于瘤内的浸润信息？", "answers_gaps": ["G1"]}],
        "hypothesis": {"statement": "瘤周多尺度纹理携带独立浸润信息", "rationale": ["浸润伴随间质反应"],
                       "predictions": ["调整大小与实性比例后仍有增量"],
                       "falsification": {"condition": "外部队列中增量无统计学意义", "metric": "AUC 差"}},
        "entry_point": "把对应关系的成立条件作为检验对象",
        "aim": "界定瘤周信息的增量与适用边界",
        "tasks": [{"id": "T1", "question": "Q1", "aim": "检验瘤周增量", "indicator": "AUC 差",
                   "baselines": ["病灶大小+实性成分比例模型"], "confounders": ["病灶大小"], "validation": "独立外部队列",
                   "subtasks": [], "depends_on": []}],
        "constraints": [],
        "feasibility": [{"kind": "preliminary", "text": "预实验结果", "source": "missing"}],
        "risks": [{"category": "technical", "risk": "外部数据不足", "mitigation": "多中心合作"},
                  {"category": "schedule", "risk": "伦理审批延迟", "mitigation": "提前申报"},
                  {"category": "resource", "risk": "标注人力不足", "mitigation": "分批标注"}],
    }


def valid_evidence() -> dict:
    return {"version": 1, "claims": [
        {"id": "C1", "text": "GGN 检出增多", "sections": ["立项依据"], "type": "background", "support": "single_verified",
         "evidence": [{"ref": "wu2021value", "role": "supporting", "basis": "full_abstract"}]},
        {"id": "C2", "text": "瘤周独立贡献未量化", "sections": ["立项依据"], "type": "gap", "support": "unsupported",
         "evidence": [{"ref": "lead:L1", "role": "supporting", "basis": "full_abstract"}]},
    ]}


def valid_plan() -> dict:
    return {"version": 1, "files": [
        {"file": "extraTex/1.1.立项依据.tex", "section": "立项依据", "must_include": ["G1", "Q1", "hypothesis", "entry_point"],
         "must_exclude": ["技术路线"], "length": {"min": 4500, "max": 10000, "unit": "cjk_chars"}, "placeholders": [], "written_with_case_version": None},
        {"file": "extraTex/3.1.研究基础.tex", "section": "研究基础", "must_include": ["feasibility", "risks"],
         "must_exclude": [], "length": None, "placeholders": ["【待补充：预实验结果】"], "written_with_case_version": None},
    ]}


class ValidCaseTest(unittest.TestCase):
    def test_valid_files_have_no_problems(self) -> None:
        self.assertEqual(validate_all(valid_case(), valid_evidence(), valid_plan(), bib_keys={"wu2021value"}), [])


class CaseRuleTest(unittest.TestCase):
    def _errors(self, mutate) -> list[str]:
        case = valid_case()
        mutate(case)
        return validate_case(case, valid_evidence())

    def assertProblem(self, mutate, fragment: str) -> None:
        errors = self._errors(mutate)
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_question_must_end_with_question_mark(self) -> None:
        self.assertProblem(lambda c: c["questions"][0].update(text="瘤周纹理提供独立信息"), "问号")

    def test_question_must_answer_existing_gap(self) -> None:
        self.assertProblem(lambda c: c["questions"][0].update(answers_gaps=["G9"]), "G9")
        self.assertProblem(lambda c: c["questions"][0].update(answers_gaps=[]), "至少回应一个缺口")

    def test_falsification_required(self) -> None:
        self.assertProblem(lambda c: c["hypothesis"]["falsification"].update(metric=""), "falsification")

    def test_task_links(self) -> None:
        self.assertProblem(lambda c: c["tasks"][0].update(question="Q7"), "Q7")
        self.assertProblem(lambda c: c.update(tasks=[]), "没有对应的研究任务")

    def test_baselines_required(self) -> None:
        self.assertProblem(lambda c: c["tasks"][0].update(baselines=[]), "必比基线")

    def test_sample_gap_and_terms_required(self) -> None:
        self.assertProblem(lambda c: c["research_object"].update(sample_vs_target_gap=""), "sample_vs_target_gap")
        self.assertProblem(lambda c: c.update(terms=[]), "terms")

    def test_three_risks_when_writing_foundation(self) -> None:
        self.assertProblem(lambda c: c.update(risks=c["risks"][:2]), "risks 至少 3 条")
        case = valid_case()
        case["project"]["sections"] = ["立项依据"]
        case["risks"] = []
        self.assertFalse(any("risks" in e for e in validate_case(case, valid_evidence())))

    def test_claim_refs_need_evidence_map(self) -> None:
        self.assertProblem(lambda c: c["gaps"][0].update(claim_ids=["C9"]), "C9")
        self.assertTrue(any("evidence_map" in e for e in validate_case(valid_case(), None)))

    def test_wrong_types_reported_without_exception(self) -> None:
        case = valid_case()
        case["questions"] = "Q1"
        case["tasks"] = ["T1"]
        case["version"] = "2"
        errors = validate_case(case, valid_evidence())
        self.assertTrue(any("questions 必须是列表" in e for e in errors), errors)
        self.assertTrue(any("tasks[0]" in e for e in errors), errors)
        self.assertTrue(any("version" in e for e in errors), errors)

    def test_unhashable_enum_values_do_not_raise(self) -> None:
        case = valid_case()
        case["status"] = ["draft"]  # list instead of string
        errors = validate_case(case, valid_evidence())
        self.assertTrue(any("status" in e for e in errors), errors)
        self.assertFalse(any("TypeError" in str(type(e)) for e in errors))

        case = valid_case()
        case["research_object"]["source"] = {"a": 1}  # dict instead of string
        errors = validate_case(case, valid_evidence())
        self.assertTrue(any("source" in e for e in errors), errors)
        self.assertFalse(any("TypeError" in str(type(e)) for e in errors))


class EvidenceRuleTest(unittest.TestCase):
    def test_overclaimed_support(self) -> None:
        evidence = valid_evidence()
        evidence["claims"][0]["support"] = "multi_verified"
        self.assertTrue(any("multi_verified" in e for e in validate_evidence(evidence, {"wu2021value"})))

    def test_leads_and_snippets_do_not_count(self) -> None:
        evidence = valid_evidence()
        evidence["claims"][1]["support"] = "single_verified"
        self.assertTrue(any("C2" in e for e in validate_evidence(evidence, {"wu2021value"})))

    def test_bibkey_must_exist(self) -> None:
        self.assertTrue(any("wu2021value" in e for e in validate_evidence(valid_evidence(), set())))

    def test_applicant_material_only_for_applicant_results(self) -> None:
        evidence = valid_evidence()
        evidence["claims"][0]["support"] = "applicant_material"
        self.assertTrue(any("applicant_material" in e for e in validate_evidence(evidence, {"wu2021value"})))

    def test_duplicate_ids_and_bad_enums(self) -> None:
        evidence = valid_evidence()
        evidence["claims"][1]["id"] = "C1"
        evidence["claims"][0]["type"] = "opinion"
        errors = validate_evidence(evidence, {"wu2021value"})
        self.assertTrue(any("重复" in e for e in errors), errors)
        self.assertTrue(any("type" in e for e in errors), errors)

    def test_unhashable_enum_values_do_not_raise(self) -> None:
        evidence = valid_evidence()
        evidence["claims"][0]["support"] = ["single_verified"]  # list instead of string
        errors = validate_evidence(evidence, {"wu2021value"})
        self.assertTrue(any("support" in e for e in errors), errors)
        self.assertFalse(any("TypeError" in str(type(e)) for e in errors))

        evidence = valid_evidence()
        evidence["claims"][0]["type"] = {"a": 1}  # dict instead of string
        errors = validate_evidence(evidence, {"wu2021value"})
        self.assertTrue(any("type" in e for e in errors), errors)

        evidence = valid_evidence()
        evidence["claims"][0]["evidence"][0]["role"] = [1]  # list instead of string
        errors = validate_evidence(evidence, {"wu2021value"})
        self.assertTrue(any("role" in e for e in errors), errors)

    def test_duplicate_refs_counted_as_one_paper(self) -> None:
        evidence = valid_evidence()
        # Add a second entry with same bibkey to C1 (which already has one supporting entry with wu2021value)
        evidence["claims"][0]["evidence"].append({"ref": "wu2021value", "role": "supporting", "basis": "full_abstract"})
        evidence["claims"][0]["support"] = "multi_verified"  # mark as multi_verified but it's really just one paper
        # Now it has two entries with wu2021value, but they should be counted as one distinct paper
        errors = validate_evidence(evidence, {"wu2021value"})
        # C1 is marked as multi_verified but only has one distinct verified paper, so it should error
        self.assertTrue(any("C1" in e and "multi_verified" in e for e in errors), errors)


def ledger_record(event: str, abstract: str | None = None) -> dict:
    return {"event": event, "bibkey": "k", "source": "user" if event == "register_user" else "crossref", "abstract": abstract}


ABSTRACT = "A multicentre cohort study reported the incremental value of peritumoral features for invasiveness."


def two_ref_claim(basis: str = "full_abstract", support: str = "multi_verified", claim_type: str = "background") -> dict:
    return {"version": 1, "claims": [
        {"id": "C1", "text": "瘤周特征有增量价值", "sections": ["立项依据"], "type": claim_type, "support": support,
         "evidence": [{"ref": "a2020", "role": "supporting", "basis": basis},
                      {"ref": "b2021", "role": "supporting", "basis": basis}]}]}


class EvidenceLedgerTest(unittest.TestCase):
    BIB = {"a2020", "b2021"}

    def test_register_user_refs_do_not_reach_multi_verified(self) -> None:
        ledger = {"a2020": ledger_record("register_user"), "b2021": ledger_record("register_user")}
        errors = validate_evidence(two_ref_claim(), self.BIB, ledger)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("只够 unsupported", errors[0])
        for key in ("a2020", "b2021"):
            self.assertIn(key, errors[0])
        self.assertIn("register_user", errors[0])

    def test_register_user_refs_do_not_reach_single_verified(self) -> None:
        ledger = {"a2020": ledger_record("register_user"), "b2021": ledger_record("register_user")}
        errors = validate_evidence(two_ref_claim(support="single_verified"), self.BIB, ledger)
        self.assertTrue(any("只够 unsupported" in e for e in errors), errors)

    def test_two_add_refs_with_abstracts_reach_multi_verified(self) -> None:
        ledger = {"a2020": ledger_record("add", ABSTRACT), "b2021": ledger_record("add", ABSTRACT)}
        self.assertEqual(validate_evidence(two_ref_claim(), self.BIB, ledger), [])

    def test_full_abstract_basis_needs_ledger_abstract(self) -> None:
        ledger = {"a2020": ledger_record("add", ABSTRACT), "b2021": ledger_record("add", None)}
        errors = validate_evidence(two_ref_claim(), self.BIB, ledger)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("只够 single_verified", errors[0])
        self.assertIn("b2021", errors[0])
        self.assertIn("摘要", errors[0])
        self.assertNotIn("a2020", errors[0])

    def test_fulltext_basis_counts_add_without_abstract(self) -> None:
        ledger = {"a2020": ledger_record("add", None), "b2021": ledger_record("add", None)}
        self.assertEqual(validate_evidence(two_ref_claim(basis="fulltext"), self.BIB, ledger), [])

    def test_ref_missing_from_ledger_is_not_counted(self) -> None:
        ledger = {"a2020": ledger_record("add", ABSTRACT)}
        errors = validate_evidence(two_ref_claim(), self.BIB, ledger)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("b2021", errors[0])
        self.assertIn("台账", errors[0])

    def test_register_user_still_backs_applicant_results(self) -> None:
        ledger = {"a2020": ledger_record("register_user"), "b2021": ledger_record("register_user")}
        evidence = two_ref_claim(support="applicant_material", claim_type="applicant_result")
        self.assertEqual(validate_evidence(evidence, self.BIB, ledger), [])

    def test_without_ledger_behavior_is_unchanged(self) -> None:
        self.assertEqual(validate_evidence(two_ref_claim(), self.BIB), [])
        self.assertEqual(validate_evidence(two_ref_claim(), self.BIB, None), [])


class PlanRuleTest(unittest.TestCase):
    def test_unknown_must_include(self) -> None:
        plan = valid_plan()
        plan["files"][0]["must_include"].append("Q9")
        self.assertTrue(any("Q9" in e for e in validate_plan(plan, valid_case())))

    def test_unknown_must_include_lists_allowed_fields(self) -> None:
        plan = valid_plan()
        plan["files"][0]["must_include"].extend(["科学假设", "C3"])
        errors = validate_plan(plan, valid_case())
        for ref in ("科学假设", "C3"):
            hit = [e for e in errors if ref in e]
            self.assertTrue(hit, ref)
            self.assertIn("hypothesis", hit[0])
            self.assertIn("研究任务的 id", hit[0])

    def test_foundation_placeholders_cover_missing_feasibility(self) -> None:
        plan = valid_plan()
        plan["files"][1]["placeholders"] = []
        self.assertTrue(any("placeholders" in e for e in validate_plan(plan, valid_case())))

    def test_bad_length(self) -> None:
        plan = valid_plan()
        plan["files"][0]["length"] = {"min": 9000, "max": 8000}
        self.assertTrue(any("length" in e for e in validate_plan(plan, valid_case())))


    def test_old_entry_with_writer_and_no_section_passes(self) -> None:
        plan = valid_plan()
        for entry, writer in zip(plan["files"], ("nsfc-justification-writer", "nsfc-research-foundation-writer")):
            del entry["section"]
            entry["writer"] = writer
        self.assertEqual(validate_plan(plan, valid_case()), [])

    def test_entry_without_section_or_writer_passes(self) -> None:
        plan = valid_plan()
        del plan["files"][0]["section"]
        self.assertEqual(validate_plan(plan, valid_case()), [])

    def test_unknown_section_name(self) -> None:
        plan = valid_plan()
        plan["files"][0]["section"] = "不存在的章"
        errors = validate_plan(plan, valid_case())
        self.assertTrue(any("未知章节" in e or "不是已知章节" in e for e in errors), errors)
        self.assertTrue(any("不存在的章" in e for e in errors), errors)

    def test_missing_writer_no_longer_reported(self) -> None:
        plan = valid_plan()
        del plan["files"][0]["section"]
        self.assertFalse(any("writer" in e for e in validate_plan(plan, valid_case())))


class ValidateCliTest(unittest.TestCase):
    def _run(self, root: Path) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(SCRIPTS / "case.py"), "validate", "--project-root", str(root)],
                              env=env, capture_output=True, text=True, timeout=60)

    def test_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            (root / "references").mkdir(parents=True)
            (root / "main.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
            (root / "references" / "refs.bib").write_text("@article{wu2021value,\n title={X},\n}\n", encoding="utf-8")
            write_yaml(root / "proposal" / "scientific_case.yaml", valid_case())
            write_yaml(root / "proposal" / "evidence_map.yaml", valid_evidence())
            write_yaml(root / "proposal" / "section_plan.yaml", valid_plan())
            ok = self._run(root)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            broken = copy.deepcopy(valid_case())
            broken["questions"][0]["text"] = "没有问号"
            write_yaml(root / "proposal" / "scientific_case.yaml", broken)
            bad = self._run(root)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("[scientific_case]", bad.stdout)

    def test_ledger_is_used_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            (root / "references").mkdir(parents=True)
            (root / "main.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
            (root / "references" / "refs.bib").write_text("@article{wu2021value,\n title={X},\n}\n", encoding="utf-8")
            write_yaml(root / "proposal" / "scientific_case.yaml", valid_case())
            write_yaml(root / "proposal" / "evidence_map.yaml", valid_evidence())
            write_yaml(root / "proposal" / "section_plan.yaml", valid_plan())
            ledger = root / "proposal" / "citation_ledger.jsonl"
            ledger.write_text(json.dumps({"event": "register_user", "bibkey": "wu2021value", "source": "user", "abstract": None}) + "\n",
                              encoding="utf-8")
            bad = self._run(root)
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
            self.assertIn("wu2021value", bad.stdout)
            ledger.write_text(json.dumps({"event": "add", "bibkey": "wu2021value", "source": "crossref", "abstract": ABSTRACT}) + "\n",
                              encoding="utf-8")
            ok = self._run(root)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)


if __name__ == "__main__":
    unittest.main()
