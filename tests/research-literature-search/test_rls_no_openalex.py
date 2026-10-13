# tests/research-literature-search/test_rls_no_openalex.py
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "research-literature-search"
sys.path.insert(0, str(SKILL / "scripts"))

import search_runner  # noqa: E402
from candidate_schema import IDENTIFIER_KEYS  # noqa: E402

TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".txt"}


class NoOpenAlexTests(unittest.TestCase):
    def test_skill_files_never_mention_openalex(self) -> None:
        hits = [str(p.relative_to(ROOT)) for p in SKILL.rglob("*")
                if p.is_file() and p.suffix in TEXT_SUFFIXES and p.name != "CHANGELOG.md"
                and "__pycache__" not in p.parts and "openalex" in p.read_text(encoding="utf-8").lower()]
        self.assertEqual(hits, [])

    def test_defaults_have_no_openalex(self) -> None:
        self.assertNotIn("openalex", search_runner.DEFAULT_PROVIDER_ORDER)
        self.assertNotIn("openalex", search_runner.SUPPORTED_PROVIDERS)
        self.assertNotIn("openalex", search_runner._provider_registry())
        self.assertNotIn("openalex", IDENTIFIER_KEYS)
        self.assertFalse((SKILL / "scripts" / "providers" / "openalex.py").exists())


if __name__ == "__main__":
    unittest.main()
