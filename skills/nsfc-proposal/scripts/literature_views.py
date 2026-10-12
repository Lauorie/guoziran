"""文献池的三种视图：阅读表（digest）、论断选文（select）、按论断汇总证据（evidence）。不联网。"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from citation_ledger import load_ledger
from literature_records import read_jsonl, write_json, write_jsonl
from proposal_common import ProposalError, proposal_paths, resolve_project_root

OUTPUT_DIR = "nsfc-proposal/output"
LITERATURE_DIR = f"{OUTPUT_DIR}/literature"
NO_QUERY = "（无检索式）"
TITLE_CHARS, VENUE_CHARS, NEAREST = 160, 50, 3


def _segment(value: str) -> str:
    text = str(value or "").strip()
    if not text or "/" in text or "\\" in text or ".." in text:
        raise ProposalError(f"--name 须为单个名称，不能含 / 、\\ 或 ..：{value!r}")
    return text


def _output(task_root: Path) -> Path:
    return resolve_project_root(task_root) / OUTPUT_DIR


def _clip(text: Any, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _norm(text: Any) -> str:
    return " ".join(str(text or "").lower().split())


def _doi(record: Mapping[str, Any]) -> str:
    ids = record.get("identifiers") if isinstance(record.get("identifiers"), Mapping) else {}
    return str(ids.get("doi") or record.get("doi") or "")


def _provenance(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("provenance")
    return value if isinstance(value, Mapping) else {}


def _abstract_state(record: Mapping[str, Any]) -> str:
    abstract = record.get("abstract")
    if record.get("abstract_status") == "present" and isinstance(abstract, str) and abstract.strip():
        return "完整"
    return "片段" if _provenance(record).get("host_abstract_snippet") else "无"


def _read_pool(path: Path) -> list[dict[str, Any]]:
    try:
        return read_jsonl(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProposalError(f"读不了候选文件 {path.parent.name}/{path.name}：{exc}") from exc


# ---------------------------------------------------------------- digest

def _digest_line(record: Mapping[str, Any]) -> str:
    year = record.get("year")
    return " | ".join([
        str(record.get("record_id") or ""), str(year if year else ""), _clip(record.get("title"), TITLE_CHARS),
        _clip(record.get("venue"), VENUE_CHARS), _doi(record), str(_provenance(record).get("host_relevance") or ""),
        f"摘要：{_abstract_state(record)}"])


def build_digest(task_root: Path, name: str) -> Path:
    """按第一条检索式分组写 digest.md，返回路径。"""
    pool_dir = _output(task_root) / "literature" / _segment(name)
    source = pool_dir / "candidates.jsonl"
    if not source.is_file():
        raise ProposalError(f"找不到候选文件：{LITERATURE_DIR}/{name}/candidates.jsonl（先跑 literature.py pool）")
    records = _read_pool(source)
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        matches = record.get("query_matches")
        first = str(matches[0]) if isinstance(matches, list) and matches and matches[0] else NO_QUERY
        groups.setdefault(first, []).append(record)
    lines = [f"# 文献池阅读表：{name}", "", f"共 {len(records)} 篇，{len(groups)} 组检索式：", ""]
    lines += [f"- {query}：{len(items)} 篇" for query, items in groups.items()]
    for query, items in groups.items():
        lines += ["", f"## {query}（{len(items)} 篇）", "",
                  "record_id | 年份 | 题名 | 期刊或会议 | doi | wispaper 相关度 | 摘要", ""]
        lines += [_digest_line(item) for item in items]
    target = pool_dir / "digest.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


# ---------------------------------------------------------------- select

def _all_candidates(task_root: Path) -> list[dict[str, Any]]:
    base = _output(task_root) / "literature"
    files = sorted(base.glob("*/candidates.jsonl")) if base.is_dir() else []
    if not files:
        raise ProposalError(f"找不到候选池：{LITERATURE_DIR}/*/candidates.jsonl")
    return [row for path in files for row in _read_pool(path)]


def _load_map(path: Path) -> dict[str, list[str]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProposalError(f"读不了论断映射文件 {Path(path).name}：{exc}") from exc
    if not isinstance(data, dict) or not data:
        raise ProposalError("论断映射须是非空对象：{论断编号: [引用, ...]}")
    for claim, refs in data.items():
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref.strip() for ref in refs):
            raise ProposalError(f"论断 {claim} 的引用须是字符串列表")
    return {str(claim): list(refs) for claim, refs in data.items()}


def _find(ref: str, candidates: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """record_id 精确匹配优先；否则题名前缀匹配。同一 record_id 在多个池里只算一篇。"""
    by_id = [c for c in candidates if c.get("record_id") == ref.strip()]
    hits = by_id or [c for c in candidates if _norm(c.get("title")).startswith(_norm(ref))]
    unique: dict[str, dict[str, Any]] = {}
    for hit in hits:
        unique.setdefault(str(hit.get("record_id")), hit)
    return list(unique.values())


def _nearest(ref: str, candidates: Sequence[dict[str, Any]]) -> list[str]:
    titles = list(dict.fromkeys(str(c.get("title") or "") for c in candidates))
    key = _norm(ref)
    scored = sorted(titles, key=lambda t: -difflib.SequenceMatcher(None, key, _norm(t)[: len(key) + 20]).ratio())
    return [_clip(t, TITLE_CHARS) for t in scored[:NEAREST]]


def select_for_claims(task_root: Path, map_path: Path) -> tuple[list[str], int]:
    """全部唯一匹配才写 selected.jsonl 与 selected_claim_map.json。返回（问题列表, 选中篇数）。"""
    claims = _load_map(map_path)
    candidates = _all_candidates(task_root)
    problems: list[str] = []
    chosen: dict[str, dict[str, Any]] = {}
    claim_map: dict[str, list[str]] = {}
    for claim, refs in claims.items():
        for ref in refs:
            hits = _find(ref, candidates)
            if len(hits) == 1:
                record = hits[0]
                chosen.setdefault(str(record["record_id"]), record)
                ids = claim_map.setdefault(claim, [])
                if record["record_id"] not in ids:
                    ids.append(str(record["record_id"]))
            elif not hits:
                near = "；".join(_nearest(ref, candidates))
                problems.append(f"论断 {claim}：「{ref}」没有匹配的记录。最接近的题名：{near}")
            else:
                listed = "；".join(f"{h['record_id']}（{_clip(h.get('title'), 60)}）" for h in hits)
                problems.append(f"论断 {claim}：「{ref}」匹配到 {len(hits)} 篇：{listed}。请改写成更长的题名开头或 record_id")
        claim_map.setdefault(claim, [])
    if problems:
        return problems, 0
    out = _output(task_root)
    write_jsonl(out / "selected.jsonl", chosen.values())
    write_json(out / "selected_claim_map.json", claim_map)
    return [], len(chosen)


# ---------------------------------------------------------------- evidence

def _read_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise ProposalError(f"缺少 {label}：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProposalError(f"读不了 {label}：{exc}") from exc


def build_evidence(task_root: Path, project_root: Path) -> Path:
    """每条论断下列出可引用文献及台账摘要，写 evidence_by_claim.md。"""
    out = _output(task_root)
    claim_map = _read_json(out / "selected_claim_map.json", "selected_claim_map.json（先跑 literature.py select）")
    resolved = _read_json(out / "bib_resolve.json", "bib_resolve.json（先跑 bib_resolve.py）")
    if not isinstance(claim_map, dict) or not isinstance(resolved, dict):
        raise ProposalError("selected_claim_map.json 或 bib_resolve.json 格式不对")
    selected = out / "selected.jsonl"
    records = {str(r.get("record_id")): r for r in read_jsonl(selected)} if selected.is_file() else {}
    outcomes = {str(o.get("record_id")): o for o in resolved.get("outcomes", []) if isinstance(o, dict)}
    ledger = load_ledger(proposal_paths(resolve_project_root(project_root)).ledger)
    sections: list[str] = []
    for claim, ids in claim_map.items():
        blocks: list[str] = []
        usable = 0
        for rid in ids:
            outcome, record = outcomes.get(rid, {}), records.get(rid, {})
            title = outcome.get("title") or record.get("title") or rid
            year = record.get("year") or ""
            key = outcome.get("bibkey")
            if outcome.get("status") in ("added", "exists") and key and key in ledger:
                usable += 1
                abstract = ledger[key].get("abstract")
                head = f"- {key}"
                body = abstract.strip() if isinstance(abstract, str) and abstract.strip() else "（无摘要）"
            else:
                status = outcome.get("status") or "未处理"
                reason = outcome.get("reason") or ("不在台账中" if key else "无原因记录")
                head, body = f"- 未入库：{status}，{reason}", ""
            blocks.append("\n".join(x for x in (head, f"  题名：{title}（{year}）" if year else f"  题名：{title}",
                                                f"  摘要：{body}" if body else "") if x))
        sections.append(f"## {claim}\n\n可引用 {usable} 篇（共选 {len(ids)} 篇）。\n\n" + "\n\n".join(blocks))
    target = out / "evidence_by_claim.md"
    target.write_text("# 按论断汇总的证据\n\n" + "\n\n".join(sections) + "\n", encoding="utf-8")
    return target
