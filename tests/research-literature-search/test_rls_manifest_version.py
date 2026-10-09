# tests/research-literature-search/test_rls_manifest_version.py
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/research-literature-search"
sys.path.insert(0, str(SKILL / "scripts"))

import manifest  # noqa: E402
import search_runner  # noqa: E402


def config_version() -> str:
    return str(yaml.safe_load((SKILL / "config.yaml").read_text(encoding="utf-8"))["skill_info"]["version"])


class ManifestVersionTest(unittest.TestCase):
    """manifest 与 Search Log 中的 search_skill_version 取自 config.yaml，不另写一份。"""

    def test_version_matches_config(self) -> None:
        self.assertEqual(manifest.SEARCH_SKILL_VERSION, config_version())
        self.assertEqual(search_runner.SEARCH_SKILL_VERSION, config_version())

    def test_missing_config_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                manifest.read_skill_version(Path(tmp) / "config.yaml")

    def test_missing_version_key_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            for text in ("skill_info:\n  name: research-literature-search\n", "- a\n", "skill_info:\n  version: ''\n"):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(RuntimeError, msg=text):
                    manifest.read_skill_version(path)

    def test_readme_does_not_repeat_the_version(self) -> None:
        readme = (SKILL / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("当前版本", readme)
        self.assertNotIn(config_version(), readme)


if __name__ == "__main__":
    unittest.main()
