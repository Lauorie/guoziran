"""bib_cn.py 与 bib_resolve 的中文文献兜底：CrossRef 没有记录时，按出版方文章页的引文标签补全。不联网。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import bib_cn  # noqa: E402
from bib_resolve import run  # noqa: E402
from citation_ledger import load_ledger  # noqa: E402

TITLE = "垃圾分类政策前后居民参与意愿对比研究——以上海市为例"
URL = "https://www.journal.example.cn/CN/10.19841/j.cnki.hjwsgc.2026.03.014"
DOI = "10.19841/j.cnki.hjwsgc.2026.03.014"
ABSTRACT = "以上海市为例，比较垃圾分类政策实施前后居民的参与意愿。" * 4
PAGE = f"""<html><head><meta charset="utf-8">
<meta name="citation_title" xml:lang="cn" content="{TITLE}" />
<meta name="citation_title" xml:lang="en" content="Residents' willingness before and after the policy" />
<meta name="citation_journal_title" content="环境卫生工程" />
<meta name="citation_journal_title" xml:lang="en" content="Environmental Sanitation Engineering" />
<meta name="citation_author" content="朱姝娲" /><meta name="citation_author" content="张俊杰" />
<meta name="citation_author" xml:lang="en" content="ZHU Shuwa" />
<meta content="34" name="citation_volume" /><meta name="citation_issue" content="3" />
<meta name="citation_firstpage" content="112" /><meta name="citation_lastpage" content="119" />
<meta name="citation_publication_date" content="2026-06-25" />
<meta name="citation_doi" content="{DOI}" />
<meta name="citation_abstract" content="&lt;p&gt;{ABSTRACT}&lt;/p&gt;" />
</head><body></body></html>"""
RECORD = {"record_id": "title:abc", "title": TITLE, "year": 2026, "authors": ["朱姝娲， 张俊杰， 高莉洁"], "url": URL,
          "abstract": "… 片段 …", "abstract_status": "missing"}


class Response:
    def __init__(self, status: int, payload: Any = None, *, content: bytes = b"", content_type: str = "") -> None:
        self.status_code = status
        self._payload = payload
        self.content = content
        self.headers = {"Content-Type": content_type} if content_type else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)

    def json(self) -> Any:
        return self._payload


class Session:
    """按 URL 返回响应；未登记的 URL 返回 404（CrossRef 标题检索因此没有结果）。"""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, params: Any = None, headers: Any = None, timeout: Any = None) -> Response:
        self.calls.append(url)
        value = self.routes.get(url)
        if isinstance(value, Exception):
            raise value
        return value if value is not None else Response(404)


def page(text: str = PAGE, encoding: str = "utf-8", content_type: str = "text/html") -> Response:
    return Response(200, content=text.encode(encoding), content_type=content_type)


def handle(found: bool) -> Response:
    return Response(200, {"responseCode": 1}) if found else Response(404, {"responseCode": 100})


class ParsingTest(unittest.TestCase):
    def test_meta_tags_prefer_chinese_values(self) -> None:
        tags = bib_cn.parse_meta(PAGE)
        self.assertEqual(bib_cn._first(tags, "citation_journal_title"), "环境卫生工程")
        self.assertEqual(tags["citation_volume"], ["34"])  # content 在 name 之前也能读到
        self.assertEqual(len(tags["citation_author"]), 3)

    def test_split_authors(self) -> None:
        self.assertEqual(bib_cn.split_authors(["李长军， 边少卿，薛云舒、马宗良;玛丽"]), ["李长军", "边少卿", "薛云舒", "马宗良", "玛丽"])

    def test_gbk_page_is_decoded(self) -> None:
        text = PAGE.replace('<meta charset="utf-8">', '<meta http-equiv="Content-Type" content="text/html; charset=gbk">')
        self.assertIn("环境卫生工程", bib_cn.decode_html(text.encode("gbk")))

    def test_safe_url(self) -> None:
        self.assertEqual(bib_cn.safe_url(URL), URL)
        for bad in ("ftp://a.example.cn/x", "http://127.0.0.1/x", "http://localhost/x", "http://[::1]/x",
                    "http://intranet/x", "http://a.internal/x", "http://u:p@a.example.cn/x", "http://a.example.cn:8080/x", None):
            self.assertIsNone(bib_cn.safe_url(bad), bad)


class ResolveFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "proj"
        (self.root / "references").mkdir(parents=True)
        (self.root / "proposal").mkdir()
        (self.root / "main.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
        self.bib = self.root / "references" / "refs.bib"
        self.bib.write_text("", encoding="utf-8")
        (self.root / "proposal" / "literature_leads.md").write_text("# 文献线索\n\n## 未核实线索\n", encoding="utf-8")
        (self.root / "proposal" / "assumptions.md").write_text("# 假设\n\n## 待核实项\n", encoding="utf-8")
        self.task = base / ".bensz-api" / "task-20261013-1200-cn"
        self.records = base / "records.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def resolve(self, session: Session, record: dict = RECORD) -> dict:
        self.records.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
        return run(self.root, self.records, self.task, session=session, sleep=lambda s: None)

    def test_chinese_record_added_from_publisher_page(self) -> None:
        session = Session({URL: page(), bib_cn.DOI_HANDLE_API + DOI: handle(True)})
        summary = self.resolve(session)
        outcome = summary["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["source"]), ("added", "publisher_page"))
        self.assertTrue(outcome["bibkey"].startswith("cn2026"))
        text = self.bib.read_text(encoding="utf-8")
        for field in ("title = {{" + TITLE + "}}", "author = {朱姝娲 and 张俊杰}", "journal = {环境卫生工程}", "volume = {34}",
                      "number = {3}", "pages = {112--119}", "year = {2026}", f"doi = {{{DOI}}}"):
            self.assertIn(field, text)
        self.assertNotIn("ZHU", text)
        entry = load_ledger(self.root / "proposal" / "citation_ledger.jsonl")[outcome["bibkey"]]
        self.assertEqual(entry["source"], "publisher_page")
        self.assertEqual(entry["provenance"]["landing_url"], URL)
        self.assertEqual(entry["abstract"], ABSTRACT)
        pending = (self.root / "proposal" / "assumptions.md").read_text(encoding="utf-8")
        self.assertIn(f"中文文献 {outcome['bibkey']}", pending)
        self.assertIn("对照知网", pending)

    def test_unregistered_doi_is_dropped_with_note(self) -> None:
        session = Session({URL: page(), bib_cn.DOI_HANDLE_API + DOI: handle(False)})
        outcome = self.resolve(session)["outcomes"][0]
        self.assertEqual(outcome["status"], "added")
        self.assertIsNone(outcome["doi"])
        self.assertNotIn("doi =", self.bib.read_text(encoding="utf-8"))
        self.assertIn("未在 doi.org 注册", (self.root / "proposal" / "assumptions.md").read_text(encoding="utf-8"))

    def from_record(self, outcome: dict, why: str) -> None:
        """出版方页面用不上时，按检索记录写入（不再挡掉），页面没用上的原因留在 notes。"""
        self.assertEqual((outcome["status"], outcome["source"]), ("added", "record"))
        self.assertIn(why, "；".join(outcome["notes"]))
        self.assertIn("author = {朱姝娲 and 张俊杰 and 高莉洁}", self.bib.read_text(encoding="utf-8"))
        self.assertNotIn("[unverified]", (self.root / "proposal" / "literature_leads.md").read_text(encoding="utf-8"))

    def test_page_without_journal_is_not_used(self) -> None:
        text = "\n".join(line for line in PAGE.splitlines() if "journal_title" not in line)
        outcome = self.resolve(Session({URL: page(text)}))["outcomes"][0]
        self.from_record(outcome, "没有期刊名")
        self.assertNotIn("环境卫生工程", self.bib.read_text(encoding="utf-8"))

    def test_page_for_another_paper_is_rejected(self) -> None:
        other = PAGE.replace(TITLE, "城市居民生活垃圾分类行为意愿研究")
        outcome = self.resolve(Session({URL: page(other)}))["outcomes"][0]
        self.from_record(outcome, "题名与记录不符")
        self.assertNotIn("城市居民生活垃圾分类行为意愿研究", self.bib.read_text(encoding="utf-8"))

    def test_unreachable_or_non_html_page(self) -> None:
        for response in (requests.ConnectionError("down"), page(content_type="application/pdf"), Response(403)):
            self.bib.write_text("", encoding="utf-8")
            outcome = self.resolve(Session({URL: response}))["outcomes"][0]
            self.from_record(outcome, "中文文献兜底")

    def test_pdf_url_is_not_fetched(self) -> None:
        record = dict(RECORD, url="https://www.journal.example.cn/download/paper.PDF")
        session = Session({})
        outcome = self.resolve(session, record)["outcomes"][0]
        self.from_record(outcome, "地址是 PDF")
        self.assertNotIn(record["url"], session.calls)

    def test_english_record_never_falls_back(self) -> None:
        record = dict(RECORD, title="Household recycling habits in Bangkok")
        session = Session({URL: page()})
        outcome = self.resolve(session, record)["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["source"]), ("added", "record"))
        self.assertNotIn(URL, session.calls)

    def test_private_address_is_not_fetched(self) -> None:
        record = dict(RECORD, url="http://10.0.0.5/paper.htm")
        session = Session({})
        outcome = self.resolve(session, record)["outcomes"][0]
        self.from_record(outcome, "中文文献兜底")
        self.assertNotIn("http://10.0.0.5/paper.htm", session.calls)
        self.assertNotIn("10.0.0.5", self.bib.read_text(encoding="utf-8"))  # 内网地址也不写进参考文献

    def test_refresh_refuses_publisher_page_entries(self) -> None:
        import bib_refresh
        from proposal_common import ProposalError
        session = Session({URL: page(), bib_cn.DOI_HANDLE_API + DOI: handle(True)})
        key = self.resolve(session)["outcomes"][0]["bibkey"]
        with self.assertRaises(ProposalError) as caught:
            bib_refresh.refresh(self.root, self.task, [key], session=session)
        self.assertIn("出版方文章页", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
