from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from case_render import info_form, render_case_md  # noqa: E402
from proposal_common import ProposalError, read_yaml, write_yaml  # noqa: E402
from test_np_validate import valid_case, valid_evidence, valid_plan  # noqa: E402


class RenderCaseTest(unittest.TestCase):
    def test_confirm_view_shows_key_items(self) -> None:
        md = render_case_md(valid_case(), valid_evidence(), valid_plan())
        self.assertIn("# 科学论证（第 1 版，状态：草稿）", md)
        self.assertIn("瘤周纹理是否提供独立于瘤内的浸润信息？", md)
        self.assertIn("否定条件：外部队列中增量无统计学意义", md)
        self.assertIn("判定指标：AUC 差", md)
        self.assertIn("**多模态**", md)
        self.assertIn("AI 拟定，待确认", md)
        self.assertIn("样本与目标人群的差异：手术病例偏向高风险结节", md)
        self.assertIn("| extraTex/1.1.立项依据.tex |", md)
        self.assertIn("切入点", md)  # must_include 中的字段名换成中文
        self.assertIn("单篇核实 1", md)


class InfoFormTest(unittest.TestCase):
    def test_justification_form_matches_writer_fields(self) -> None:
        form = info_form(valid_case(), valid_plan(), "nsfc-justification-writer")
        for heading in ("1. **研究对象/应用场景**", "3. **关键科学问题（疑问句，非研究目标）**",
                        "4. **核心科学假设（陈述句，预测性结果，不写验证方式）**", "5. **本项目切入点（差异化切口）**",
                        "8. **主流路线与代表工作（引用先核验）**"):
            self.assertIn(heading, form)
        self.assertIn("8000–10000", form)
        self.assertIn("技术路线", form)  # 本章不写
        self.assertNotIn("Q1", form)

    def test_content_form_lists_subgoal_triplets(self) -> None:
        form = info_form(valid_case(), valid_plan(), "nsfc-research-content-writer")
        self.assertIn("4. **子目标（3–4 个，强制可检验）**", form)
        self.assertIn("对照/基线：病灶大小+实性成分比例模型", form)
        self.assertIn("需控制的混杂：病灶大小", form)
        self.assertNotIn("T1", form)

    def test_content_form_with_unresolved_dependencies_and_constraints(self) -> None:
        case = valid_case()
        case["tasks"][0]["depends_on"] = ["T9"]  # Unresolved dependency
        form = info_form(case, valid_plan(), "nsfc-research-content-writer")
        self.assertNotIn("T9", form)  # Unresolved ID should not appear
        self.assertIn("数据来源与验证：独立外部队列", form)  # Updated label
        self.assertNotIn("见第 7 项", form)  # Item 10 should show constraints, not reference

    def test_content_form_duration_follows_project_type(self) -> None:
        case = valid_case()
        case["project"]["type"] = "面上项目"
        form = info_form(case, valid_plan(), "nsfc-research-content-writer")
        self.assertIn("10. **研究期限与分年硬约束**：研究期限 4 年（项目类型：面上项目）；按 4 年分年度写，不跨年", form)
        self.assertNotIn("三年", form)
        self.assertNotIn("项目类型未写明", form)
        young = info_form(valid_case(), valid_plan(), "nsfc-research-content-writer")  # 青年科学基金
        self.assertIn("研究期限 3 年", young)
        self.assertNotIn("项目类型未写明", young)

    def test_content_form_duration_defaults_when_type_missing(self) -> None:
        case = valid_case()
        case["project"]["type"] = ""
        form = info_form(case, valid_plan(), "nsfc-research-content-writer")
        self.assertIn("研究期限 3 年", form)
        self.assertIn("按 3 年分年度写", form)
        self.assertIn("项目类型未写明，按 3 年；请在 assumptions.md 记一条 AI 拟定项", form)

    def test_foundation_form_marks_missing_items_as_placeholders(self) -> None:
        form = info_form(valid_case(), valid_plan(), "nsfc-research-foundation-writer")
        self.assertIn("## 4. 风险清单", form)
        self.assertIn("【待补充：预实验结果】", form)

    def test_unknown_writer(self) -> None:
        with self.assertRaises(ProposalError):
            info_form(valid_case(), valid_plan(), "nsfc-unknown")


class StateCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        (self.root / "extraTex").mkdir(parents=True)
        (self.root / "main.tex").write_text("", encoding="utf-8")
        write_yaml(self.root / "proposal" / "scientific_case.yaml", valid_case())
        write_yaml(self.root / "proposal" / "evidence_map.yaml", valid_evidence())
        write_yaml(self.root / "proposal" / "section_plan.yaml", valid_plan())
        (self.root / "proposal" / "assumptions.md").write_text("# 假设与待核实清单\n\n## 确认点状态\n\n## AI 拟定项\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(SCRIPTS / "case.py"), *args, "--project-root", str(self.root)],
                              env=env, capture_output=True, text=True, timeout=60)

    def test_render_writes_markdown(self) -> None:
        self.assertEqual(self._run("render").returncode, 0)
        self.assertTrue((self.root / "proposal" / "scientific_case.md").is_file())

    def test_bump_increments_version_and_resets_status(self) -> None:
        self._run("status", "--set", "confirmed")
        proc = self._run("bump")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        case = read_yaml(self.root / "proposal" / "scientific_case.yaml")
        self.assertEqual((case["version"], case["status"]), (2, "draft"))
        self.assertIn("第 2 版", (self.root / "proposal" / "scientific_case.md").read_text(encoding="utf-8"))

    def test_status_records_confirmation(self) -> None:
        proc = self._run("status", "--set", "bypassed")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(read_yaml(self.root / "proposal" / "scientific_case.yaml")["status"], "bypassed")
        text = (self.root / "proposal" / "assumptions.md").read_text(encoding="utf-8")
        self.assertIn("第 1 版：未确认（先继续）", text)

    def test_mark_written(self) -> None:
        self.assertEqual(self._run("mark-written", "--file", "extraTex/1.1.立项依据.tex").returncode, 0)
        files = read_yaml(self.root / "proposal" / "section_plan.yaml")["files"]
        self.assertEqual(files[0]["written_with_case_version"], 1)
        self.assertEqual(self._run("mark-written", "--file", "extraTex/9.9.不存在.tex").returncode, 2)

    def test_to_info_form_writes_file(self) -> None:
        out = Path(self.tmp.name) / "form.md"
        proc = self._run("to-info-form", "--writer", "nsfc-justification-writer", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("NSFC 写作信息表", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
