#!/usr/bin/env python3
"""跨章确定性检查（设计文档 4.7 节）。语义一致性由 AI 判断，不在本脚本内。

errors：必须修正。needs_review：交给 AI 复核，例如疑似内部编号可能是「T1 加权」这类误报。
placeholders：正文中全部可见占位。退出码：0 无 errors；1 有 errors；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from case_validate import case_ids, claim_ids
from latex_files import read_bib_index, relpath, scan_latex_tree
from proposal_common import ProposalError, load_config, project_path, proposal_paths, read_yaml, resolve_project_root, split_latex_comment

CITE_RE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\]){0,2}\{([^}]*)\}")
DEFAULT_PLACEHOLDER = "【待补充：[^】]*】"
LABELS = {
    "hidden_placeholder": "注释中的隐藏占位",
    "placeholder_unlisted": "占位未列入 assumptions.md",
    "missing_bibkey": "引用 key 不在 .bib",
    "term_unused": "界定过的术语未在正文出现",
    "stale_section": "章节依据旧版科学论证",
    "internal_id": "疑似内部编号（请 AI 复核）",
    "file_not_compiled": "文件未被 main.tex 引用",
}


@dataclass(frozen=True)
class Finding:
    kind: str
    file: str
    line: int | None
    detail: str


@dataclass
class Report:
    errors: list[Finding] = field(default_factory=list)
    needs_review: list[Finding] = field(default_factory=list)
    placeholders: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {name: [asdict(f) for f in getattr(self, name)] for name in ("errors", "needs_review", "placeholders")}


def _id_regex(ids: Iterable[str], extra_patterns: Iterable[str]) -> re.Pattern[str] | None:
    patterns = [re.escape(i) for i in sorted(ids)] + [str(p) for p in extra_patterns]
    if not patterns:
        return None
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(patterns) + r")(?![A-Za-z0-9])")


def check_project(project_root: Path, config: Mapping[str, Any] | None = None) -> Report:
    settings = (config or load_config()).get("consistency") or {}
    hidden_words = [str(w) for w in settings.get("hidden_placeholder_words") or []]
    placeholder_re = re.compile(str(settings.get("placeholder_pattern") or DEFAULT_PLACEHOLDER))
    root = resolve_project_root(project_root)
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    evidence = read_yaml(paths.evidence) if paths.evidence.exists() else {}
    plan = read_yaml(paths.plan)
    tree = scan_latex_tree(root)
    compiled = {relpath(root, p) for p in tree.tex_files}
    bib_keys = read_bib_index(tree.bib_files).keys
    assumptions = paths.assumptions.read_text(encoding="utf-8") if paths.assumptions.exists() else ""
    id_re = _id_regex(case_ids(case) | claim_ids(evidence), settings.get("extra_internal_id_patterns") or [])
    entries = [e for e in plan.get("files") or [] if isinstance(e, Mapping) and isinstance(e.get("file"), str)]

    report = Report()
    bodies: list[str] = []
    for entry in entries:
        rel = entry["file"]
        path = project_path(root, rel)
        if not path.is_file():
            continue
        is_tex = rel.endswith(".tex")
        if is_tex and rel not in compiled:
            report.needs_review.append(Finding("file_not_compiled", rel, None, "main.tex 未引用该文件，内容不会进入 PDF"))
        for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            body, comment = split_latex_comment(raw) if is_tex else (raw, "")
            bodies.append(body)
            if comment and any(word in comment for word in hidden_words):
                report.errors.append(Finding("hidden_placeholder", rel, number, comment.strip()[:80]))
            if id_re:
                for match in id_re.finditer(body):
                    report.needs_review.append(Finding("internal_id", rel, number, match.group(0)))
            for match in placeholder_re.finditer(body):
                report.placeholders.append(Finding("placeholder", rel, number, match.group(0)))
                if match.group(0) not in assumptions:
                    report.errors.append(Finding("placeholder_unlisted", rel, number, match.group(0)))
            if is_tex:
                for match in CITE_RE.finditer(body):
                    for key in (k.strip() for k in match.group(1).split(",")):
                        if key and key not in bib_keys:
                            report.errors.append(Finding("missing_bibkey", rel, number, key))

    text = "\n".join(bodies)
    for term in case.get("terms") or []:
        name = term.get("term").strip() if isinstance(term, Mapping) and isinstance(term.get("term"), str) else ""
        if name and name not in text:
            report.errors.append(Finding("term_unused", "", None, name))
    version = case.get("version")
    for entry in entries:
        written = entry.get("written_with_case_version")
        if isinstance(written, int) and isinstance(version, int) and written < version:
            report.errors.append(Finding("stale_section", entry["file"], None, f"依据第 {written} 版科学论证，当前为第 {version} 版"))
    return report


def _print_human(report: Report) -> None:
    for title, items in (("必须修正", report.errors), ("需要复核", report.needs_review)):
        print(f"## {title}（{len(items)}）")
        for f in items:
            where = f"{f.file}:{f.line}" if f.line else (f.file or "全文")
            print(f"- [{LABELS.get(f.kind, f.kind)}] {where} {f.detail}")
    print(f"## 正文占位（{len(report.placeholders)}）")
    for f in report.placeholders:
        print(f"- {f.file}:{f.line} {f.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="consistency_check.py", description="nsfc-proposal 跨章一致性检查")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)
    try:
        report = check_project(Path(args.project_root))
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
