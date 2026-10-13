# tests/nsfc-proposal/test_np_bib_record_fallback.py
"""bib_resolve：CrossRef 查不到时，按检索记录自带的字段写 .bib，不再挡掉这篇文献。不联网。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_np_bib_resolve as base  # noqa: E402

from bib_resolve import CROSSREF_WORKS, record_authors  # noqa: E402

EMPTY = base.FakeResponse(200, {"message": {"items": []}})
ABSTRACT = "We study how test-time sampling and majority voting change the accuracy of multi-step reasoning in language models."


def paper(**fields) -> dict:
    row = {"record_id": "r", "title": "Self-Consistency Improves Chain of Thought Reasoning in Language Models",
           "authors": ["Xuezhi Wang", "Jason Wei"], "venue": "International Conference on Learning Representations",
           "year": 2023, "source": "wispaper"}
    row.update(fields)
    return row


class RecordFallbackTest(unittest.TestCase):
    setUp = base.ResolveTest.setUp
    tearDown = base.ResolveTest.tearDown
    _records = base.ResolveTest._records
    _run = base.ResolveTest._run

    def entry(self, key: str) -> str:
        text = self.bib.read_text(encoding="utf-8")
        start = text.index("@", text.index("{" + key + ",") - 20)
        return text[start:text.index("\n}\n", start) + 2]

    def test_conference_record_is_written_from_record(self) -> None:
        summary = self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), paper())
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["source"], outcome["bibkey"]), ("added", "record", "wang2023self"))
        self.assertIn("CrossRef 无标题匹配的条目", "；".join(outcome["notes"]))
        entry = self.entry("wang2023self")
        self.assertIn("@inproceedings{wang2023self,", entry)
        self.assertIn("author = {Wang, Xuezhi and Wei, Jason}", entry)
        self.assertIn("booktitle = {International Conference on Learning Representations}", entry)
        self.assertIn("year = {2023}", entry)
        for field in ("volume", "number", "pages", "doi"):
            self.assertNotIn(f"{field} =", entry)

    def test_journal_venue_becomes_article(self) -> None:
        self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), paper(venue="Journal of Test Economics"))
        entry = self.entry("wang2023self")
        self.assertIn("@article{wang2023self,", entry)
        self.assertIn("journal = {Journal of Test Economics}", entry)

    def test_arxiv_record_becomes_preprint(self) -> None:
        record = paper(title="Breaking the Safety-Capability Tradeoff", authors=["Dongkyu Derek Cho", "Huan Song"], year=2025,
                       venue="arXiv (Cornell University)", url="https://arxiv.org/abs/2511.21050v2",
                       identifiers={"doi": "10.48550/arxiv.2511.21050"}, publication={"is_preprint": True})
        summary = self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), record)
        self.assertEqual(summary["outcomes"][0]["status"], "added")
        entry = self.entry("cho2025breaking")
        self.assertIn("@misc{cho2025breaking,", entry)
        self.assertIn("author = {Cho, Dongkyu Derek and Song, Huan}", entry)
        self.assertIn("howpublished = {arXiv preprint arXiv:2511.21050}", entry)
        self.assertIn("url = {https://arxiv.org/abs/2511.21050v2}", entry)
        self.assertIn("doi = {10.48550/arxiv.2511.21050}", entry)

    def test_network_failure_with_full_record_is_added(self) -> None:
        error = requests.ConnectionError("offline")
        session = base.FakeSession({base.doi_url("10.5555/nsfc.test.001"): error, CROSSREF_WORKS: error})
        record = paper(title=base.TITLE_1, authors=["Alice Tester"], venue="Journal of Test Imaging", year=2024,
                       identifiers={"doi": "10.5555/nsfc.test.001"})
        summary = self._run(session, record)
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["source"]), ("added", "record"))
        self.assertIn("ConnectionError", "；".join(outcome["notes"]))
        self.assertIn("doi = {10.5555/nsfc.test.001}", self.bib.read_text(encoding="utf-8"))
        leads = (self.root / "proposal" / "literature_leads.md").read_text(encoding="utf-8")
        self.assertNotIn("[unverified]", leads)

    def test_doi_of_another_paper_is_not_written(self) -> None:
        session = base.FakeSession({base.doi_url("10.5555/nsfc.test.001"): base.FakeResponse(200, {"message": base.CROSSREF_ITEM_1})})
        record = paper(title="A completely different study of liver lesions in rats", venue="Journal of Test Hepatology",
                       identifiers={"doi": "10.5555/nsfc.test.001"}, abstract=ABSTRACT, abstract_status="present")
        summary = self._run(session, record)
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["doi"]), ("added", None))
        self.assertIn("不符", "；".join(outcome["notes"]))
        self.assertNotIn("doi =", self.entry(outcome["bibkey"]))
        events = [json.loads(line) for line in (self.root / "proposal" / "citation_ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual((events[-1]["source"], events[-1]["abstract"]), ("record", ABSTRACT))

    def test_crossref_saying_dataset_blocks_the_fallback(self) -> None:
        before = self.bib.read_text(encoding="utf-8")
        by_title = base.FakeSession({CROSSREF_WORKS: base.FakeResponse(200, {"message": {"items": [base.DATASET_ITEM]}})})
        summary = self._run(by_title, paper(title=base.DATASET_ITEM["title"][0], year=2021))
        self.assertEqual(summary["outcomes"][0]["status"], "unresolved")
        by_doi = base.FakeSession({base.doi_url("10.5555/nsfc.test.reg1"): base.FakeResponse(200, {"message": base.DATASET_ITEM}),
                                   CROSSREF_WORKS: EMPTY})
        summary = self._run(by_doi, paper(title=base.DATASET_ITEM["title"][0], year=2021,
                                          identifiers={"doi": "10.5555/nsfc.test.reg1"}))
        self.assertEqual(summary["outcomes"][0]["status"], "unresolved")
        self.assertEqual(self.bib.read_text(encoding="utf-8"), before)

    def test_record_without_authors_or_year_stays_unresolved(self) -> None:
        summary = self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), paper(authors=[]), paper(record_id="r2", year=None))
        self.assertEqual([o["status"] for o in summary["outcomes"]], ["unresolved", "unresolved"])
        self.assertIn("记录缺作者", summary["outcomes"][0]["reason"])
        self.assertIn("记录缺年份", summary["outcomes"][1]["reason"])

    def test_rerun_finds_entry_by_title(self) -> None:
        self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), paper())
        before = self.bib.read_text(encoding="utf-8")
        summary = self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), paper())
        self.assertEqual((summary["outcomes"][0]["status"], summary["outcomes"][0]["bibkey"]), ("exists", "wang2023self"))
        self.assertEqual(self.bib.read_text(encoding="utf-8"), before)

    def test_chinese_record_without_article_page(self) -> None:
        record = paper(title="垃圾分类政策前后居民参与意愿对比研究", authors=["朱姝娲", "张俊杰"], venue="环境卫生工程", year=2026)
        summary = self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), record)
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["source"]), ("added", "record"))
        self.assertTrue(outcome["bibkey"].startswith("cn2026"))
        entry = self.entry(outcome["bibkey"])
        self.assertIn("author = {朱姝娲 and 张俊杰}", entry)
        self.assertIn("journal = {环境卫生工程}", entry)

    def test_incomplete_entries_are_listed_once(self) -> None:
        preprint = paper(record_id="r2", title="Breaking the Safety-Capability Tradeoff", authors=["Huan Song"], year=2025,
                         venue="arXiv (Cornell University)", publication={"is_preprint": True})
        no_venue = paper(record_id="r3", title="A participatory physical activity intervention in preschools",
                         authors=["Florian De Bock"], year=2013, venue=None, url="https://www.example.org/article/abstract")
        summary = self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), paper(), preprint, no_venue)
        keys = [o["bibkey"] for o in summary["outcomes"]]
        lines = [l for l in (self.root / "proposal" / "assumptions.md").read_text(encoding="utf-8").splitlines()
                 if "CrossRef 无记录" in l]
        self.assertEqual(len(lines), 1)
        self.assertIn(f"{keys[0]}（缺页码）", lines[0])
        self.assertIn(f"{keys[2]}（缺刊名、卷、期、页码）", lines[0])
        self.assertNotIn(keys[1], lines[0])  # 预印本本来没有卷期页

    def test_doi_with_url_tail_is_trimmed(self) -> None:
        record = paper(title="Working memory", authors=["Alan Baddeley"], year=2020, venue=None,
                       identifiers={"doi": "10.4324/9780429449642-4&type=chapterpdf"})
        summary = self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), record)
        self.assertIn("doi = {10.4324/9780429449642-4}", self.entry(summary["outcomes"][0]["bibkey"]))

    def test_refresh_refuses_record_entries(self) -> None:
        import bib_refresh
        from proposal_common import ProposalError
        record = paper(identifiers={"doi": "10.48550/arxiv.2203.11171"})
        key = self._run(base.FakeSession({CROSSREF_WORKS: EMPTY}), record)["outcomes"][0]["bibkey"]
        with self.assertRaises(ProposalError) as caught:
            bib_refresh.refresh(self.root, self.task, [key], session=base.FakeSession({}))
        self.assertIn("取自检索记录", str(caught.exception))

    def test_record_authors_split(self) -> None:
        self.assertEqual(record_authors(["G Prat-Ortega", "Ludwig van Beethoven", "Kojima, Takeshi", "朱姝娲", "Plato", " "]),
                         (("Prat-Ortega", "G"), ("van Beethoven", "Ludwig"), ("Kojima", "Takeshi"), ("朱姝娲", ""), ("Plato", "")))
        self.assertEqual(record_authors(["朱姝娲， 张俊杰、高莉洁;肖黎姗"]), (("朱姝娲", ""), ("张俊杰", ""), ("高莉洁", ""), ("肖黎姗", "")))
        # 平台记录约 7% 把作者摊平成「姓, 名, 姓, 名」：偶数个、都是单个拉丁词时两两配对；中文名不配对
        self.assertEqual(record_authors(["Dutta", "Prateek"]), (("Dutta", "Prateek"),))
        self.assertEqual(record_authors(["Lu", "Yi", "Kong", "Deyang"]), (("Lu", "Yi"), ("Kong", "Deyang")))
        self.assertEqual(record_authors(["朱姝娲", "张俊杰"]), (("朱姝娲", ""), ("张俊杰", "")))
        self.assertEqual(record_authors(["Plato", "Aristotle", "Euclid"]), (("Plato", ""), ("Aristotle", ""), ("Euclid", "")))

    def test_entry_type_from_venue(self) -> None:
        import bib_record
        from bib_resolve import WorkMeta
        cases = {"Zenodo (CERN European Organization for Nuclear Research)": ("misc", "Zenodo"),
                 "KTH Publication Database DiVA (KTH Royal Institute of Technology)": ("misc", "KTH Publication Database DiVA"),
                 "Findings of the Association for Computational Linguistics: EMNLP 2023": ("inproceedings", None),
                 "EACL (Volume 1: Long Papers)": ("inproceedings", None),
                 "Proceedings of the National Academy of Sciences": ("article", None),
                 "ACM Comput. Surv.": ("article", None),
                 None: ("misc", None)}
        for venue, (kind, howpublished) in cases.items():
            with self.subTest(venue=venue):
                meta, _ = bib_record.record_meta(paper(venue=venue), work_meta=WorkMeta)
                self.assertEqual(meta.entry_type, kind)
                if howpublished:
                    self.assertEqual(meta.journal, howpublished)


if __name__ == "__main__":
    unittest.main()
