#!/usr/bin/env python3
"""按引用台账中的 DOI 重新取 CrossRef 元数据，用原 key 重写 .bib 条目，并在台账追加 add 事件（reason 为 refresh）。

用途：旧版 bib_resolve 写入的条目有缺陷（如期刊名中的 &amp;），或条目需要按来源更新。条目文本只来自检索，
不接受手改；key 不变，正文的 \\cite 不用改。只处理台账中由 bib_resolve 写入（add）且带 DOI 的条目；
申请人登记的条目（register_user）与没有 DOI 的条目不刷新：先 citation_ledger.py drop，从 .bib 删去，再用 bib_resolve 重新解析。
退出码：0 全部刷新或无需改动；1 有条目刷新失败（该条目保持原样）；2 输入或路径错误（不写任何文件）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import requests

from bib_resolve import HttpSession, Settings, backup_file, check_task_root, crossref_by_doi, to_bibtex
from citation_ledger import add_event, append_event, entry_sha256, load_ledger
from latex_files import bib_entry_texts, normalize_doi, scan_latex_tree
from proposal_common import ProposalError, load_config, proposal_paths, resolve_project_root

TITLE_FIELD_RE = re.compile(r"^\s*title\s*=\s*\{\{?(.*?)\}?\},?\s*$", re.MULTILINE)


@dataclass
class RefreshOutcome:
    bibkey: str
    status: str  # refreshed | unchanged | failed
    doi: str | None = None
    reason: str | None = None


def _wanted_title(record: Mapping[str, Any], entry_text: str) -> str:
    """核对标题用台账记下的检索记录标题；没有时用条目里的 title 字段。"""
    provenance = record.get("provenance") if isinstance(record.get("provenance"), Mapping) else {}
    title = str(provenance.get("record_title") or "").strip()
    if title:
        return title
    match = TITLE_FIELD_RE.search(entry_text)
    return match.group(1) if match else ""


def _check_keys(keys: Sequence[str], texts: Mapping[str, str], ledger: Mapping[str, Mapping[str, Any]]) -> None:
    """有任何一个 key 不能刷新时报错，一条也不处理。"""
    absent = [k for k in keys if k not in texts]
    if absent:
        raise ProposalError(f".bib 中没有这些条目：{'、'.join(absent)}")
    not_added = [k for k in keys if (ledger.get(k) or {}).get("event") != "add"]
    if not_added:
        raise ProposalError(f"这些条目不是 bib_resolve 写入的（台账中没有有效的 add 记录），不能刷新：{'、'.join(not_added)}；"
                            "申请人登记的条目由申请人核对")
    no_doi = [k for k in keys if not normalize_doi(ledger[k].get("doi"))]
    if no_doi:
        raise ProposalError(f"这些条目在台账中没有 DOI，不能刷新：{'、'.join(no_doi)}；"
                            "请先 citation_ledger.py drop，从 .bib 删去，再用 bib_resolve 重新解析")


def _rewrite(bib_files: Sequence[Path], old_texts: Mapping[str, str], new_texts: Mapping[str, str], backup_dir: Path) -> list[str]:
    """把各 key 的条目原文换成新文本；只改含该条目的文件，写前备份。返回备份路径。"""
    backups: list[str] = []
    for path in bib_files:
        path = Path(path)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated = text
        for key, new in new_texts.items():
            old = old_texts[key].rstrip()
            if updated.count(old) == 1:
                updated = updated.replace(old, new.rstrip(), 1)
        if updated != text:
            backups.append(str(backup_file(path, backup_dir)))
            path.write_text(updated, encoding="utf-8")
    return backups


def refresh(project_root: Path, task_root: Path, keys: Sequence[str], *, session: HttpSession | None = None,
            sleep: Callable[[float], None] | None = None) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    task = check_task_root(task_root)
    wanted = list(dict.fromkeys(keys))
    if not wanted:
        raise ProposalError("至少给一个 --key")
    tree = scan_latex_tree(root)
    if not tree.bib_files:
        raise ProposalError("main.tex 及其 \\input 文件中没有 \\bibliography，无法确定 .bib")
    texts = bib_entry_texts(tree.bib_files)
    ledger_path = proposal_paths(root).ledger
    ledger = load_ledger(ledger_path)
    _check_keys(wanted, texts, ledger)
    settings = Settings.from_config(load_config())
    if sleep is not None:
        settings = replace(settings, sleep=sleep)
    http = session or requests.Session()
    outcomes: list[RefreshOutcome] = []
    new_texts: dict[str, str] = {}
    for key in wanted:
        doi = normalize_doi(ledger[key].get("doi"))
        meta, reason = crossref_by_doi(doi, _wanted_title(ledger[key], texts[key]), session=http, settings=settings)
        if meta is None:
            outcomes.append(RefreshOutcome(key, "failed", doi=doi, reason=reason))
            continue
        text = to_bibtex(meta, key)
        if entry_sha256(text) == entry_sha256(texts[key]):
            outcomes.append(RefreshOutcome(key, "unchanged", doi=doi))
            continue
        new_texts[key] = text
        outcomes.append(RefreshOutcome(key, "refreshed", doi=meta.doi or doi))
    out_dir = task / "nsfc-proposal" / "output"
    backups = _rewrite(tree.bib_files, texts, new_texts, out_dir / "bib_backup")
    written = bib_entry_texts(tree.bib_files)
    for outcome in outcomes:
        if outcome.status != "refreshed":
            continue
        if entry_sha256(written.get(outcome.bibkey, "")) != entry_sha256(new_texts[outcome.bibkey]):
            outcome.status, outcome.reason = "failed", "未能在 .bib 中定位原条目文本，条目未改"
            continue
        prior = ledger[outcome.bibkey]
        append_event(ledger_path, add_event(
            outcome.bibkey, source="crossref", entry_text=written[outcome.bibkey], doi=outcome.doi,
            abstract=prior.get("abstract"), provenance=prior.get("provenance") or {}, reason="refresh"))
    summary = {
        "bib_files": [str(p) for p in tree.bib_files],
        "backups": backups,
        "counts": {status: sum(1 for o in outcomes if o.status == status) for status in ("refreshed", "unchanged", "failed")},
        "outcomes": [asdict(o) for o in outcomes],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bib_refresh.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bib_refresh.py", description="按台账中的 DOI 重新取元数据，用原 key 重写 .bib 条目")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task-root", required=True, help="本任务的 .bensz-api/task-*/ 目录")
    parser.add_argument("--key", action="append", required=True, help="要刷新的 bibkey；可重复")
    args = parser.parse_args(argv)
    try:
        summary = refresh(Path(args.project_root), Path(args.task_root), args.key)
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["counts"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
