"""coach 提示词：可以新增已核验的引用，可以新增配置允许的标题。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "nsfc-justification-writer" / "scripts"))

from core.writing_coach import _copyable_prompt  # noqa: E402

STAGES = ("skeleton", "draft", "revise", "polish", "final", "auto")


class CoachPromptTest(unittest.TestCase):
    def test_no_stage_forbids_new_citations(self):
        for stage in STAGES:
            text = _copyable_prompt(stage=stage, style_preamble="")
            self.assertNotIn("不新增引用", text, stage)
            self.assertNotIn("不修改任何标题层级", text, stage)

    def test_new_citations_must_be_verified(self):
        text = _copyable_prompt(stage="draft", style_preamble="")
        self.assertIn("可以新增引用", text)
        self.assertIn(".bib", text)
        self.assertIn("引用台账", text)

    def test_headings_follow_config(self):
        text = _copyable_prompt(stage="draft", style_preamble="")
        self.assertIn("allowed_new_heading_commands", text)


if __name__ == "__main__":
    unittest.main()
