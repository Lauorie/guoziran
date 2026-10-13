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

    def test_props_mde_individual(self) -> None:
        r = js("props-mde", "--p0", 0.3, "--n", 200)
        self.assertAlmostEqual(r["p1"], 0.435, places=3)
        self.assertLessEqual(r["n_per_group"], 200)
        self.assertNotIn("clusters_needed", r)
        below = js("props", "--p0", 0.3, "--p1", 0.434)
        self.assertGreater(below["n_per_group"], 200)
        text = run("props-mde", "--p0", 0.3, "--n", 200).stdout
        self.assertIn("每组 200 人", text)
        self.assertIn("高", text)

    def test_props_mde_lower(self) -> None:
        r = js("props-mde", "--p0", 0.3, "--n", 200, "--lower")
        self.assertLess(r["p1"], 0.3)
        self.assertLess(r["difference_pp"], 0)
        self.assertLessEqual(js("props", "--p0", 0.3, "--p1", r["p1"])["n_per_group"], 200)
        closer = js("props", "--p0", 0.3, "--p1", round(r["p1"] + 0.001, 3))
        self.assertGreater(closer["n_per_group"], 200)
        self.assertIn("低", run("props-mde", "--p0", 0.3, "--n", 200, "--lower").stdout)
        cl = js("props-mde", "--p0", 0.6, "--clusters", 8, "--cluster-size", 40, "--icc", 0.1, "--lower")
        self.assertLess(cl["p1"], 0.6)
        self.assertLessEqual(cl["clusters_needed"], 8)

    def test_props_mde_needs_exactly_one_design(self) -> None:
        for args in (("props-mde", "--p0", 0.3),
                     ("props-mde", "--p0", 0.3, "--n", 200, "--clusters", 8, "--cluster-size", 40, "--icc", 0.1),
                     ("props-mde", "--p0", 0.3, "--n", 200, "--cluster-size", 40, "--icc", 0.1),
                     ("props-mde", "--p0", 0.3, "--clusters", 8),
                     ("props-mde", "--p0", 0.3, "--n", 1)):
            res = run(*args)
            self.assertEqual(res.returncode, 2, args)
            self.assertIn("✗", res.stderr)

    def test_means_small_sample_adds_one(self) -> None:
        for d, n in ((1.5, 9), (2.0, 6), (3.0, 4)):
            r = js("means", "--d", d)
            self.assertEqual(r["n_per_group"], n, d)
            self.assertEqual(r["n_group2"], n, d)
            self.assertEqual(r["small_sample_added"], 1)
        self.assertEqual(js("means", "--d", 0.5)["small_sample_added"], 0)
        self.assertIn("加 1 人", run("means", "--d", 2.0).stdout)

    def test_means_mde_cluster(self) -> None:
        plain = js("means-mde", "--n1", 320, "--n2", 320)["d"]
        r = js("means-mde", "--n1", 320, "--n2", 320, "--cluster-size", 40, "--icc", 0.1)
        self.assertAlmostEqual(r["design_effect"], 4.9)
        self.assertAlmostEqual(r["d"], 0.49, places=2)
        self.assertGreater(r["d"], plain)
        self.assertEqual(run("means-mde", "--n1", 30, "--n2", 30, "--cluster-size", 4).returncode, 2)

    def test_means_mde_small_n_caveat(self) -> None:
        self.assertIn("偏乐观", run("means-mde", "--n1", 8, "--n2", 8).stdout)
        self.assertNotIn("偏乐观", run("means-mde", "--n1", 30, "--n2", 30).stdout)
        self.assertTrue(js("means-mde", "--n1", 8, "--n2", 8)["small_sample_caveat"])

    def test_means_ratio_must_be_finite_and_cluster_both_groups(self) -> None:
        for bad in ("inf", "nan", "-1", "0"):
            self.assertEqual(run("means", "--d", 0.5, "--ratio", bad).returncode, 2, bad)
        r = js("means", "--d", 0.5, "--ratio", 2, "--cluster-size", 40, "--icc", 0.1)
        self.assertEqual(r["clusters_per_group"], -(-r["n_per_group"] // 40))
        self.assertEqual(r["clusters_group2"], -(-r["n_group2"] // 40))
        text = run("means", "--d", 0.5, "--ratio", 2, "--cluster-size", 40, "--icc", 0.1).stdout
        self.assertIn(f"第二组需 {r['clusters_group2']} 个群", text)

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
