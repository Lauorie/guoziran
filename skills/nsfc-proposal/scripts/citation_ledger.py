#!/usr/bin/env python3
"""引用台账：proposal/citation_ledger.jsonl，只追加的 JSONL 事件日志。

每条进入 .bib 的文献留一条记录：来自哪条检索记录、元数据出自哪个服务（现只用 CrossRef；旧台账中其他来源的记录照常读取）、
写入 .bib 的条目文本哈希、可用的摘要原文。一致性检查据此拒绝手写或手改的条目。
事件：add（bib_resolve 写入；bib_refresh 按台账中的 DOI 重新取元数据、原 key 重写条目后再记一条，reason 为 refresh）、
register_user（申请人确认由其提供、用 register-user --key 登记的条目）、drop（作废）。case.py init 只建空台账，不登记任何条目。
条目文本只由脚本写，不接受手改。同一篇文献的条目有误时用 bib_refresh；要换成另一篇，先 drop，再用 bib_resolve 重新解析。
退出码：0 正常；1 audit 发现问题；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from latex_files import DOI_FIELD_RE, bib_entry_texts, normalize_doi, scan_latex_tree
from proposal_common import ProposalError, proposal_paths, resolve_project_root

EVENTS = ("add", "register_user", "drop")
MIN_ABSTRACT_CHARS = 80


def entry_sha256(text: str) -> str:
    """条目文本规范化后取 SHA-256：去首尾空白、每行去行尾空白、换行统一为 \\n。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized = "\n".join(line.rstrip() for line in lines).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_event(path: Path, event: Mapping[str, Any]) -> None:
    """向台账追加一行；文件和目录不存在时创建。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = False
    if target.is_file() and target.stat().st_size:
        with target.open("rb") as handle:
            handle.seek(-1, 2)
            needs_newline = handle.read(1) != b"\n"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(("\n" if needs_newline else "") + json.dumps(dict(event), ensure_ascii=False) + "\n")


def _read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProposalError(f"无法读取台账：{path}") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProposalError(f"{Path(path).name} 第 {number} 行不是合法 JSON") from exc
        if not isinstance(value, dict) or value.get("event") not in EVENTS or not isinstance(value.get("bibkey"), str) or not value["bibkey"]:
            raise ProposalError(f"{Path(path).name} 第 {number} 行不是合法台账事件（需要 event 与 bibkey）")
        events.append(value)
    return events


def load_ledger(path: Path) -> dict[str, dict[str, Any]]:
    """按 bibkey 返回当前有效的记录：最后一次 add/register_user 生效，之后的 drop 使其失效。"""
    if not Path(path).is_file():
        return {}
    current: dict[str, dict[str, Any]] = {}
    for event in _read_events(path):
        if event["event"] == "drop":
            current.pop(event["bibkey"], None)
        else:
            current[event["bibkey"]] = event
    return current


def dropped_keys(path: Path) -> set[str]:
    """最后一次事件是 drop 的 bibkey。"""
    if not Path(path).is_file():
        return set()
    last: dict[str, str] = {}
    for event in _read_events(path):
        last[event["bibkey"]] = event["event"]
    return {key for key, kind in last.items() if kind == "drop"}


def add_event(bibkey: str, *, source: str | None, entry_text: str, doi: str | None, abstract: str | None,
              provenance: Mapping[str, Any], reason: str | None = None) -> dict[str, Any]:
    return {"event": "add", "bibkey": bibkey, "time": now_iso(), "source": source, "doi": doi,
            "entry_sha256": entry_sha256(entry_text), "abstract": abstract, "provenance": dict(provenance), "reason": reason}


def _record_provenance(record: Mapping[str, Any], record_id: str) -> dict[str, Any]:
    provenance = record.get("provenance") if isinstance(record.get("provenance"), Mapping) else {}
    sources = record.get("sources") if isinstance(record.get("sources"), list) else []
    first = sources[0] if sources and isinstance(sources[0], Mapping) else {}
    matches = record.get("query_matches")
    return {"record_id": record_id, "record_title": record.get("title"),
            "query_matches": matches if isinstance(matches, list) else [],
            "host_tool": provenance.get("host_tool"), "provider": first.get("provider")}


def _record_abstract(record: Mapping[str, Any]) -> str | None:
    abstract = record.get("abstract")
    if record.get("abstract_status") == "present" and isinstance(abstract, str) and len(abstract.strip()) >= MIN_ABSTRACT_CHARS:
        return abstract.strip()
    return None


def _record_doi(record: Mapping[str, Any]) -> str | None:
    identifiers = record.get("identifiers") if isinstance(record.get("identifiers"), Mapping) else {}
    return normalize_doi(identifiers.get("doi") or record.get("doi"))


def record_added(ledger_path: Path, bib_files: list[Path], records: list[dict[str, Any]], outcomes: list[Any]) -> None:
    """给每个 status 为 added 的结果追加 add 事件；哈希取实际写入 .bib 的条目文本，来源缺失时记 null。

    记录的摘要只在写入 .bib 的就是这条记录时才记：解析出的 DOI 与记录 DOI 规范化后相同，或记录本来没有 DOI。
    记录 DOI 的标题核对失败、改按标题解析到另一篇时，摘要属于原 DOI 那一篇，台账记 null。
    """
    texts = bib_entry_texts(bib_files)
    for record, outcome in zip(records, outcomes):
        if outcome.status != "added" or outcome.bibkey not in texts:
            continue
        record_doi = _record_doi(record)
        same_work = record_doi is None or normalize_doi(outcome.doi) == record_doi
        append_event(ledger_path, add_event(
            outcome.bibkey, source=outcome.source, entry_text=texts[outcome.bibkey], doi=outcome.doi,
            abstract=_record_abstract(record) if same_work else None, provenance=_record_provenance(record, outcome.record_id)))


def register_user_entries(project_root: Path, keys: Sequence[str] | None = None, bib_files: list[Path] | None = None) -> list[str]:
    """把申请人确认的 .bib 条目登记为 register_user，返回新登记的 bibkey。

    keys 为 None 时登记 .bib 中全部未入账条目（CLI 的 --all），已 drop 的跳过。给出 keys 时只登记这些 key：
    有 key 不在 .bib 中或已作废时报 ProposalError，一条也不写；已有有效记录的 key 跳过。
    """
    root = resolve_project_root(project_root)
    ledger_path = proposal_paths(root).ledger
    files = scan_latex_tree(root).bib_files if bib_files is None else bib_files
    texts = bib_entry_texts(files)
    active, dropped = set(load_ledger(ledger_path)), dropped_keys(ledger_path)
    if keys is None:
        wanted = [key for key in texts if key not in dropped]
    else:
        wanted = list(dict.fromkeys(keys))
        absent = [key for key in wanted if key not in texts]
        if absent:
            raise ProposalError(f".bib 中没有这些条目：{'、'.join(absent)}")
        voided = [key for key in wanted if key in dropped]
        if voided:
            raise ProposalError(f"这些条目已作废，不能再登记：{'、'.join(voided)}；要恢复，先从 .bib 删去，再用 bib_resolve 重新解析")
    registered: list[str] = []
    for key in wanted:
        if key in active:
            continue
        text = texts[key]
        doi_match = DOI_FIELD_RE.search(text)
        append_event(ledger_path, {
            "event": "register_user", "bibkey": key, "time": now_iso(), "source": "user",
            "doi": normalize_doi(doi_match.group(1)) if doi_match else None,
            "entry_sha256": entry_sha256(text), "abstract": None, "provenance": None, "reason": None})
        registered.append(key)
    return registered


def audit(project_root: Path) -> tuple[list[str], list[str]]:
    """返回（.bib 中有、台账中无的 key，哈希不一致的 key）。"""
    root = resolve_project_root(project_root)
    ledger = load_ledger(proposal_paths(root).ledger)
    missing: list[str] = []
    modified: list[str] = []
    for key, text in bib_entry_texts(scan_latex_tree(root).bib_files).items():
        if key not in ledger:
            missing.append(key)
        elif ledger[key].get("entry_sha256") != entry_sha256(text):
            modified.append(key)
    return missing, modified


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citation_ledger.py", description="引用台账：登记、作废、查看、审计")
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("register-user", help="把申请人确认由其提供的 .bib 条目登记入账")
    register.add_argument("--project-root", required=True)
    which = register.add_mutually_exclusive_group(required=True)
    which.add_argument("--key", action="append", help="要登记的 bibkey；可重复。key 不在 .bib 中或已作废时退出 2")
    which.add_argument("--all", action="store_true", help="登记 .bib 中全部未入账条目（已作废的除外）")
    for name, help_text in (("show", "列出有效条目"), ("audit", "对照 .bib 与台账")):
        sub.add_parser(name, help=help_text).add_argument("--project-root", required=True)
    drop = sub.add_parser("drop", help="作废一条记录")
    drop.add_argument("--project-root", required=True)
    drop.add_argument("--key", required=True)
    drop.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    try:
        root = resolve_project_root(Path(args.project_root))
        ledger_path = proposal_paths(root).ledger
        if args.command == "register-user":
            keys = register_user_entries(root, None if args.all else args.key)
            print(f"登记 {len(keys)} 条：{'、'.join(keys) if keys else '无'}")
        elif args.command == "drop":
            if args.key not in load_ledger(ledger_path):
                raise ProposalError(f"台账中没有有效记录：{args.key}")
            append_event(ledger_path, {"event": "drop", "bibkey": args.key, "time": now_iso(), "reason": args.reason})
            print(f"已作废：{args.key}。下一步：从 .bib 中删除该条目，再重跑 bib_resolve 重新写入"
                  "（仍留在 .bib 中的 key 会被 bib_resolve 判为 exists，不会重新入账）。")
        elif args.command == "show":
            for key, rec in load_ledger(ledger_path).items():
                print(f"{key}\t{rec.get('source')}\t{rec.get('doi') or '-'}\t{'有摘要' if rec.get('abstract') else '无摘要'}")
        else:
            missing, modified = audit(root)
            print(f"## .bib 中有、台账中无（{len(missing)}）")
            for key in missing:
                print(f"- {key}")
            print(f"## 条目文本与台账哈希不一致（{len(modified)}）")
            for key in modified:
                print(f"- {key}")
            return 1 if missing or modified else 0
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
