"""CrossRef 查不到的中文文献：用检索记录与出版方文章页的引文标签补全元数据（供 bib_resolve.py 调用）。

只处理标题含汉字的记录。期刊名、卷、期、页码、DOI、摘要取自记录 url 指向的文章页中的
<meta name="citation_*"> 标签（Highwire Press 标签，期刊官网普遍提供），题名与作者优先取文章页、缺时取检索记录，
都不凭记忆补。文章页的题名须与记录标题相符；缺期刊名时不兜底。DOI 先经 doi.org 的 handle 接口确认已注册，
否则不写。只访问 http/https 的公网主机名（不访问 IP 字面量、localhost、.local/.internal），页面最多读 2 MB。
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import quote, urlparse

import requests

from http_retry import failure_label, get_with_retry
from latex_files import normalize_doi

SOURCE = "publisher_page"
USER_AGENT = "Mozilla/5.0 (compatible; nsfc-proposal-bib-resolve/0.1)"
DOI_HANDLE_API = "https://doi.org/api/handles/"
MAX_PAGE_BYTES = 2_000_000
MIN_ABSTRACT_CHARS = 80
CJK_RE = re.compile(r"[㐀-䶿一-鿿]")
META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
ATTR_RE = re.compile(r"([A-Za-z_:][-\w:.]*)\s*=\s*(\"([^\"]*)\"|'([^']*)')", re.S)
CHARSET_RE = re.compile(rb"charset\s*=\s*[\"']?([A-Za-z0-9_-]+)", re.IGNORECASE)
DOI_IN_TEXT_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>?#]+")
AUTHOR_SPLIT_RE = re.compile(r"\s*[，,、;；]\s*")
YEAR_RE = re.compile(r"(19|20)\d{2}")
BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localdomain")


@dataclass
class Fallback:
    """兜底结果：meta 为 None 时 reason 写明原因；extras 进 bib_resolve 的结果与台账。"""
    meta: Any = None
    reason: str | None = None
    landing_url: str | None = None
    abstract: str | None = None
    notes: list[str] = field(default_factory=list)


def has_cjk(text: str | None) -> bool:
    return bool(CJK_RE.search(text or ""))


def safe_url(url: Any) -> str | None:
    """只放行 http/https 的公网主机名；返回规范化后的地址，不合格时返回 None。"""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        return None
    if port not in (None, 80, 443) or host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES) or "." not in host:
        return None
    try:
        ipaddress.ip_address(host.strip("[]"))
        return None  # IP 字面量
    except ValueError:
        pass
    return url.strip()


def decode_html(content: bytes, content_type: str = "") -> str:
    """按响应头或页内 charset 解码；都没有时先试 UTF-8，再试 GB18030（中文期刊站常见 GBK）。"""
    candidates = []
    for source in (content_type.encode("ascii", "ignore"), content[:4096]):
        match = CHARSET_RE.search(source)
        if match:
            candidates.append(match.group(1).decode("ascii").lower())
    candidates += ["utf-8", "gb18030"]
    for charset in candidates:
        try:
            return content.decode("gb18030" if charset in ("gbk", "gb2312") else charset)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


def parse_meta(text: str) -> dict[str, list[str]]:
    """收集 <meta name=... content=...>，键名小写；同名多值按出现顺序保留。"""
    tags: dict[str, list[str]] = {}
    for tag in META_RE.findall(text):
        attrs = {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4)) for m in ATTR_RE.finditer(tag)}
        name = (attrs.get("name") or attrs.get("property") or "").strip().lower()
        content = html.unescape(attrs.get("content") or "").strip()
        if name and content:
            tags.setdefault(name, []).append(content)
    return tags


def _first(tags: Mapping[str, list[str]], *names: str) -> str | None:
    """按名字顺序取第一个值；同名有中英文两种写法时（xml:lang 不同），取含汉字的那个。"""
    for name in names:
        values = tags.get(name) or []
        if values:
            return next((v for v in values if has_cjk(v)), values[0])
    return None


def split_authors(values: Any) -> list[str]:
    """检索记录的中文作者常是一整串（「李长军， 边少卿， …」）；按中英文逗号、顿号、分号拆开。"""
    names: list[str] = []
    for value in values if isinstance(values, list) else [values]:
        for part in AUTHOR_SPLIT_RE.split(str(value or "")):
            part = re.sub(r"\s+", " ", part).strip()
            if part and part not in names:
                names.append(part)
    return names


def doi_registered(session: Any, doi: str, settings: Any) -> bool | None:
    """doi.org handle 接口：responseCode 1 为已注册，100 为不存在；网络失败返回 None。"""
    try:
        response = get_with_retry(session, DOI_HANDLE_API + quote(doi, safe="/"), params=None,
                                  headers={"User-Agent": USER_AGENT}, timeout=settings.timeout,
                                  retries=settings.http_retries, backoff_s=settings.http_backoff_s, sleep=settings.sleep)
        if getattr(response, "status_code", 200) == 404:
            return False
        response.raise_for_status()
        return (response.json() or {}).get("responseCode") == 1
    except (requests.RequestException, ValueError):
        return None


def fetch_page(session: Any, url: str, settings: Any) -> tuple[str | None, str | None]:
    """返回（页面文字, 失败原因）。"""
    try:
        response = get_with_retry(session, url, params=None, headers={"User-Agent": USER_AGENT}, timeout=settings.timeout,
                                  retries=settings.http_retries, backoff_s=settings.http_backoff_s, sleep=settings.sleep)
        response.raise_for_status()
    except requests.RequestException as exc:
        return None, f"文章页打不开（{failure_label(exc)}）"
    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
    if content_type and "html" not in content_type.lower():
        return None, f"文章页不是 HTML（{content_type.split(';')[0]}）"
    content = getattr(response, "content", b"") or b""
    return decode_html(content[:MAX_PAGE_BYTES], content_type), None


def _strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text))).strip()


def _year(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    match = YEAR_RE.search(str(value or ""))
    return int(match.group(0)) if match else None


def fallback_meta(record: Mapping[str, Any], *, session: Any, settings: Any, work_meta: type,
                  title_matches: Any, year_ok: Any) -> Fallback:
    """按文章页的引文标签补全一条中文记录；work_meta、title_matches、year_ok 由 bib_resolve 传入，避免循环导入。"""
    title = str(record.get("title") or "").strip()
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), Mapping) else {}
    url = safe_url(record.get("url"))
    if not url:
        return Fallback(reason="中文文献兜底：记录没有可访问的文章页地址")
    if urlparse(url).path.lower().endswith(".pdf"):
        return Fallback(reason="中文文献兜底：记录的地址是 PDF，不是文章页", landing_url=url)  # 不下载、不读 PDF
    text, failure = fetch_page(session, url, settings)
    if text is None:
        return Fallback(reason=f"中文文献兜底：{failure}", landing_url=url)
    tags = parse_meta(text)
    page_title = next((t for t in (tags.get("citation_title") or []) + (tags.get("dc.title") or [])
                       if title_matches(title, t, settings.title_similarity)), None)
    if not page_title:
        return Fallback(reason="中文文献兜底：文章页题名与记录不符或缺失", landing_url=url)
    journal = _first(tags, "citation_journal_title", "prism.publicationname", "citation_conference_title")
    if not journal:
        return Fallback(reason="中文文献兜底：文章页没有期刊名（citation_journal_title）", landing_url=url)
    record_year = _year(record.get("year"))
    page_year = _year(_first(tags, "citation_publication_date", "citation_date", "citation_year", "dc.date"))
    if not year_ok(record_year, page_year, settings.year_window):
        return Fallback(reason=f"中文文献兜底：年份不符（记录 {record_year}，文章页 {page_year}）", landing_url=url)
    page_authors = split_authors(tags.get("citation_author") or [])
    if any(has_cjk(a) for a in page_authors):
        page_authors = [a for a in page_authors if has_cjk(a)]  # 中英文作者名并列时只留中文
    authors = page_authors or split_authors(record.get("authors") or [])
    if not authors:
        return Fallback(reason="中文文献兜底：没有作者", landing_url=url)
    notes: list[str] = []
    doi = normalize_doi(identifiers.get("doi") or record.get("doi") or _first(tags, "citation_doi", "dc.identifier"))
    if not doi:
        match = DOI_IN_TEXT_RE.search(url)
        doi = normalize_doi(match.group(0)) if match else None
    if doi:
        registered = doi_registered(session, doi, settings)
        if registered is not True:
            notes.append(f"DOI {doi} {'未在 doi.org 注册' if registered is False else '未能在 doi.org 确认'}，未写入")
            doi = None
    first, last = _first(tags, "citation_firstpage"), _first(tags, "citation_lastpage")
    pages = f"{first}-{last}" if first and last and first != last else first
    abstract = _first(tags, "citation_abstract", "dc.description")
    abstract = _strip_tags(abstract) if abstract else None
    meta = work_meta(title=page_title, authors=tuple((name, "") for name in authors), journal=journal,
                     year=page_year or record_year, volume=_first(tags, "citation_volume"),
                     issue=_first(tags, "citation_issue"), pages=pages, doi=doi, entry_type="article")
    return Fallback(meta=meta, landing_url=url, notes=notes,
                    abstract=abstract if abstract and len(abstract) >= MIN_ABSTRACT_CHARS else None)


def cn_bibkey(title: str, year: int | None) -> str:
    """中文条目的 key：cn + 年份 + 题名哈希前 6 位（作者名转不成 ASCII）。"""
    return f"cn{year or 'nd'}{hashlib.sha1(title.encode('utf-8')).hexdigest()[:6]}"
