from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

from case import init_proposal  # noqa: E402
from proposal_common import ProposalError, proposal_paths, read_yaml  # noqa: E402

COMPILED = ["1.1.立项依据", "2.1.研究内容", "2.2.特色与创新", "2.3.年度研究计划", "3.1.研究基础", "3.2.工作条件"]


def make_project(base: Path) -> Path:
    root = base / "proj"
    extra = root / "extraTex"
    extra.mkdir(parents=True)
    for name in COMPILED + ["4.5.生成式人工智能"]:
        (extra / f"{name}.tex").write_text("\\justifying\n\\NSFCBodyText\n", encoding="utf-8")
    (root / "references").mkdir()
    (root / "references" / "reference.tex").write_text("\\bibliography{references/myexample}\n", encoding="utf-8")
    inputs = "".join(f"\\input{{extraTex/{name}.tex}}\n" for name in COMPILED)
    (root / "main.tex").write_text(inputs + "\\input{references/reference.tex}\n", encoding="utf-8")
    return root


class InitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_project(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_creates_all_files_with_project_fields(self) -> None:
        result = init_proposal(self.root, title="肺磨玻璃结节浸润性预测", project_type="青年科学基金")
        paths = proposal_paths(self.root)
        self.assertEqual(set(result.created), {paths.case, paths.evidence, paths.plan, paths.assumptions, paths.leads, paths.ledger})
        case = read_yaml(paths.case)
        self.assertEqual(case["project"]["title"], "肺磨玻璃结节浸润性预测")
        self.assertEqual(case["version"], 1)
        self.assertEqual(case["status"], "draft")
        self.assertIn("研究基础", case["project"]["sections"])
        leads = paths.leads.read_text(encoding="utf-8").splitlines()
        self.assertEqual([line for line in leads if line.startswith("## ")], ["## 检索式", "## 官方文件", "## 未核实线索"])

    def test_plan_uses_length_budgets_and_writers(self) -> None:
        init_proposal(self.root, title="T", project_type="青年科学基金")
        files = {f["file"]: f for f in read_yaml(proposal_paths(self.root).plan)["files"]}
        self.assertEqual(files["extraTex/1.1.立项依据.tex"]["length"], {"min": 4500, "max": 10000, "unit": "cjk_chars"})
        self.assertEqual(files["extraTex/2.1.研究内容.tex"]["length"], {"min": 7000, "max": 15000, "unit": "cjk_chars"})
        self.assertEqual(files["extraTex/1.1.立项依据.tex"]["writer"], "nsfc-justification-writer")
        self.assertIn("技术路线", files["extraTex/1.1.立项依据.tex"]["must_exclude"])
        self.assertIsNone(files["extraTex/3.2.工作条件.tex"]["length"])
        self.assertEqual(files["NSFC-ABSTRACTS.md"]["writer"], "nsfc-abstract")
        self.assertIsNone(files["extraTex/1.1.立项依据.tex"]["written_with_case_version"])

    def test_uncompiled_ai_declaration_falls_back_to_proposal_dir(self) -> None:
        result = init_proposal(self.root, title="T", project_type="青年科学基金")
        files = [f["file"] for f in read_yaml(proposal_paths(self.root).plan)["files"]]
        self.assertIn("proposal/ai_declaration.md", files)
        self.assertNotIn("extraTex/4.5.生成式人工智能.tex", files)
        self.assertTrue(any("4.5.生成式人工智能.tex" in w for w in result.warnings))
        self.assertIn("4.5.生成式人工智能.tex", proposal_paths(self.root).assumptions.read_text(encoding="utf-8"))

    def test_rerun_does_not_overwrite_or_duplicate_warnings(self) -> None:
        init_proposal(self.root, title="旧标题", project_type="青年科学基金")
        result = init_proposal(self.root, title="新标题", project_type="面上项目")
        paths = proposal_paths(self.root)
        self.assertEqual(result.created, [])
        self.assertEqual(read_yaml(paths.case)["project"]["title"], "旧标题")
        self.assertEqual(paths.assumptions.read_text(encoding="utf-8").count("4.5.生成式人工智能.tex"), 1)

    def test_section_subset(self) -> None:
        init_proposal(self.root, title="T", project_type="青年科学基金", sections=["立项依据", "摘要"])
        files = [f["file"] for f in read_yaml(proposal_paths(self.root).plan)["files"]]
        self.assertEqual(files, ["extraTex/1.1.立项依据.tex", "NSFC-ABSTRACTS.md"])

    def test_unknown_section_rejected(self) -> None:
        with self.assertRaises(ProposalError):
            init_proposal(self.root, title="T", project_type="青年科学基金", sections=["不存在的章"])

    def test_non_nsfc_project_rejected(self) -> None:
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        with self.assertRaises(ProposalError):
            init_proposal(empty, title="T", project_type="青年科学基金")


class InitCliTest(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(SCRIPTS / "case.py"), *args], env=env, capture_output=True, text=True, timeout=60)

    def test_cli_success_and_path_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            ok = self._run("init", "--project-root", str(root), "--title", "T", "--type", "青年科学基金")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("已创建", ok.stdout)
            bad = self._run("init", "--project-root", str(Path(tmp) / "absent"), "--title", "T", "--type", "青年科学基金")
            self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
