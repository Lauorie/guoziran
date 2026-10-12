"""文献池阅读表、论断选文、按论断汇总证据。不联网。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
LITERATURE = SCRIPTS / "literature.py"

LONG = "This abstract is long enough to be kept in the ledger as a verified abstract for the evidence view."


def rec(rid, title, year=2020, doi=None, venue="Radiology", queries=("q one",), status="present", abstract="x" * 100,
        relevance="perfect", snippet=None):
    prov = {"host_tool": "wispaper", "host_relevance": relevance}
    if snippet:
        prov["host_abstract_snippet"] = snippet
    return {"record_id": rid, "title": title, "year": year, "identifiers": {"doi": doi}, "venue": venue,
            "abstract": abstract if status == "present" else None, "abstract_status": status,
            "query_matches": list(queries), "provenance": prov}


def run(*args):
    return subprocess.run([sys.executable, str(LITERATURE), *map(str, args)], capture_output=True, text=True)


class ViewsBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.task = Path(self._tmp.name) / "T"
        self.proj = Path(self._tmp.name) / "P"
        self.out = self.task / "nsfc-proposal/output"
        self.proj.mkdir(parents=True)

    def pool(self, name, rows):
        d = self.out / "literature" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "candidates.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return d


class DigestTests(ViewsBase):
    def test_groups_and_abstract_states(self) -> None:
        d = self.pool("p1", [
            rec("r1", "Alpha radiomics of nodules", doi="10.1/a"),
            rec("r2", "Beta study " + "t" * 200, queries=("q one", "q two"), status="missing", snippet="… part …"),
            rec("r3", "Gamma", queries=("q two",), status="missing"),
            rec("r4", "Delta", queries=(), status="missing"),
        ])
        res = run("digest", "--task-root", self.task, "--name", "p1")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(str(d / "digest.md"), res.stdout)
        text = (d / "digest.md").read_text(encoding="utf-8")
        self.assertIn("p1", text)
        self.assertIn("4 篇", text)
        self.assertIn("q one", text)
        self.assertIn("（无检索式）", text)
        self.assertIn("r1 | 2020 | Alpha radiomics of nodules | Radiology | 10.1/a | perfect | 摘要：完整", text)
        self.assertIn("摘要：片段", text)
        self.assertIn("r3 | 2020 | Gamma | Radiology |  | perfect | 摘要：无", text)
        long_line = [ln for ln in text.splitlines() if ln.startswith("r2 |")][0]
        self.assertNotIn("t" * 170, long_line)
        # r2 belongs to the first query only
        self.assertEqual(text.count("r2 |"), 1)

    def test_missing_pool_is_usage_error(self) -> None:
        res = run("digest", "--task-root", self.task, "--name", "nope")
        self.assertEqual(res.returncode, 2)

    def test_bad_name_rejected(self) -> None:
        self.assertEqual(run("digest", "--task-root", self.task, "--name", "../x").returncode, 2)


class SelectTests(ViewsBase):
    def setUp(self) -> None:
        super().setUp()
        self.pool("p1", [rec("r1", "Peritumoral radiomics predicts invasiveness"),
                         rec("r2", "Deep learning for nodule segmentation"),
                         rec("r3", "Deep learning for nodule detection")])
        self.pool("p2", [rec("r1", "Peritumoral radiomics predicts invasiveness"), rec("r4", "Texture   analysis of GGN")])
        self.map = Path(self._tmp.name) / "map.json"

    def write_map(self, data):
        self.map.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_unique_prefix_and_id(self) -> None:
        self.write_map({"C1": ["peritumoral  RADIOMICS", "r2"], "C2": ["texture analysis", "r2"]})
        res = run("select", "--task-root", self.task, "--map", self.map)
        self.assertEqual(res.returncode, 0, res.stderr)
        rows = [json.loads(x) for x in (self.out / "selected.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["record_id"] for r in rows], ["r1", "r2", "r4"])
        cm = json.loads((self.out / "selected_claim_map.json").read_text(encoding="utf-8"))
        self.assertEqual(cm, {"C1": ["r1", "r2"], "C2": ["r4", "r2"]})

    def test_ambiguous_title_writes_nothing(self) -> None:
        self.write_map({"C1": ["Deep learning for nodule", "r1"]})
        res = run("select", "--task-root", self.task, "--map", self.map)
        self.assertEqual(res.returncode, 1)
        self.assertIn("Deep learning for nodule", res.stderr)
        self.assertIn("r2", res.stderr)
        self.assertFalse((self.out / "selected.jsonl").exists())
        self.assertFalse((self.out / "selected_claim_map.json").exists())

    def test_unmatched_lists_nearest_and_writes_nothing(self) -> None:
        self.write_map({"C1": ["Peritumoral radiomics predicts invasiveness", "Quantum gravity of lungs"]})
        res = run("select", "--task-root", self.task, "--map", self.map)
        self.assertEqual(res.returncode, 1)
        self.assertIn("Quantum gravity of lungs", res.stderr)
        self.assertIn("Deep learning for nodule", res.stderr)
        self.assertFalse((self.out / "selected.jsonl").exists())

    def test_same_title_without_doi_counts_as_one_paper(self) -> None:
        self.pool("p3", [rec("w1", "Shared Title Of One Paper", status="missing")])
        self.pool("p4", [rec("w2", "shared  title of one PAPER", status="present", abstract="full " * 30)])
        self.write_map({"C1": ["shared title of one"]})
        res = run("select", "--task-root", self.task, "--map", self.map)
        self.assertEqual(res.returncode, 0, res.stderr)
        rows = [json.loads(x) for x in (self.out / "selected.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["record_id"] for r in rows], ["w2"])
        self.assertEqual(rows[0]["abstract_status"], "present")
        self.assertEqual(json.loads((self.out / "selected_claim_map.json").read_text(encoding="utf-8")), {"C1": ["w2"]})

    def test_same_title_both_without_abstract_takes_first(self) -> None:
        self.pool("p3", [rec("w1", "Twin paper", status="missing")])
        self.pool("p4", [rec("w2", "Twin paper", status="missing")])
        self.write_map({"C1": ["twin paper"]})
        self.assertEqual(run("select", "--task-root", self.task, "--map", self.map).returncode, 0)
        rows = [json.loads(x) for x in (self.out / "selected.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["record_id"] for r in rows], ["w1"])

    def test_cross_pool_copy_with_full_abstract_wins(self) -> None:
        self.pool("p3", [rec("r9", "Snippet copy", status="missing", snippet="… part …")])
        self.pool("p4", [rec("r9", "Snippet copy", status="present", abstract="full abstract " * 10)])
        self.write_map({"C1": ["r9"], "C2": ["snippet copy"]})
        res = run("select", "--task-root", self.task, "--map", self.map)
        self.assertEqual(res.returncode, 0, res.stderr)
        rows = [json.loads(x) for x in (self.out / "selected.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["abstract_status"], "present")
        self.assertIn("full abstract", rows[0]["abstract"])

    def test_same_id_with_different_title_strings_is_one_paper(self) -> None:
        self.pool("p3", [rec("doi:10.1/t", "Twin paper.", status="missing")])
        self.pool("p4", [rec("doi:10.1/t", "Twin paper", status="present", abstract="full abstract " * 10)])
        self.write_map({"C1": ["doi:10.1/t"]})
        res = run("select", "--task-root", self.task, "--map", self.map)
        self.assertEqual(res.returncode, 0, res.stderr)
        rows = [json.loads(x) for x in (self.out / "selected.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["abstract_status"], "present")

    def test_bad_map_is_usage_error(self) -> None:
        self.write_map(["not", "a", "dict"])
        self.assertEqual(run("select", "--task-root", self.task, "--map", self.map).returncode, 2)
        self.assertEqual(run("select", "--task-root", self.task, "--map", self.map.with_name("none.json")).returncode, 2)


class EvidenceTests(ViewsBase):
    def setUp(self) -> None:
        super().setUp()
        self.out.mkdir(parents=True)
        rows = [rec("r1", "Added paper", year=2021), rec("r2", "Existing paper", year=2019),
                rec("r3", "Unresolved paper", year=2018), rec("r4", "Existing no abstract", year=2017)]
        (self.out / "selected.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        (self.out / "selected_claim_map.json").write_text(
            json.dumps({"C1": ["r1", "r2", "r3"], "C2": ["r4", "r1"]}), encoding="utf-8")
        outcomes = [
            {"record_id": "r1", "title": "Added paper", "status": "added", "bibkey": "a2021x", "doi": "10.1/a"},
            {"record_id": "r2", "title": "Existing paper", "status": "exists", "bibkey": "e2019y"},
            {"record_id": "r3", "title": "Unresolved paper", "status": "unresolved", "reason": "CrossRef 无标题匹配的条目"},
            {"record_id": "r4", "title": "Existing no abstract", "status": "exists", "bibkey": "n2017z"},
        ]
        (self.out / "bib_resolve.json").write_text(json.dumps({"outcomes": outcomes}), encoding="utf-8")
        ledger = self.proj / "proposal/citation_ledger.jsonl"
        ledger.parent.mkdir(parents=True)
        ev = lambda k, a: {"event": "add", "bibkey": k, "abstract": a}  # noqa: E731
        ledger.write_text("\n".join(json.dumps(x) for x in [
            ev("a2021x", LONG), ev("e2019y", "old"), ev("e2019y", LONG + " v2"), ev("n2017z", None)]) + "\n", encoding="utf-8")

    def test_evidence_by_claim(self) -> None:
        res = run("evidence", "--task-root", self.task, "--project-root", self.proj)
        self.assertEqual(res.returncode, 0, res.stderr)
        path = self.out / "evidence_by_claim.md"
        self.assertIn(str(path), res.stdout)
        text = path.read_text(encoding="utf-8")
        c1, c2 = text.split("C2", 1)[0], text.split("C2", 1)[1]
        self.assertIn("可引用 2 篇", c1)
        self.assertIn("a2021x", c1)
        self.assertIn(LONG, c1)
        self.assertIn(LONG + " v2", c1)
        self.assertNotIn("\nold", c1)
        self.assertIn("未入库：unresolved", c1)
        self.assertIn("CrossRef 无标题匹配的条目", c1)
        self.assertIn("可引用 2 篇", c2)
        self.assertIn("（无摘要）", c2)

    def test_dropped_entry_counts_as_not_in_library(self) -> None:
        ledger = self.proj / "proposal/citation_ledger.jsonl"
        with ledger.open("a", encoding="utf-8") as h:
            h.write(json.dumps({"event": "drop", "bibkey": "a2021x", "reason": "换成正式发表版"}) + "\n")
        run("evidence", "--task-root", self.task, "--project-root", self.proj)
        text = (self.out / "evidence_by_claim.md").read_text(encoding="utf-8")
        self.assertIn("可引用 1 篇", text.split("C2", 1)[0])
        self.assertIn("已作废：换成正式发表版", text)
        self.assertNotIn("未入库：added", text)

    def test_record_without_outcome_is_unchecked(self) -> None:
        (self.out / "selected_claim_map.json").write_text(json.dumps({"C1": ["r1", "r5"]}), encoding="utf-8")
        res = run("evidence", "--task-root", self.task, "--project-root", self.proj)
        self.assertEqual(res.returncode, 0, res.stderr)
        text = (self.out / "evidence_by_claim.md").read_text(encoding="utf-8")
        self.assertIn("未核对（bib_resolve 结果中没有这条记录）", text)
        self.assertNotIn("未处理", text)
        self.assertIn("可引用 1 篇", text)

    def test_missing_ledger_exit_2(self) -> None:
        (self.proj / "proposal/citation_ledger.jsonl").unlink()
        res = run("evidence", "--task-root", self.task, "--project-root", self.proj)
        self.assertEqual(res.returncode, 2)
        self.assertIn("引用台账", res.stderr)
        self.assertFalse((self.out / "evidence_by_claim.md").exists())

    def test_missing_inputs_exit_2(self) -> None:
        (self.out / "bib_resolve.json").unlink()
        self.assertEqual(run("evidence", "--task-root", self.task, "--project-root", self.proj).returncode, 2)


if __name__ == "__main__":
    unittest.main()
