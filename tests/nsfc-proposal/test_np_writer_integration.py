from __future__ import annotations

import unittest
from pathlib import Path

import yaml

SKILLS = Path(__file__).resolve().parents[2] / "skills"
VERSIONS = {
    "nsfc-justification-writer": "1.4.0",
    "nsfc-research-content-writer": "1.1.0",
    "nsfc-research-foundation-writer": "0.2.0",
    "nsfc-abstract": "2.1.3",
    "research-literature-search": "1.1.0",
}


def read(rel: str) -> str:
    return (SKILLS / rel).read_text(encoding="utf-8")


class IntegrationDocsTest(unittest.TestCase):
    def test_versions_and_changelogs(self) -> None:
        for skill, version in VERSIONS.items():
            config = yaml.safe_load(read(f"{skill}/config.yaml"))
            self.assertEqual(str(config["skill_info"]["version"]), version, skill)
            changelog = read(f"{skill}/CHANGELOG.md")
            self.assertIn(f"## [{version}] - 2026-10-09", changelog, skill)
            self.assertIn("本分支未写 BAC 记录，经负责人同意。", changelog, skill)

    def test_writers_describe_proposal_mode(self) -> None:
        for skill in ("nsfc-justification-writer", "nsfc-research-content-writer", "nsfc-research-foundation-writer", "nsfc-abstract"):
            text = read(f"{skill}/SKILL.md")
            self.assertIn("proposal/", text, skill)
            self.assertIn("没有 `proposal/` 时", text, skill)

    def test_justification_tier2_checks(self) -> None:
        text = read("nsfc-justification-writer/references/tier2_semantic_review.md")
        self.assertIn("## 与 nsfc-proposal 协作时的追加检查", text)
        self.assertIn("evidence_map.yaml", text)
        self.assertIn("must_exclude", text)
        self.assertIn("--task-root", read("nsfc-justification-writer/SKILL.md"))
        self.assertIn("--task-root", read("nsfc-justification-writer/README.md"))

    def test_foundation_requires_visible_placeholders(self) -> None:
        self.assertIn("【待补充：", read("nsfc-research-foundation-writer/SKILL.md"))

    def test_content_readme_no_longer_asks_for_subgoal_ids_in_body(self) -> None:
        self.assertNotIn("2.2/2.3 标注回溯到对应 Sx", read("nsfc-research-content-writer/README.md"))

    def test_search_documents_host_results(self) -> None:
        for rel in ("research-literature-search/SKILL.md", "research-literature-search/README.md"):
            self.assertIn("--host-results", read(rel), rel)
            self.assertIn("rls.host_results.v1", read(rel), rel)


if __name__ == "__main__":
    unittest.main()
