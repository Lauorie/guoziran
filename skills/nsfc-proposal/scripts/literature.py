#!/usr/bin/env python3
"""文献池：把 wispaper 的检索结果汇成候选池，并只用已有检索结果补摘要。不联网。

用法：
  literature.py pool --task-root T --name <名称> [--name ...] [--max-per-query N] [--out <池名>]
  literature.py abstract-queries --input <记录.jsonl> --output <检索式.json> [--reuse <上次输出>]
  literature.py enrich-abstracts --input <记录.jsonl> --output <输出.jsonl> [--host-results <host.json>] [--reuse <上次输出>]

退出码：0 完成（pool 为 success 或 partial_success）；1 pool 全部检索式都没有结果；2 参数或输入错误。
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from literature_records import (
    ELLIPSES, dedupe_records, load_host_results, normalize_doi, normalize_record, read_jsonl, validate_candidate,
    write_json, write_jsonl,
)
from proposal_common import ProposalError, resolve_project_root

POOL_SCHEMA = "nsfc-proposal.literature_pool.v1"
WISPAPER_DIR = "nsfc-proposal/output/wispaper"
LITERATURE_DIR = "nsfc-proposal/output/literature"
DEFAULT_MAX_PER_QUERY = 20
ABSTRACT_TITLE_SIMILARITY = 0.9
TRUNCATED_TITLE_MIN_CHARS = 30
EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


# ---------------------------------------------------------------- 路径

def _segment(value: str, label: str) -> str:
    """名称只能是单个路径段：不含 / 、\\ 、..，不为空。"""
    text = str(value or "").strip()
    if not text or "/" in text or "\\" in text or ".." in text or text in (".",):
        raise ProposalError(f"{label} 须为单个名称，不能含 / 、\\ 或 ..：{value!r}")
    return text


def _inside(base: Path, target: Path, label: str) -> Path:
    resolved = target.resolve()
    if resolved != base.resolve() and base.resolve() not in resolved.parents:
        raise ProposalError(f"{label} 越出 {base.name}/：{target.name}")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------- pool

def build_pool(task_root: Path, names: Sequence[str], *, max_per_query: int = DEFAULT_MAX_PER_QUERY,
               out: str | None = None) -> tuple[dict[str, Any], int]:
    """读 wispaper host 文件，写候选池目录。返回（manifest, 退出码）。输入错误抛 ProposalError。"""
    if not names:
        raise ProposalError("至少给一个 --name")
    if max_per_query < 1:
        raise ProposalError("--max-per-query 须为正整数")
    root = resolve_project_root(task_root)
    clean_names = [_segment(n, "--name") for n in dict.fromkeys(names)]
    pool_name = _segment(out if out is not None else clean_names[0], "--out")
    wispaper_dir = root / WISPAPER_DIR
    pool_dir = _inside(root / LITERATURE_DIR, root / LITERATURE_DIR / pool_name, "--out")

    hosts: list[dict[str, Any]] = []
    merged: dict[str, list[dict[str, Any]]] = {}
    for name in clean_names:
        path = _inside(wispaper_dir, wispaper_dir / f"{name}_host.json", "--name")
        if not path.is_file():
            raise ProposalError(f"找不到检索结果文件：{WISPAPER_DIR}/{name}_host.json（先跑 wispaper_search.py）")
        try:
            results = load_host_results(path)
        except ValueError as exc:
            raise ProposalError(f"{name}_host.json 不是可用的 wispaper 检索结果：{exc}") from exc
        hosts.append({"name": name, "file": f"{name}_host.json", "sha256": _sha256(path), "queries": len(results)})
        for query, papers in results.items():
            merged.setdefault(query, []).extend(papers)

    normalized: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []
    notes: list[str] = []
    failed_rows = 0
    for query, papers in merged.items():
        used = papers[:max_per_query]
        for rank, raw in enumerate(used, 1):
            try:
                record = normalize_record(raw, query_id=query, rank=rank, fallback_index=len(normalized) + 1)
            except ValueError as exc:
                failed_rows += 1
                notes.append(f"检索式「{query}」第 {rank} 篇无法入池：{exc}")
                continue
            errors = validate_candidate(record)
            if errors:
                failed_rows += 1
                notes.append(f"检索式「{query}」第 {rank} 篇无法入池：{'；'.join(errors)}")
                continue
            normalized.append(record)
        query_rows.append({"query": query, "papers": len(papers), "used": len(used)})
    canonical, edges = dedupe_records(normalized)

    empty = [row["query"] for row in query_rows if row["papers"] == 0]
    if not canonical:
        status = "failed"
        notes.append("所有检索式都没有可用的论文；候选文件为空。")
    elif empty:
        status = "partial_success"
        notes.append(f"有 {len(empty)} 条检索式没有结果，见 empty_queries。")
    else:
        status = "success"
    pool_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(pool_dir / "candidates.jsonl", canonical)
    manifest = {
        "schema": POOL_SCHEMA,
        "status": status,
        "pool": pool_name,
        "hosts": hosts,
        "max_per_query": max_per_query,
        "queries": query_rows,
        "empty_queries": empty,
        "counts": {"before_dedupe": len(normalized), "after_dedupe": len(canonical),
                   "merged": len(edges), "unusable": failed_rows},
        "notes": notes,
    }
    write_json(pool_dir / "manifest.json", manifest)
    return manifest, EXIT_FAILED if status == "failed" else EXIT_OK


# ---------------------------------------------------------------- 补摘要（只用本地已有结果）

def _title_key(value: Any) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", str(value or "").lower()).split())


def _strip_ellipses(text: str) -> str:
    text = " ".join(str(text or "").split())
    while text.endswith(ELLIPSES):
        text = text[:-1].rstrip() if text.endswith("…") else text[:-3].rstrip()
    while text.startswith(ELLIPSES):
        text = text[1:].lstrip() if text.startswith("…") else text[3:].lstrip()
    return text


def _hit_abstract(item: Mapping[str, Any]) -> str:
    text = item.get("abstract")
    return re.sub(r"\s+", " ", text).strip() if isinstance(text, str) else ""


def _same_paper(hit: Mapping[str, Any], *, title: str, doi: str | None) -> bool:
    """同 DOI，或（任一方没有 DOI 时）标题相似度够高。"""
    hit_doi = normalize_doi(hit.get("doi"))
    if doi and hit_doi:
        return hit_doi == doi
    hit_title, own_title = _title_key(hit.get("title")), _title_key(title)
    if not hit_title or not own_title:
        return False
    return difflib.SequenceMatcher(None, own_title, hit_title).ratio() >= ABSTRACT_TITLE_SIMILARITY


def _reusable_abstracts(path: Path, min_chars: int) -> dict[str, dict[str, Any]]:
    """前一次 enrich-abstracts 输出中已有足够长摘要的记录，按 record_id 索引；同一 id 取先出现的。"""
    found: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        record_id, abstract = row.get("record_id"), row.get("abstract")
        if (isinstance(record_id, str) and record_id and row.get("abstract_status") == "present"
                and isinstance(abstract, str) and len(abstract.strip()) >= min_chars):
            found.setdefault(record_id, row)
    return found


def _needs_abstract(row: Mapping[str, Any], min_chars: int) -> bool:
    abstract = row.get("abstract")
    return not (isinstance(abstract, str) and len(abstract.strip()) >= min_chars)


def _host_match(hit: Mapping[str, Any], *, title: str, doi: str | None) -> bool:
    """检索结果是否就是这条记录：DOI 都有时比 DOI；否则比标题，截断的标题按前缀比。"""
    if _same_paper(hit, title=title, doi=doi):
        return True
    if doi and normalize_doi(hit.get("doi")):
        return False
    own = _title_key(_strip_ellipses(title))
    truncated = str(title or "").strip().endswith(ELLIPSES)
    return truncated and len(own) >= TRUNCATED_TITLE_MIN_CHARS and _title_key(hit.get("title")).startswith(own)


def _host_candidates(host_results: Mapping[str, list[dict[str, Any]]], title: str) -> list[tuple[str, dict[str, Any]]]:
    """标题与检索式相同的那一组排在前面，其余按文件顺序。"""
    own = _title_key(_strip_ellipses(title))
    first = [(q, hit) for q, hits in host_results.items() if _title_key(q) == own for hit in hits]
    rest = [(q, hit) for q, hits in host_results.items() if _title_key(q) != own for hit in hits]
    return first + rest


def _fill_from_host(row: dict[str, Any], host_results: Mapping[str, list[dict[str, Any]]], min_chars: int,
                    name: str | None) -> None:
    """只用检索结果补一条记录的摘要；找不到则标 missing。"""
    title = str(row.get("title") or "")
    doi = normalize_doi(str(row.get("doi") or (row.get("identifiers") or {}).get("doi") or ""))
    rejected = 0
    provenance: dict[str, Any] = {"source": "wispaper", "method": "post_selection", "query": None,
                                  "host_results": name, "rejected_mismatch": 0}
    for query, hit in _host_candidates(host_results, title):
        candidate = _hit_abstract(hit)
        if len(candidate) < min_chars:
            continue
        if not _host_match(hit, title=title, doi=doi):
            rejected += 1
            continue
        row["abstract"] = candidate
        row["abstract_status"] = "present"
        row["abstract_provenance"] = {**provenance, "query": query, "rejected_mismatch": rejected}
        return
    row["abstract_status"] = "missing"
    row["abstract_provenance"] = {**provenance, "rejected_mismatch": rejected}
    row.setdefault("quality_warnings", [])
    if "missing_abstract" not in row["quality_warnings"]:
        row["quality_warnings"].append("missing_abstract")


def abstract_queries(input_path: Path, output_path: Path, *, max_papers: int = 200, min_chars: int = 80,
                     reuse_path: Path | None = None) -> dict[str, Any]:
    """列出缺完整摘要的记录标题（去重、去省略号），写成 {"queries": [...]}，供 wispaper 按标题检索。"""
    rows = read_jsonl(input_path)
    reusable = _reusable_abstracts(reuse_path, min_chars) if reuse_path is not None else {}
    queries: list[str] = []
    seen: set[str] = set()
    skipped_reusable = no_title = 0
    for row in rows[: max_papers if max_papers > 0 else len(rows)]:
        if not _needs_abstract(row, min_chars):
            continue
        if str(row.get("record_id") or "") in reusable:
            skipped_reusable += 1
            continue
        title = _strip_ellipses(row.get("title") or "")
        key = _title_key(title)
        if not key:
            no_title += 1
            continue
        if key not in seen:
            seen.add(key)
            queries.append(title)
    write_json(output_path, {"queries": queries})
    return {"queries": len(queries), "skipped_reusable": skipped_reusable, "no_title": no_title, "output": Path(output_path).name}


def enrich_abstracts(input_path: Path, output_path: Path, *, max_papers: int = 200, min_chars: int = 80,
                     reuse_path: Path | None = None, host_results: Mapping[str, list[dict[str, Any]]] | None = None,
                     host_results_name: str | None = None) -> dict[str, Any]:
    """补摘要：先沿用 --reuse 里已有的，再从 host 检索结果取；不发任何网络请求。"""
    rows = read_jsonl(input_path)
    reusable = _reusable_abstracts(reuse_path, min_chars) if reuse_path is not None else {}  # 输出被覆盖前先读
    output = [dict(row) for row in rows]
    attempted = filled = reused = 0
    for row in output[: max_papers if max_papers > 0 else len(output)]:
        if not _needs_abstract(row, min_chars):
            row["abstract_status"] = "present"
            continue
        prior = reusable.get(str(row.get("record_id") or ""))
        if prior is not None:
            previous = prior.get("abstract_provenance")
            row["abstract"] = prior["abstract"].strip()
            row["abstract_status"] = "present"
            row["abstract_provenance"] = {**(previous if isinstance(previous, dict) else {"method": "post_selection"}),
                                          "reused_from": Path(reuse_path).name}
            reused += 1
            continue
        attempted += 1
        row["abstract_status"] = "attempted"
        _fill_from_host(row, host_results or {}, min_chars, host_results_name)
        filled += row["abstract_status"] == "present"
    write_jsonl(output_path, output)
    summary = {"mode": "selected", "attempted": attempted, "filled": filled, "reused": reused,
               "missing": sum(1 for row in output if row.get("abstract_status") == "missing"),
               "min_abstract_chars": min_chars, "max_papers_total": max_papers,
               "host_results": host_results_name,
               "reuse_file": Path(reuse_path).name if reuse_path is not None else None}
    write_json(Path(output_path).with_suffix(Path(output_path).suffix + ".summary.json"), summary)
    return summary


# ---------------------------------------------------------------- 命令行

def _fail(message: str) -> int:
    print(f"✗ {message}", file=sys.stderr)
    return EXIT_USAGE


def _need_file(path: Path | None, label: str) -> str | None:
    if path is not None and not path.is_file():
        return f"{label} 文件不存在：{path}"
    return None


def _cmd_pool(args: argparse.Namespace) -> int:
    manifest, code = build_pool(args.task_root, args.name, max_per_query=args.max_per_query, out=args.out)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
    if code:
        print("✗ 所有检索式都没有结果，候选池为空。", file=sys.stderr)
    elif manifest["empty_queries"]:
        print(f"⚠ {len(manifest['empty_queries'])} 条检索式没有结果：" + "；".join(manifest["empty_queries"]), file=sys.stderr)
    return code


def _cmd_queries(args: argparse.Namespace) -> int:
    problem = _need_file(args.input, "--input") or _need_file(args.reuse, "--reuse")
    if problem:
        return _fail(problem)
    summary = abstract_queries(args.input, args.output, max_papers=args.max_papers, min_chars=args.min_abstract_chars,
                               reuse_path=args.reuse)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return EXIT_OK


def _cmd_enrich(args: argparse.Namespace) -> int:
    problem = _need_file(args.input, "--input") or _need_file(args.reuse, "--reuse") or _need_file(args.host_results, "--host-results")
    if problem:
        return _fail(problem)
    host = None
    if args.host_results is not None:
        try:
            host = load_host_results(args.host_results)
        except ValueError as exc:
            return _fail(f"--host-results 读不了：{exc}")
    summary = enrich_abstracts(args.input, args.output, max_papers=args.max_papers, min_chars=args.min_abstract_chars,
                               reuse_path=args.reuse, host_results=host,
                               host_results_name=args.host_results.name if args.host_results is not None else None)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="文献池：wispaper 结果汇总、去重、补摘要（不联网）")
    sub = parser.add_subparsers(dest="command", required=True)
    pool = sub.add_parser("pool", help="把 wispaper_search.py 写出的 <名称>_host.json 汇成候选池")
    pool.add_argument("--task-root", required=True, type=Path)
    pool.add_argument("--name", action="append", required=True, help="检索结果名称，可重复")
    pool.add_argument("--max-per-query", type=int, default=DEFAULT_MAX_PER_QUERY)
    pool.add_argument("--out", help="池名（单个路径段）；缺省取第一个 --name")
    queries = sub.add_parser("abstract-queries", help="列出缺完整摘要的记录标题，供 wispaper 按标题检索")
    queries.add_argument("--input", required=True, type=Path)
    queries.add_argument("--output", required=True, type=Path)
    queries.add_argument("--reuse", type=Path, help="前一次 enrich-abstracts 的输出：已补到摘要的记录不再列出")
    queries.add_argument("--max-papers", type=int, default=200)
    queries.add_argument("--min-abstract-chars", type=int, default=80)
    enrich = sub.add_parser("enrich-abstracts", help="只从 host 检索结果与 --reuse 补摘要，不联网")
    enrich.add_argument("--input", required=True, type=Path)
    enrich.add_argument("--output", required=True, type=Path)
    enrich.add_argument("--host-results", type=Path, help="rls.host_results.v1 文件（wispaper 按标题检索的结果）")
    enrich.add_argument("--reuse", type=Path, help="前一次的输出：同一 record_id 已补到的摘要直接沿用；可与 --output 相同")
    enrich.add_argument("--max-papers", type=int, default=200)
    enrich.add_argument("--min-abstract-chars", type=int, default=80)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "pool":
            return _cmd_pool(args)
        if args.command == "abstract-queries":
            return _cmd_queries(args)
        return _cmd_enrich(args)
    except ProposalError as exc:
        return _fail(str(exc))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _fail(f"读写失败（{type(exc).__name__}）：{exc}")


if __name__ == "__main__":
    raise SystemExit(main())
