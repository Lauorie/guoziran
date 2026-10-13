"""CrossRef 没有记录时，按文献记录自带的字段写 .bib 条目（bib_resolve 调用）。

记录来自检索（wispaper）或申请人材料。只用记录里已有的字段：作者、题名、刊名或会议名、年份、DOI、arXiv 号与网址；
卷、期、页码记录里没有，就不写，不凭记忆补。文献类型按记录判断：预印本（arXiv 等）写 @misc，会议写 @inproceedings，
其余有刊名的写 @article，没有刊名的写 @misc。类型判断错只影响文献类型标识，不改动任何字段的内容。
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from bib_cn import safe_url
from latex_files import normalize_doi

SOURCE = "record"
CJK_RE = re.compile(r"[\u3400-\u9fff]")
CJK_NAME_SEPARATORS = re.compile(r"\s*[，、；;,]\s*")  # 中文作者名常连成一串：「朱姝娲， 张俊杰、高莉洁」
PARTICLES = frozenset({"van", "von", "der", "den", "de", "del", "della", "di", "da", "du", "dos", "das", "le", "la",
                       "ten", "ter", "bin", "al"})
ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5}|[a-z][a-z.\-]*/\d{7})(?:v\d+)?", re.IGNORECASE)
ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", re.IGNORECASE)
PREPRINT_MARKS = ("arxiv", "biorxiv", "medrxiv", "chemrxiv", "techrxiv", "ssrn", "research square", "preprints.org",
                  "preprint", "zenodo", "figshare", "repository", "publication database")  # 预印本与存储库按网络文献写
JOURNAL_RE = re.compile(r"\b(journal|transactions|letters)\b|national academy|royal society", re.IGNORECASE)
CONFERENCE_RE = re.compile(r"\b(conference|proceedings|symposium|workshop|congress|meeting|findings|papers|neurips|nips|"
                           r"iclr|icml|aaai|ijcai|cvpr|iccv|eccv|acl|eacl|emnlp|naacl|coling|kdd|sigir|icse)\b|neural information processing "
                           r"systems|learning representations", re.IGNORECASE)
MISSING = {"article": ("卷", "期", "页码"), "inproceedings": ("页码",), "misc": ("刊名", "卷", "期", "页码")}
URL_TAIL_RE = re.compile(r"[&?]\w+=.*$")  # 检索记录里的 DOI 偶尔带网址参数，如 &type=chapterpdf


def _split_name(name: str) -> tuple[str, str] | None:
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return None
    if CJK_RE.search(name):
        return name, ""
    if "," in name:
        family, given = (part.strip() for part in name.split(",", 1))
        return family, given
    parts = name.split(" ")
    if len(parts) == 1:
        return name, ""
    start = len(parts) - 1
    while start > 1 and parts[start - 1].lower() in PARTICLES:  # van、von 等归入姓
        start -= 1
    return " ".join(parts[start:]), " ".join(parts[:start])


def record_authors(names: Any) -> tuple[tuple[str, str], ...]:
    """记录里的作者名 →（姓, 名）。中文名整体作姓，连成一串的按中文分隔符拆开；「名 姓」取最后一词作姓；「姓, 名」按逗号分。"""
    items = names if isinstance(names, (list, tuple)) else []
    raw: list[str] = []
    for item in items:
        text = str(item.get("name") if isinstance(item, Mapping) else item or "")
        raw += CJK_NAME_SEPARATORS.split(text) if CJK_RE.search(text) else [text]
    raw = [re.sub(r"\s+", " ", name).strip() for name in raw if name.strip()]
    if len(raw) % 2 == 0 and raw and all(re.fullmatch(r"[^\W\d_][\w.'\-]*", n) and not CJK_RE.search(n) for n in raw):
        return tuple(zip(raw[0::2], raw[1::2]))  # 检索记录把作者摊平成「姓, 名, 姓, 名」
    return tuple(pair for pair in (_split_name(name) for name in raw) if pair)


def _clean(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or None


def arxiv_id(record: Mapping[str, Any]) -> str | None:
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), Mapping) else {}
    doi = normalize_doi(identifiers.get("doi") or record.get("doi")) or ""
    url_match = ARXIV_URL_RE.search(str(record.get("url") or ""))
    doi_match = ARXIV_DOI_RE.match(doi)
    for raw in (identifiers.get("arxiv"), record.get("arxiv_id"), doi_match and doi_match.group(1),
                url_match and url_match.group(1)):
        match = ARXIV_ID_RE.search(re.sub(r"^arxiv:", "", str(raw or ""), flags=re.IGNORECASE))
        if raw and match:
            return match.group(1)
    return None


def _web_url(value: Any) -> str | None:
    """只写公网 http(s) 地址；内网、带端口或带账号的地址不写进参考文献。"""
    url = _clean(value)
    return safe_url(url) if url and re.match(r"^https?://\S+$", url) else None


def _is_preprint(record: Mapping[str, Any]) -> bool:
    """预印本或存储库（arXiv、Zenodo 等）：本来没有卷期页。"""
    publication = record.get("publication") if isinstance(record.get("publication"), Mapping) else {}
    probe = f"{record.get('venue') or ''} {record.get('url') or ''}".lower()
    return bool(arxiv_id(record)) or publication.get("is_preprint") is True or any(mark in probe for mark in PREPRINT_MARKS)


def _record_doi(record: Mapping[str, Any]) -> str | None:
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), Mapping) else {}
    doi = normalize_doi(identifiers.get("doi") or record.get("doi"))
    return URL_TAIL_RE.sub("", doi) or None if doi else None


def _entry_type(record: Mapping[str, Any], venue: str | None) -> str:
    if _is_preprint(record) or not venue:
        return "misc"
    if JOURNAL_RE.search(venue):
        return "article"
    return "inproceedings" if CONFERENCE_RE.search(venue) else "article"


def record_meta(record: Mapping[str, Any], *, work_meta: type, drop_doi: bool = False) -> tuple[Any | None, str | None]:
    """返回（元数据, 缺项说明）。题名、作者、年份缺一不写条目；drop_doi 为真时不写记录的 DOI（它在 CrossRef 中是另一篇）。"""
    title = _clean(record.get("title"))
    authors = record_authors(record.get("authors"))
    year = record.get("year") if isinstance(record.get("year"), int) and not isinstance(record.get("year"), bool) else None
    lacking = [label for label, value in (("题名", title), ("作者", authors), ("年份", year)) if not value]
    if lacking:
        return None, "记录缺" + "、".join(lacking) + "，不写条目"
    venue = _clean(record.get("venue"))
    arxiv = arxiv_id(record)
    entry_type = _entry_type(record, venue)
    if entry_type == "misc":
        venue = f"arXiv preprint arXiv:{arxiv}" if arxiv else (re.sub(r"\s*\([^)]*\)$", "", venue) if venue else None)
    meta = work_meta(title=title, authors=authors, journal=venue, year=year, volume=None, issue=None, pages=None,
                     doi=None if drop_doi else _record_doi(record),
                     entry_type=entry_type, url=_web_url(record.get("url")) if entry_type == "misc" else None)
    return meta, None


def missing_fields(record: Mapping[str, Any], entry_type: str) -> tuple[str, ...]:
    """按记录写的条目缺哪些国标著录项；预印本与存储库本来没有卷期页，返回空。"""
    return () if _is_preprint(record) else MISSING.get(entry_type, ())
