#!/usr/bin/env python3
"""把选作证据的文献记录补全成 .bib 条目（设计文档 6.4 节）。

输入：rls.paper.v1 记录（JSONL）。有 DOI 时查 CrossRef 并核对标题；没有 DOI 或核对失败时，
按标题查 CrossRef，再查 OpenAlex。核对成功的条目追加到 main.tex 指向的第一个 .bib
（写前备份，按 DOI 去重）；其余写入 proposal/literature_leads.md，标 [unverified]，正文不得引用。
退出码：0 完成（含未核实条目）；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.parse import quote

import requests

from citation_ledger import record_added
from latex_files import BibIndex, bib_entry_texts, normalize_doi, read_bib_index, scan_latex_tree
from proposal_common import ProposalError, append_under_heading, load_config, proposal_paths, resolve_project_root

USER_AGENT = "nsfc-proposal-bib-resolve/0.1"
CROSSREF_WORKS = "https://api.crossref.org/works"
OPENALEX_WORKS = "https://api.openalex.org/works"
ELLIPSIS_RE = re.compile(r"…|\.\.\.")
MIN_FRAGMENT_CHARS = 20
STOPWORDS = frozenset({"a", "an", "the", "of", "on", "in", "for", "and", "to", "with", "by", "from", "at", "via", "is", "are"})
LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
}


class HttpSession(Protocol):
    def get(self, url: str, params: Mapping[str, Any] | None = None, headers: Mapping[str, str] | None = None,
            timeout: float | None = None) -> Any: ...


@dataclass(frozen=True)
class Settings:
    title_similarity: float = 0.92
    doi_title_similarity: float = 0.8
    year_window: int = 1
    timeout: float = 15.0

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "Settings":
        lit = config.get("literature") or {}
        return cls(
            title_similarity=float(lit.get("title_similarity", 0.92)),
            doi_title_similarity=float(lit.get("doi_title_similarity", 0.8)),
            year_window=int(lit.get("year_window", 1)),
            timeout=float(lit.get("http_timeout_s", 15)),
        )


@dataclass(frozen=True)
class WorkMeta:
    title: str
    authors: tuple[tuple[str, str], ...]
    journal: str | None
    year: int | None
    volume: str | None
    issue: str | None
    pages: str | None
    doi: str | None
    entry_type: str = "article"


@dataclass
class Outcome:
    record_id: str
    title: str
    status: str
    bibkey: str | None = None
    doi: str | None = None
    source: str | None = None
    reason: str | None = None


def _get_json(session: HttpSession, url: str, params: Mapping[str, Any] | None, timeout: float) -> Any | None:
    response = session.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    if getattr(response, "status_code", 200) == 404:
        return None
    response.raise_for_status()
    return response.json()


def _str(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None


def _crossref_year(item: Mapping[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "published"):
        block = item.get(key)
        parts = block.get("date-parts") if isinstance(block, Mapping) else None
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def crossref_meta(item: Mapping[str, Any]) -> WorkMeta | None:
    titles = item.get("title")
    title = titles[0].strip() if isinstance(titles, list) and titles and isinstance(titles[0], str) else ""
    if not title:
        return None
    authors = []
    for author in item.get("author") or []:
        if isinstance(author, Mapping) and (author.get("family") or author.get("name")):
            authors.append((str(author.get("family") or author.get("name")).strip(), str(author.get("given") or "").strip()))
    journals = item.get("container-title")
    journal = journals[0] if isinstance(journals, list) and journals else None
    kind = item.get("type")
    entry_type = "article" if kind in (None, "journal-article") else ("inproceedings" if kind == "proceedings-article" else "misc")
    return WorkMeta(title=title, authors=tuple(authors), journal=_str(journal), year=_crossref_year(item),
                    volume=_str(item.get("volume")), issue=_str(item.get("issue")), pages=_str(item.get("page")),
                    doi=normalize_doi(item.get("DOI")), entry_type=entry_type)


def openalex_meta(item: Mapping[str, Any]) -> WorkMeta | None:
    title = str(item.get("title") or item.get("display_name") or "").strip()
    if not title:
        return None
    authors = []
    for authorship in item.get("authorships") or []:
        name = str(((authorship or {}).get("author") or {}).get("display_name") or "").strip()
        if name:
            parts = name.split()
            authors.append((parts[-1], " ".join(parts[:-1])))
    source = ((item.get("primary_location") or {}).get("source") or {})
    biblio = item.get("biblio") or {}
    first, last = _str(biblio.get("first_page")), _str(biblio.get("last_page"))
    pages = f"{first}--{last}" if first and last and first != last else first
    year = item.get("publication_year") if isinstance(item.get("publication_year"), int) else None
    return WorkMeta(title=title, authors=tuple(authors), journal=_str(source.get("display_name")), year=year,
                    volume=_str(biblio.get("volume")), issue=_str(biblio.get("issue")), pages=pages,
                    doi=normalize_doi(item.get("doi")))


def _norm_title(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_matches(wanted: str, candidate: str, threshold: float) -> bool:
    """完整标题按相似度比较；含省略号的截断标题要求每个足够长的片段都出现在候选标题中。"""
    if ELLIPSIS_RE.search(wanted):
        fragments = [f for f in (_norm_title(p) for p in ELLIPSIS_RE.split(wanted)) if len(f) >= MIN_FRAGMENT_CHARS]
        target = _norm_title(candidate)
        return bool(fragments) and all(f in target for f in fragments)
    return SequenceMatcher(None, _norm_title(wanted), _norm_title(candidate)).ratio() >= threshold


def year_ok(wanted: int | None, found: int | None, window: int) -> bool:
    return wanted is None or found is None or abs(wanted - found) <= window


def _ascii(text: str) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower())


def make_bibkey(meta: WorkMeta, taken: set[str]) -> str:
    family = (_ascii(meta.authors[0][0]) if meta.authors else "") or "anon"
    first = next((w for w in (_ascii(x) for x in _norm_title(meta.title).split()) if w and w not in STOPWORDS), "untitled")
    base = f"{family}{meta.year or 'nd'}{first}"
    key, suffix = base, 0
    while key in taken:
        suffix += 1
        key = base + chr(ord("a") + suffix - 1)
    taken.add(key)
    return key


def _escape(text: str) -> str:
    text = re.sub(r"</?(?:i|b|em|strong|sub|sup|scp|span|mml:[A-Za-z]+)(?:\s[^>]*)?>", "", text, flags=re.IGNORECASE)
    return "".join(LATEX_SPECIALS.get(ch, ch) for ch in text)


def to_bibtex(meta: WorkMeta, key: str) -> str:
    venue_field = {"article": "journal", "inproceedings": "booktitle"}.get(meta.entry_type, "howpublished")
    authors = " and ".join(f"{_escape(f)}, {_escape(g)}" if g else _escape(f) for f, g in meta.authors)
    pages = meta.pages.replace("-", "--") if meta.pages and "--" not in meta.pages else meta.pages
    fields = [
        ("title", "{" + _escape(meta.title) + "}"),
        ("author", authors or None),
        (venue_field, _escape(meta.journal) if meta.journal else None),
        ("year", str(meta.year) if meta.year else None),
        ("volume", meta.volume),
        ("number", meta.issue),
        ("pages", pages),
        ("doi", meta.doi),
    ]
    lines = [f"@{meta.entry_type}{{{key},"]
    lines += [f"  {name} = {{{value}}}," for name, value in fields if value]
    lines.append("}")
    return "\n".join(lines) + "\n"


def _record_fields(record: Mapping[str, Any]) -> tuple[str | None, str, int | None]:
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), Mapping) else {}
    doi = normalize_doi(identifiers.get("doi") or record.get("doi"))
    title = str(record.get("title") or "").strip()
    year = record.get("year")
    return doi, title, year if isinstance(year, int) and not isinstance(year, bool) else None


def _authoritative_by_doi(doi: str, title: str, *, session: HttpSession, settings: Settings) -> WorkMeta | None:
    """用 DOI 回 CrossRef 取元数据；查询失败、无此 DOI 或标题不符时返回 None。"""
    try:
        data = _get_json(session, f"{CROSSREF_WORKS}/{quote(doi, safe='/')}", None, settings.timeout)
    except (requests.RequestException, ValueError):
        return None
    meta = crossref_meta((data or {}).get("message") or {}) if data else None
    if meta is None or not title_matches(title, meta.title, settings.doi_title_similarity):
        return None
    return meta


def lookup(record: Mapping[str, Any], *, session: HttpSession, settings: Settings) -> tuple[WorkMeta | None, str | None, str | None]:
    """返回 (元数据, 来源, 失败原因)；元数据为 None 时原因非空。"""
    doi, title, year = _record_fields(record)
    failures: list[str] = []
    if doi:
        try:
            data = _get_json(session, f"{CROSSREF_WORKS}/{quote(doi, safe='/')}", None, settings.timeout)
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"CrossRef DOI 查询失败（{type(exc).__name__}）")
        else:
            meta = crossref_meta((data or {}).get("message") or {}) if data else None
            if meta is None:
                failures.append("CrossRef 没有这个 DOI")
            elif title and not title_matches(title, meta.title, settings.doi_title_similarity):
                failures.append(f"DOI {doi} 对应的标题与记录不符")
            else:
                return meta, "crossref", None
    if not title:
        return None, None, "；".join(failures + ["记录没有标题"])
    query = re.sub(r"\s+", " ", ELLIPSIS_RE.sub(" ", title)).strip()
    searches: tuple[tuple[str, str, dict[str, Any], Callable[[Any], list], Callable[[Mapping[str, Any]], WorkMeta | None]], ...] = (
        ("CrossRef", CROSSREF_WORKS, {"query.bibliographic": query, "rows": 5},
         lambda d: ((d or {}).get("message") or {}).get("items") or [], crossref_meta),
        ("OpenAlex", OPENALEX_WORKS, {"search": query, "per-page": 5},
         lambda d: (d or {}).get("results") or [], openalex_meta),
    )
    for label, url, params, items_of, to_meta in searches:
        try:
            data = _get_json(session, url, params, settings.timeout)
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"{label} 标题检索失败（{type(exc).__name__}）")
            continue
        for item in items_of(data):
            meta = to_meta(item) if isinstance(item, Mapping) else None
            if meta and title_matches(title, meta.title, settings.title_similarity) and year_ok(year, meta.year, settings.year_window):
                if label == "OpenAlex" and meta.doi:
                    authoritative = _authoritative_by_doi(meta.doi, title, session=session, settings=settings)
                    if authoritative:
                        return authoritative, "crossref", None
                return meta, label.lower(), None
        failures.append(f"{label} 无标题匹配的条目")
    return None, None, "；".join(failures)


def resolve_records(records: Iterable[Mapping[str, Any]], *, session: HttpSession, settings: Settings,
                    index: BibIndex) -> tuple[list[Outcome], list[str]]:
    taken = set(index.keys)
    known = dict(index.doi_keys)
    outcomes: list[Outcome] = []
    entries: list[str] = []
    for record in records:
        doi, title, _ = _record_fields(record)
        record_id = str(record.get("record_id") or title or "?")
        if doi and doi in known:
            outcomes.append(Outcome(record_id, title, "exists", bibkey=known[doi], doi=doi))
            continue
        meta, source, reason = lookup(record, session=session, settings=settings)
        if meta is None:
            outcomes.append(Outcome(record_id, title, "unresolved", reason=reason))
            continue
        if meta.doi and meta.doi in known:
            outcomes.append(Outcome(record_id, title, "exists", bibkey=known[meta.doi], doi=meta.doi, source=source))
            continue
        key = make_bibkey(meta, taken)
        entries.append(to_bibtex(meta, key))
        if meta.doi:
            known[meta.doi] = key
        outcomes.append(Outcome(record_id, title, "added", bibkey=key, doi=meta.doi, source=source))
    return outcomes, entries


def append_entries(bib_path: Path, entries: list[str], backup_dir: Path) -> Path | None:
    """追加条目；写前备份。没有条目时不碰文件。"""
    if not entries:
        return None
    backup = None
    text = ""
    if bib_path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{bib_path.name}.{datetime.now().strftime('%Y%m%d%H%M%S%f')}.bak"
        shutil.copy2(bib_path, backup)
        text = bib_path.read_text(encoding="utf-8")
    else:
        bib_path.parent.mkdir(parents=True, exist_ok=True)
    if not text:
        separator = ""
    elif text.endswith("\n\n"):
        separator = ""
    elif text.endswith("\n"):
        separator = "\n"
    else:
        separator = "\n\n"
    bib_path.write_text(text + separator + "\n".join(entries), encoding="utf-8")
    return backup


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProposalError(f"无法读取记录文件：{path}") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProposalError(f"{Path(path).name} 第 {number} 行不是合法 JSON") from exc
        if isinstance(value, dict):
            rows.append(value)
    return rows


def run(project_root: Path, records_path: Path, task_root: Path, *, session: HttpSession | None = None, dry_run: bool = False) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    task = Path(task_root).expanduser().resolve()
    if not task.name.startswith("task-") or task.parent.name != ".bensz-api":
        raise ProposalError(f"--task-root 必须指向 .bensz-api/task-*/ 目录：{task}")
    records = _read_jsonl(records_path)
    tree = scan_latex_tree(root)
    if not tree.bib_files:
        raise ProposalError("main.tex 及其 \\input 文件中没有 \\bibliography，无法确定 .bib")
    target = tree.bib_files[0]
    outcomes, entries = resolve_records(records, session=session or requests.Session(),
                                        settings=Settings.from_config(load_config()), index=read_bib_index(tree.bib_files))
    out_dir, backup = task / "nsfc-proposal" / "output", None
    if not dry_run:
        backup = append_entries(target, entries, out_dir / "bib_backup")
        record_added(proposal_paths(root).ledger, tree.bib_files, records, outcomes)
        for outcome in outcomes:
            if outcome.status == "unresolved":
                append_under_heading(proposal_paths(root).leads, "## 未核实线索", f"- [unverified] {outcome.title or outcome.record_id}；原因：{outcome.reason}；记录：{outcome.record_id}")
    summary = {
        "bib_file": str(target),
        "backup": str(backup) if backup else None,
        "dry_run": dry_run,
        "counts": {status: sum(1 for o in outcomes if o.status == status) for status in ("added", "exists", "unresolved")},
        "outcomes": [asdict(o) for o in outcomes],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bib_resolve.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bib_resolve.py", description="补全文献元数据并追加到项目 .bib")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--records", required=True, help="rls.paper.v1 JSONL：选作证据的文献记录")
    parser.add_argument("--task-root", required=True, help="本任务的 .bensz-api/task-*/ 目录")
    parser.add_argument("--dry-run", action="store_true", help="只查询与汇总，不写 .bib 和线索文件")
    args = parser.parse_args(argv)
    try:
        summary = run(Path(args.project_root), Path(args.records), Path(args.task_root), dry_run=args.dry_run)
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
