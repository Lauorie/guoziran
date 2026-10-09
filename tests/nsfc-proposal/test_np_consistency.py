# tests/nsfc-proposal/test_np_consistency.py
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
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consistency_check import check_project  # noqa: E402
from proposal_common import write_yaml  # noqa: E402
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


def build(base: Path, *, body_11: str = BODY_11, terms: list | None = None) -> Path:
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


if __name__ == "__main__":
    unittest.main()
