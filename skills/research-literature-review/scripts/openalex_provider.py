"""OpenAlex adapter owned by research-literature-review.

``search`` returns records in generic fields so that research-literature-search
does not need to know the OpenAlex response format.
"""

from __future__ import annotations

from typing import Any

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
DOI_PREFIX = "https://doi.org/"


def _abstract_from_inverted_index(index: Any) -> str:
    """Rebuild an abstract from an OpenAlex word -> positions index; return "" if unusable."""
    if not isinstance(index, dict):
        return ""
    terms: list[tuple[int, str]] = []
    for token, positions in index.items():
        if isinstance(positions, list):
            terms.extend((pos, str(token)) for pos in positions if isinstance(pos, int) and not isinstance(pos, bool))
    return " ".join(token for _, token in sorted(terms))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_raw(work: dict[str, Any]) -> dict[str, Any]:
    """Convert one OpenAlex work to the generic candidate fields."""
    doi = _text(work.get("doi"))
    if doi and doi.lower().startswith(DOI_PREFIX):
        doi = doi[len(DOI_PREFIX):]
    primary = work.get("primary_location") if isinstance(work.get("primary_location"), dict) else {}
    source = primary.get("source") if isinstance(primary.get("source"), dict) else {}
    open_access = work.get("open_access") if isinstance(work.get("open_access"), dict) else {}
    authors = []
    for item in work.get("authorships") or []:
        author = item.get("author") if isinstance(item, dict) and isinstance(item.get("author"), dict) else {}
        name = _text(author.get("display_name"))
        if name:
            authors.append(name)
    return {
        "id": work.get("id"),
        "title": work.get("title") or work.get("display_name"),
        "authors": authors,
        "doi": doi,
        "year": work.get("publication_year"),
        "venue": source.get("display_name"),
        "abstract": _abstract_from_inverted_index(work.get("abstract_inverted_index")) or None,
        "url": (DOI_PREFIX + doi) if doi else primary.get("landing_page_url"),
        "is_open_access": open_access.get("is_oa"),
        "type": work.get("type"),
    }


def search(query: str, *, max_results: int = 50, min_year: int | None = None, max_year: int | None = None, mailto: str | None = None, timeout: float = 30, session: Any = None, **_: Any) -> list[dict[str, Any]]:
    import requests

    params: dict[str, Any] = {"search": query, "per-page": max(1, min(int(max_results), 200))}
    filters: list[str] = []
    if min_year is not None:
        filters.append(f"from_publication_date:{int(min_year)}-01-01")
    if max_year is not None:
        filters.append(f"to_publication_date:{int(max_year)}-12-31")
    if filters:
        params["filter"] = ",".join(filters)
    if mailto:
        params["mailto"] = mailto
    client = session or requests
    response = client.get(OPENALEX_WORKS_URL, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    works = list(data.get("results") or [])[: int(max_results)]
    return [_to_raw(work) for work in works if isinstance(work, dict)]
