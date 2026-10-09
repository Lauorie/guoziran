#!/usr/bin/env python3
"""nsfc-proposal 共享文件的命令行入口。

退出码：0 成功；1 校验未通过；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from latex_files import relpath, scan_latex_tree
from proposal_common import (
    SKILL_ROOT,
    ProposalError,
    append_under_heading,
    load_config,
    proposal_paths,
    read_yaml,
    resolve_project_root,
    write_yaml,
)

ASSUMPTIONS_TEMPLATE = "# 假设与待核实清单\n\n## 确认点状态\n\n## AI 拟定项\n\n## 待核实项\n\n## 占位清单\n"
LEADS_TEMPLATE = "# 文献线索\n\n## 检索式\n\n## 未核实线索\n"


@dataclass
class InitResult:
    created: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_length_budgets(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """读取 nsfc-length-aligner 的篇幅预算；文件缺失时返回空列表。"""
    source = config.get("length_budget_source")
    if not source:
        return []
    path = (SKILL_ROOT / str(source)).resolve()
    if not path.is_file():
        return []
    standard = read_yaml(path).get("length_standard") or {}
    unit = standard.get("unit") or "cjk_chars"
    budgets = []
    for item in standard.get("files") or []:
        if isinstance(item, Mapping) and item.get("match"):
            budgets.append({"match": str(item["match"]), "min": item.get("min"), "max": item.get("max"), "unit": unit})
    return budgets


def budget_for(file: str, budgets: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    name = Path(file).name
    for budget in budgets:
        if fnmatch.fnmatch(name, budget["match"]) and isinstance(budget["min"], int) and isinstance(budget["max"], int):
            return {"min": budget["min"], "max": budget["max"], "unit": budget["unit"]}
    return None


def _select_sections(config: Mapping[str, Any], names: Sequence[str] | None) -> list[Mapping[str, Any]]:
    sections = [s for s in config.get("sections") or [] if isinstance(s, Mapping)]
    if not names:
        return sections
    known = [str(s["name"]) for s in sections]
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ProposalError(f"未知章节：{'、'.join(unknown)}；可选：{'、'.join(known)}")
    return [s for s in sections if s["name"] in names]


def init_proposal(
    project_root: Path,
    *,
    title: str,
    project_type: str,
    sections: Sequence[str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> InitResult:
    """在 project_root/proposal/ 下建立共享文件骨架；已存在的文件不覆盖。"""
    cfg = config or load_config()
    root = resolve_project_root(project_root)
    if not (root / "extraTex").is_dir():
        raise ProposalError(f"project_root 缺少 extraTex/，不是 NSFC 正文项目：{root}")
    compiled = {relpath(root, p) for p in scan_latex_tree(root).tex_files}
    chosen = _select_sections(cfg, sections)
    budgets = load_length_budgets(cfg)
    result = InitResult()
    plan_files = []
    for section in chosen:
        file = str(section["file"])
        if file.endswith(".tex") and file not in compiled:
            fallback = section.get("fallback_file")
            if fallback:
                result.warnings.append(f"main.tex 未引用 {file}；{section['name']}改写到 {fallback}，需申请人决定放在申请书何处。")
                file = str(fallback)
            else:
                result.warnings.append(f"main.tex 未引用 {file}；该章写入后不会出现在 PDF 中。")
        plan_files.append({
            "file": file,
            "writer": section["writer"],
            "must_include": [],
            "must_exclude": list(section.get("must_exclude") or []),
            "length": budget_for(str(section["file"]), budgets),
            "placeholders": [],
            "written_with_case_version": None,
        })

    paths = proposal_paths(root)
    paths.root.mkdir(parents=True, exist_ok=True)
    if not paths.case.exists():
        case = read_yaml(SKILL_ROOT / "assets" / "scientific_case.yaml")
        case["project"] = {"type": project_type, "title": title, "sections": [str(s["name"]) for s in chosen]}
        write_yaml(paths.case, case)
        result.created.append(paths.case)
    if not paths.evidence.exists():
        write_yaml(paths.evidence, read_yaml(SKILL_ROOT / "assets" / "evidence_map.yaml"))
        result.created.append(paths.evidence)
    if not paths.plan.exists():
        plan = read_yaml(SKILL_ROOT / "assets" / "section_plan.yaml")
        plan["files"] = plan_files
        write_yaml(paths.plan, plan)
        result.created.append(paths.plan)
    for path, template in ((paths.assumptions, ASSUMPTIONS_TEMPLATE), (paths.leads, LEADS_TEMPLATE)):
        if not path.exists():
            path.write_text(template, encoding="utf-8")
            result.created.append(path)
    if paths.assumptions in result.created:
        for warning in result.warnings:
            append_under_heading(paths.assumptions, "## 待核实项", f"- {warning}")
    return result


def cmd_init(args: argparse.Namespace) -> int:
    sections = [s.strip() for s in args.sections.split(",") if s.strip()] if args.sections else None
    result = init_proposal(Path(args.project_root), title=args.title, project_type=args.project_type, sections=sections)
    for path in result.created:
        print(f"已创建：{path}")
    for warning in result.warnings:
        print(f"⚠️ {warning}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="case.py", description="nsfc-proposal 共享文件工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="在 project_root/proposal/ 下建立共享文件骨架（已存在的文件不覆盖）")
    p_init.add_argument("--project-root", required=True)
    p_init.add_argument("--title", required=True)
    p_init.add_argument("--type", dest="project_type", required=True, help="项目类型，如 青年科学基金")
    p_init.add_argument("--sections", help="逗号分隔的章节名；默认全部")
    p_init.set_defaults(func=cmd_init)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
