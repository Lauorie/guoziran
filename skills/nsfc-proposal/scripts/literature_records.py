"""文献记录：wispaper 宿主结果适配、rls.paper.v1 规范化、去重。

只处理 wispaper 的检索结果；记录字段（identifiers.doi、title、year、record_id、abstract 等）
按 rls.paper.v1 产出，供 bib_resolve.py 与 citation_ledger.py 读取。本模块不联网。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Mapping

HOST_SCHEMA = "rls.host_results.v1"
SCHEMA_VERSION = "rls.paper.v1"
PROVIDER = "wispaper"
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
DOI_IN_URL_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>?#]+", re.IGNORECASE)
DOI_URL_SUFFIXES = ("/full", "/abstract", "/epdf", "/pdf", ".pdf", "/fulltext", "/html")
ELLIPSES = ("…", "...")
IDENTIFIER_KEYS = ("doi", "pmid", "arxiv")
ABSTRACT_STATUSES = {"present", "missing", "attempted", "not_requested"}
STOPWORDS = {"a", "an", "the", "and", "or", "of", "for", "in", "on", "to", "with", "from", "by", "via"}


# ---------------------------------------------------------------- 基础工具

def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    raw = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", raw, flags=re.I)
    raw = re.sub(r"^doi:\s*", "", raw, flags=re.I).strip().rstrip(".,;)")
    return raw.lower() if raw else None


def normalize_year(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1000 <= value <= 3000 else None
    match = re.search(r"\b(1[0-9]{3}|2[0-9]{3}|3000)\b", str(value))
    return int(match.group(0)) if match else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
                      encoding="utf-8")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- wispaper 适配

def doi_from_urls(*urls: object) -> str | None:
    """从出版社链接中提取 DOI，去掉 /full、/abstract 等页面尾缀并转小写。"""
    for url in urls:
        if not isinstance(url, str):
            continue
        match = DOI_IN_URL_RE.search(url)
        if not match:
            continue
        doi = match.group(0).rstrip(".,;)").lower()
        stripped = True
        while stripped:
            stripped = False
            for suffix in DOI_URL_SUFFIXES:
                if doi.endswith(suffix):
                    doi = doi[: -len(suffix)]
                    stripped = True
        return doi
    return None


def _is_fragment(text: str) -> bool:
    text = text.strip()
    return text.startswith(ELLIPSES) or text.endswith(ELLIPSES)


def adapt_wispaper(paper: Mapping[str, Any]) -> dict[str, Any]:
    """把一篇 wispaper 论文转成原始记录；以省略号开头或结尾的摘要是片段，不当摘要。"""
    warnings: list[str] = []
    provenance: dict[str, Any] = {"host_tool": PROVIDER}
    title = str(paper.get("title") or "").strip()
    if title and _is_fragment(title):
        warnings.append("title_truncated")
    abstract = paper.get("abstract") if isinstance(paper.get("abstract"), str) else None
    if abstract and _is_fragment(abstract):
        provenance["host_abstract_snippet"] = abstract.strip()
        abstract = None
        warnings.append("abstract_snippet_only")
    flags = paper.get("flags") if isinstance(paper.get("flags"), Mapping) else {}
    if flags:
        provenance["host_relevance"] = "perfect" if flags.get("perfect") else ("partial" if flags.get("partial") else "none")
    doi = paper.get("doi") or doi_from_urls(paper.get("url"), paper.get("source_url"), paper.get("pdf_url"))
    url = paper.get("url") or paper.get("source_url")
    return {
        "id": paper.get("paper_id") or doi or url,
        "title": title,
        "authors": [a for a in (paper.get("authors") or []) if isinstance(a, str)],
        "doi": doi,
        "arxiv": paper.get("arxiv_id"),
        "year": paper.get("year"),
        "venue": paper.get("venue"),
        "url": url,
        "abstract": abstract,
        "quality_warnings": warnings,
        "provenance": provenance,
    }


def load_host_results(path: Path) -> dict[str, list[dict[str, Any]]]:
    """读取 rls.host_results.v1 文件，返回 {检索式原文: [原始记录]}；格式不对抛 ValueError（中文信息）。"""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"读不了（{type(exc).__name__}）") from exc
    if not isinstance(payload, dict) or payload.get("schema") != HOST_SCHEMA:
        raise ValueError(f"schema 须为 {HOST_SCHEMA}")
    if payload.get("provider") != PROVIDER:
        raise ValueError(f"provider 须为 {PROVIDER}")
    entries = payload.get("queries")
    if not isinstance(entries, list):
        raise ValueError("queries 须为数组")
    results: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or not isinstance(entry.get("query"), str) or not entry["query"].strip():
            raise ValueError(f"第 {index} 条检索式缺 query")
        papers = entry.get("papers")
        if not isinstance(papers, list):
            raise ValueError(f"第 {index} 条检索式的 papers 须为数组")
        results.setdefault(entry["query"].strip(), []).extend(adapt_wispaper(p) for p in papers if isinstance(p, dict))
    return results


# ---------------------------------------------------------------- rls.paper.v1 规范化

def stable_record_id(record: Mapping[str, Any], *, fallback_index: int = 0) -> str:
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), dict) else {}
    doi = normalize_doi(identifiers.get("doi") or record.get("doi"))
    if doi:
        return f"doi:{doi}"
    for key in ("pmid", "arxiv"):
        value = _text(identifiers.get(key) or record.get(key))
        if value:
            return f"{key}:{value.lower()}"
    title = re.sub(r"\s+", " ", str(record.get("title") or "").strip().lower())
    payload = f"{title}|{normalize_year(record.get('year')) or ''}|{fallback_index}".encode("utf-8")
    return "title:" + hashlib.sha256(payload).hexdigest()[:24]


def _authors(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def normalize_record(raw: Mapping[str, Any], *, query_id: str | None = None, rank: int | None = None,
                     fallback_index: int = 0) -> dict[str, Any]:
    """把 adapt_wispaper 的输出转成 rls.paper.v1 记录。标题为空时抛 ValueError。"""
    if not isinstance(raw, Mapping):
        raise ValueError("候选记录不是对象")
    identifiers: dict[str, str | None] = {key: _text(raw.get(key)) for key in IDENTIFIER_KEYS}
    identifiers["doi"] = normalize_doi(identifiers["doi"])
    title = _text(raw.get("title"))
    if not title:
        raise ValueError("候选记录标题为空")
    abstract = _text(raw.get("abstract"))
    venue = _text(raw.get("venue"))
    probe = f"{venue or ''} {raw.get('url') or ''}".lower()
    is_preprint = any(token in probe for token in ("arxiv", "biorxiv", "medrxiv", "preprint"))
    provider_id = raw.get("id")
    sources = [{
        "provider": PROVIDER,
        "provider_record_id": str(provider_id) if provider_id else None,
        "first_seen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query_id": query_id,
        "rank": rank,
        "url": raw.get("url"),
    }]
    warnings = [str(item) for item in (raw.get("quality_warnings") or []) if str(item).strip()]
    if identifiers["doi"] and not DOI_RE.match(identifiers["doi"]):
        warnings.append("invalid_doi_discarded")
        identifiers["doi"] = None
    if not venue:
        warnings.append("missing_venue")
    if not abstract and "missing_abstract" not in warnings:
        warnings.append("missing_abstract")
    record: dict[str, Any] = {
        "record_type": "paper",
        "schema_version": SCHEMA_VERSION,
        "record_id": "",
        "title": title,
        "authors": _authors(raw.get("authors")),
        "identifiers": identifiers,
        "venue": venue,
        "year": normalize_year(raw.get("year")),
        "url": _text(raw.get("url")),
        "abstract": abstract,
        "abstract_status": "present" if abstract else "missing",
        "abstract_provenance": None,
        "publication": {"is_preprint": is_preprint, "language": None, "is_open_access": None},
        "sources": sources,
        "provenance": raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {},
        "query_matches": [query_id] if query_id else [],
        "quality_warnings": sorted(set(warnings)),
    }
    record["record_id"] = stable_record_id(record, fallback_index=fallback_index)
    record.update({"doi": identifiers["doi"], "pmid": identifiers["pmid"], "arxiv_id": identifiers["arxiv"],
                   "source": PROVIDER, "language": None, "is_open_access": None})
    return record


def validate_candidate(record: Any) -> list[str]:
    """检查一条 rls.paper.v1 记录的必要字段；返回错误列表。"""
    if not isinstance(record, dict):
        return ["记录不是对象"]
    errors: list[str] = []
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 须为 {SCHEMA_VERSION}")
    if not isinstance(record.get("record_id"), str) or not record["record_id"].strip():
        errors.append("record_id 为空")
    if not isinstance(record.get("title"), str) or not record["title"].strip():
        errors.append("title 为空")
    identifiers = record.get("identifiers")
    if not isinstance(identifiers, dict):
        errors.append("identifiers 须为对象")
    else:
        doi = identifiers.get("doi")
        if doi is not None and (not isinstance(doi, str) or not DOI_RE.match(doi)):
            errors.append("identifiers.doi 不合法")
    year = record.get("year")
    if year is not None and (not isinstance(year, int) or not 1000 <= year <= 3000):
        errors.append("year 须为空或 1000 到 3000 的整数")
    if record.get("abstract_status") not in ABSTRACT_STATUSES:
        errors.append("abstract_status 不合法")
    return errors


# ---------------------------------------------------------------- 去重

def normalize_title(title: Any) -> str:
    text = re.sub(r"[　\s]+", " ", str(title or "").strip().lower())
    text = re.sub(r"[\"'“”‘’]", "", text)
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"[-_]+", " ", text)
    return " ".join(token for token in re.sub(r"\s+", " ", text).strip().split() if token not in STOPWORDS)


def token_jaccard(left: str, right: str) -> float:
    a, b = set(left.split()), set(right.split())
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_preprint(record: Mapping[str, Any]) -> bool:
    pub = record.get("publication") if isinstance(record.get("publication"), dict) else {}
    if pub.get("is_preprint") is True:
        return True
    probe = f"{record.get('venue') or ''} {record.get('url') or ''}".lower()
    return any(token in probe for token in ("arxiv", "biorxiv", "medrxiv", "preprint"))


def _doi_of(record: Mapping[str, Any]) -> str | None:
    return normalize_doi(record.get("doi") or (record.get("identifiers") or {}).get("doi"))


def quality_score(record: Mapping[str, Any]) -> int:
    score = 0
    if _doi_of(record):
        score += 10
    if not is_preprint(record):
        score += 4
    if record.get("venue"):
        score += 2
    if normalize_year(record.get("year")):
        score += 1
    if isinstance(record.get("abstract"), str):
        score += min(2, len(record["abstract"]) // 400)
    return score


def merge_records(canonical: Mapping[str, Any], other: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(canonical)
    for key in ("title", "venue", "year", "url", "abstract"):
        if merged.get(key) in (None, "", []) and other.get(key) not in (None, "", []):
            merged[key] = other[key]
    if not merged.get("authors") and other.get("authors"):
        merged["authors"] = list(other["authors"])
    left_ids = canonical.get("identifiers") if isinstance(canonical.get("identifiers"), dict) else {}
    right_ids = other.get("identifiers") if isinstance(other.get("identifiers"), dict) else {}
    identifiers = {key: (left_ids.get(key) or right_ids.get(key)) for key in IDENTIFIER_KEYS}
    identifiers["doi"] = normalize_doi(identifiers.get("doi"))
    merged["identifiers"] = identifiers
    merged["sources"] = list({json.dumps(item, ensure_ascii=False, sort_keys=True): item
                              for item in [*(merged.get("sources") or []), *(other.get("sources") or [])]}.values())
    merged["query_matches"] = sorted(set(merged.get("query_matches") or []) | set(other.get("query_matches") or []))
    merged["quality_warnings"] = sorted(set(merged.get("quality_warnings") or []) | set(other.get("quality_warnings") or []))
    merged["record_id"] = canonical.get("record_id") or other.get("record_id")
    merged["doi"] = identifiers["doi"]
    merged["pmid"] = identifiers.get("pmid") or merged.get("pmid")
    merged["arxiv_id"] = identifiers.get("arxiv") or merged.get("arxiv_id")
    return merged


def dedupe_records(records: list[dict[str, Any]], *, title_similarity: float = .92, token_threshold: float = .80,
                   year_window: int = 1) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """先按 DOI，再按规范化标题加年份窗口去重；返回（保留的记录，合并边）。顺序稳定。"""
    canonical: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    doi_index: dict[str, int] = {}
    for source_index, record in enumerate(records):
        title = normalize_title(record.get("title"))
        year = normalize_year(record.get("year"))
        doi = _doi_of(record)
        match_index: int | None = doi_index.get(doi) if doi else None
        best: tuple[float, float, int, str] | None = None
        reason = ""
        if match_index is None and title:
            for index, existing in enumerate(canonical):
                existing_title = normalize_title(existing.get("title"))
                existing_year = normalize_year(existing.get("year"))
                if year is not None and existing_year is not None and abs(year - existing_year) > year_window:
                    continue
                similarity = SequenceMatcher(None, title, existing_title).ratio()
                jaccard = token_jaccard(title, existing_title)
                existing_doi = _doi_of(existing)
                cross_version = bool((doi and not existing_doi and is_preprint(existing))
                                     or (existing_doi and not doi and is_preprint(record)))
                cross_doi = bool(doi and existing_doi and doi != existing_doi)
                if (cross_doi or cross_version) and not (is_preprint(record) or is_preprint(existing)):
                    continue
                required = .97 if (cross_doi or cross_version) else title_similarity
                if similarity >= required and jaccard >= token_threshold:
                    candidate = (similarity, jaccard, index,
                                 "cross_doi_preprint_to_published" if (cross_doi or cross_version) else "fuzzy_title_year")
                    if best is None or candidate[:2] > best[:2]:
                        best = candidate
            if best is not None:
                _, _, match_index, reason = best
        if match_index is None:
            match_index = len(canonical)
            canonical.append(record)
            if doi:
                doi_index[doi] = match_index
            continue
        existing = canonical[match_index]
        existing_id, incoming_id = existing.get("record_id"), record.get("record_id")
        incoming_wins = quality_score(record) > quality_score(existing)
        same_doi = bool(doi and _doi_of(existing) == doi)
        if incoming_wins:
            canonical[match_index] = merge_records(record, existing)
            canonical[match_index]["record_id"] = incoming_id or existing_id
        else:
            canonical[match_index] = merge_records(existing, record)
        chosen = canonical[match_index]
        chosen_doi = _doi_of(chosen)
        if chosen_doi:
            doi_index[chosen_doi] = match_index
        edges.append({
            "canonical_record_id": chosen.get("record_id"),
            "merged_record_id": existing_id if incoming_wins else incoming_id,
            "reason": "same_doi" if same_doi else (reason or "fuzzy_title_year"),
            "source_index": source_index,
            "similarity": 1.0 if same_doi else (best[0] if best else 0.0),
            "jaccard": 1.0 if same_doi else (best[1] if best else 0.0),
        })
    return canonical, edges
