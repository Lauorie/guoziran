"""宿主 MCP 检索结果到 provider 原始记录的适配（当前支持 wispaper）。

AI 通过 MCP 调用 wispaper，把原始返回按 rls.host_results.v1 保存；本模块把每篇论文
转成 normalize_record 能识别的原始字段，并标出摘要片段与截断标题。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

HOST_RESULTS_SCHEMA = "rls.host_results.v1"
SUPPORTED_HOST_PROVIDERS = {"wispaper"}
DOI_IN_URL_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>?#]+", re.IGNORECASE)
DOI_URL_SUFFIXES = ("/full", "/abstract", "/epdf", "/pdf", ".pdf", "/fulltext", "/html")
ELLIPSES = ("…", "...")


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
    """把一篇 wispaper 论文转成 provider 原始记录。"""
    warnings: list[str] = []
    provenance: dict[str, Any] = {"host_tool": "wispaper"}
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
    """读取 rls.host_results.v1 文件，返回 {检索式原文: [原始记录]}。"""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"host results unreadable: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != HOST_RESULTS_SCHEMA:
        raise ValueError(f"host results schema must be {HOST_RESULTS_SCHEMA}")
    provider = payload.get("provider")
    if provider not in SUPPORTED_HOST_PROVIDERS:
        raise ValueError(f"unsupported host provider: {provider}")
    entries = payload.get("queries")
    if not isinstance(entries, list):
        raise ValueError("host results queries must be a list")
    results: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or not isinstance(entry.get("query"), str) or not entry["query"].strip():
            raise ValueError(f"host results entry {index} needs a non-empty query")
        papers = entry.get("papers")
        if not isinstance(papers, list):
            raise ValueError(f"host results entry {index} papers must be a list")
        adapted = [adapt_wispaper(p) for p in papers if isinstance(p, dict)]
        results.setdefault(entry["query"].strip(), []).extend(adapted)
    return results
