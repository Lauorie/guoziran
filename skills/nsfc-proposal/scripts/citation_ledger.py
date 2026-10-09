#!/usr/bin/env python3
"""引用台账：proposal/citation_ledger.jsonl，只追加的 JSONL 事件日志。

每条进入 .bib 的文献留一条记录：来自哪条检索记录、元数据出自 CrossRef 还是 OpenAlex、
写入 .bib 的条目文本哈希、可用的摘要原文。一致性检查据此拒绝手写或手改的条目。
事件：add（bib_resolve 写入）、register_user（申请人原有条目）、drop（作废）。不做 revise：
要改一条文献，先 drop，再用 bib_resolve 重新解析。
退出码：0 正常；1 audit 发现问题；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from latex_files import DOI_FIELD_RE, bib_entry_texts, normalize_doi, scan_latex_tree
from proposal_common import ProposalError, proposal_paths, resolve_project_root

EVENTS = ("add", "register_user", "drop")


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


def add_event(bibkey: str, *, source: str, entry_text: str, doi: str | None, abstract: str | None,
              provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {"event": "add", "bibkey": bibkey, "time": now_iso(), "source": source, "doi": doi,
            "entry_sha256": entry_sha256(entry_text), "abstract": abstract, "provenance": dict(provenance), "reason": None}


def register_user_entries(project_root: Path, bib_files: list[Path] | None = None) -> list[str]:
    """把 .bib 中尚未在台账里的条目登记为 register_user；返回新登记的 bibkey。已 drop 的条目不重新登记。"""
    root = resolve_project_root(project_root)
    ledger_path = proposal_paths(root).ledger
    files = scan_latex_tree(root).bib_files if bib_files is None else bib_files
    known = set(load_ledger(ledger_path)) | dropped_keys(ledger_path)
    registered: list[str] = []
    for key, text in bib_entry_texts(files).items():
        if key in known:
            continue
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
    for name, help_text in (("register-user", "把 .bib 中尚未入账的条目登记为申请人提供"), ("show", "列出有效条目"),
                            ("audit", "对照 .bib 与台账")):
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
            keys = register_user_entries(root)
            print(f"登记 {len(keys)} 条：{'、'.join(keys) if keys else '无'}")
        elif args.command == "drop":
            if args.key not in load_ledger(ledger_path):
                raise ProposalError(f"台账中没有有效记录：{args.key}")
            append_event(ledger_path, {"event": "drop", "bibkey": args.key, "time": now_iso(), "reason": args.reason})
            print(f"已作废：{args.key}")
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
