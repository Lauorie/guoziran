from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-justification-writer/scripts"
sys.path.insert(0, str(SCRIPTS))

from core.change_guard import inspect_proposal  # noqa: E402


class ChangeGuardHeadingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.target = self.root / "extraTex" / "1.1.立项依据.tex"
        self.target.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _inspect(self, original: str, proposed: str, allowed: tuple[str, ...] = ()):
        return inspect_proposal(
            original=original,
            proposed=proposed,
            target_path=self.target,
            project_root=self.root,
            allowed_new_headings=allowed,
        )

    def test_new_subsubsection_allowed_when_configured(self) -> None:
        result = self._inspect("\\justifying\n", "\\justifying\n\\subsubsection{研究背景}\n正文。\n", ("subsubsection",))
        self.assertTrue(result.ok)
        self.assertEqual(result.structural_hits, [])

    def test_new_subsubsection_rejected_without_allowlist(self) -> None:
        result = self._inspect("\\justifying\n", "\\justifying\n\\subsubsection{研究背景}\n正文。\n")
        self.assertFalse(result.ok)
        self.assertEqual(result.structural_hits, ["\\subsubsection"])

    def test_removing_existing_heading_still_rejected(self) -> None:
        result = self._inspect("\\subsubsection{旧标题}\n旧正文。\n", "新正文。\n", ("subsubsection",))
        self.assertFalse(result.ok)
        self.assertIn("\\subsubsection", result.structural_hits)

    def test_renaming_existing_heading_rejected(self) -> None:
        result = self._inspect("\\subsubsection{旧标题}\n正文。\n", "\\subsubsection{新标题}\n正文。\n", ("subsubsection",))
        self.assertFalse(result.ok)

    def test_new_input_command_still_rejected(self) -> None:
        result = self._inspect("", "\\subsubsection{背景}\n\\input{extraTex/other}\n", ("subsubsection",))
        self.assertFalse(result.ok)
        self.assertEqual(result.structural_hits, ["\\input"])

    def test_allowlist_accepts_backslash_prefix(self) -> None:
        result = self._inspect("", "\\subsubsection{背景}\n", ("\\subsubsection",))
        self.assertTrue(result.ok)


class PreviewCliHeadingTest(unittest.TestCase):
    def test_preview_dry_run_accepts_new_heading_with_default_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            target = project / "extraTex" / "1.1.立项依据.tex"
            target.parent.mkdir(parents=True)
            target.write_text("\\justifying\n\\NSFCBodyText\n", encoding="utf-8")
            proposal = Path(tmp) / "proposal.tex"
            proposal.write_text("\\justifying\n\\NSFCBodyText\n\n\\subsubsection{研究背景}\n正文。\n", encoding="utf-8")
            env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
            env.pop("NSFC_JUSTIFICATION_WRITER_RUNS_DIR", None)
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "run.py"), "--no-user-override", "preview",
                 "--project-root", str(project), "--proposal-file", str(proposal),
                 "--target-file", "extraTex/1.1.立项依据.tex", "--dry-run"],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("未发现结构/配置命令变化", proc.stdout)


if __name__ == "__main__":
    unittest.main()
