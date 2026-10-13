from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/nsfc-justification-writer/scripts"))

from core.versioning import list_runs  # noqa: E402


class ListRunsTest(unittest.TestCase):
    def test_skips_workspace_and_cache_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nsfc-justification-writer"
            for name in ("input", "output", "log", "cache"):
                (root / name).mkdir(parents=True)
            (root / "auto_20261009093512" / "backup").mkdir(parents=True)
            (root / "my-custom-run" / "logs").mkdir(parents=True)
            (root / "init_20261009093000").mkdir(parents=True)
            (root / "random_folder").mkdir(parents=True)
            ids = sorted(r.run_id for r in list_runs(runs_root=root))
            self.assertEqual(ids, ["auto_20261009093512", "init_20261009093000", "my-custom-run"])

    def test_missing_root_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list_runs(runs_root=Path(tmp) / "absent"), [])


if __name__ == "__main__":
    unittest.main()
