"""样本量与最小可检测效应。"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

POWER = Path(__file__).resolve().parents[2] / "skills/nsfc-proposal/scripts/power.py"


def run(*args):
    return subprocess.run([sys.executable, str(POWER), *map(str, args)], capture_output=True, text=True)


def js(*args):
    res = run(*args, "--json")
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


class PowerTests(unittest.TestCase):
    def test_props_plain(self) -> None:
        self.assertEqual(js("props", "--p0", 0.6, "--p1", 0.7)["n_per_group"], 356)

    def test_props_cluster(self) -> None:
        r = js("props", "--p0", 0.6, "--p1", 0.7, "--cluster-size", 40, "--icc", 0.1)
        self.assertAlmostEqual(r["design_effect"], 4.9)
        self.assertGreaterEqual(r["n_per_group"], 356 * 4.9 - 5)
        self.assertEqual(r["clusters_per_group"], -(-r["n_per_group"] // 40))

    def test_props_r2_reduces_n(self) -> None:
        r = js("props", "--p0", 0.6, "--p1", 0.7, "--r", 0.3)
        self.assertLess(r["n_per_group"], 356)

    def test_props_mde(self) -> None:
        r = js("props-mde", "--p0", 0.6, "--clusters", 8, "--cluster-size", 40, "--icc", 0.1)
        self.assertGreater(r["p1"], 0.6)
        self.assertLessEqual(r["clusters_needed"], 8)
        bigger = js("props-mde", "--p0", 0.6, "--clusters", 20, "--cluster-size", 40, "--icc", 0.1)
        self.assertLess(bigger["p1"], r["p1"])
        # one step below must need more than K clusters
        below = js("props", "--p0", 0.6, "--p1", round(r["p1"] - 0.001, 3), "--cluster-size", 40, "--icc", 0.1)
        self.assertGreater(below["clusters_per_group"], 8)

    def test_means(self) -> None:
        self.assertEqual(js("means", "--d", 0.5)["n_per_group"], 64)

    def test_means_cluster_and_ratio(self) -> None:
        r = js("means", "--d", 0.5, "--cluster-size", 40, "--icc", 0.1)
        self.assertAlmostEqual(r["design_effect"], 4.9)
        self.assertEqual(r["n_per_group"], 314)
        self.assertEqual(r["clusters_per_group"], 8)
        r2 = js("means", "--d", 0.5, "--ratio", 2)
        self.assertGreater(r2["n_total"], 128)

    def test_means_mde(self) -> None:
        self.assertAlmostEqual(js("means-mde", "--n1", 30, "--n2", 30)["d"], 0.74, places=2)

    def test_text_output_chinese(self) -> None:
        res = run("means", "--d", 0.5)
        self.assertEqual(res.returncode, 0)
        self.assertIn("每组", res.stdout)
        self.assertIn("公式", res.stdout)

    def test_out_of_range_exit_2(self) -> None:
        for args in (("props", "--p0", 1.2, "--p1", 0.5), ("props", "--p0", 0.5, "--p1", 0.5),
                     ("props", "--p0", 0.5, "--p1", 0.6, "--alpha", 0),
                     ("props", "--p0", 0.5, "--p1", 0.6, "--cluster-size", 40),
                     ("props", "--p0", 0.5, "--p1", 0.6, "--icc", 1.5, "--cluster-size", 4),
                     ("means", "--d", 0), ("means-mde", "--n1", 1, "--n2", 30),
                     ("props-mde", "--p0", 0.5, "--clusters", 0, "--cluster-size", 4, "--icc", 0.1)):
            self.assertEqual(run(*args).returncode, 2, args)


if __name__ == "__main__":
    unittest.main()
