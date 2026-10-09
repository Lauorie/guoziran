# tests/nsfc-proposal/test_np_skill_docs.py
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "nsfc-proposal"
SKILLS = ROOT / "skills"
TEXT = (SKILL / "SKILL.md").read_text(encoding="utf-8") if (SKILL / "SKILL.md").exists() else ""
ORDER = ["## 目标", "## 流程", "### 输入", "### 执行步骤", "### 输出", "### 输出管理", "### 校验", "### 失败与恢复", "## 约束"]


def frontmatter() -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", TEXT, re.S)
    return yaml.safe_load(match.group(1)) if match else {}


class SkillDocTest(unittest.TestCase):
    def test_frontmatter(self) -> None:
        meta = frontmatter()
        self.assertEqual(meta.get("name"), "nsfc-proposal")
        self.assertEqual((meta.get("metadata") or {}).get("author"), "Lauorie")
        description = meta.get("description") or ""
        self.assertTrue(description)
        for leak in ("proposal/", ".yaml", "case.py", "--"):
            self.assertNotIn(leak, description)

    def test_section_order_and_no_control_section(self) -> None:
        headings = [line for line in TEXT.splitlines() if line.startswith(("## ", "### "))]
        positions = [headings.index(h) for h in ORDER]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("## 控制", TEXT)

    def test_common_constraints_block_is_verbatim(self) -> None:
        template = (ROOT / "docs/templates/skill-common-constraints.md").read_text(encoding="utf-8").splitlines()
        block = "\n".join(template[1:]).strip()
        self.assertIn(block, TEXT)

    def test_referenced_files_exist(self) -> None:
        local = set(re.findall(r"(?<![A-Za-z])S/((?:scripts|references|assets)/[\w.\-]+)", TEXT))
        local |= set(re.findall(r"`(references/[\w.\-]+\.md)`", TEXT))
        shared = set(re.findall(r"(?<![A-Za-z])SK/([\w\-]+/(?:scripts/[\w.\-]+|SKILL\.md))", TEXT))
        self.assertTrue(local and shared)
        for rel in sorted(local):
            self.assertTrue((SKILL / rel).is_file(), rel)
        for rel in sorted(shared):
            self.assertTrue((SKILLS / rel).is_file(), rel)

    def test_version_only_in_config(self) -> None:
        config = yaml.safe_load((SKILL / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config["skill_info"]["version"], "0.1.0")
        self.assertNotIn("0.1.0", TEXT)
        self.assertNotIn("0.1.0", (SKILL / "README.md").read_text(encoding="utf-8"))

    def test_changelog(self) -> None:
        changelog = (SKILL / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [0.1.0] - 2026-10-09", changelog)
        self.assertIn("初始化技能，实现核心功能", changelog)
        self.assertIn("本分支未写 BAC 记录，经负责人同意。", changelog)


if __name__ == "__main__":
    unittest.main()
