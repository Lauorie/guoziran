#!/usr/bin/env python3
"""nsfc-proposal 共享文件的命令行入口。

退出码：0 成功；1 校验未通过；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from citation_ledger import load_ledger
from latex_files import bib_entry_texts, read_bib_index, relpath, scan_latex_tree
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
from case_render import WRITERS, info_form, render_case_md
from case_validate import validate_all

ASSUMPTIONS_TEMPLATE = "# 假设与待核实清单\n\n## 确认点状态\n\n## AI 拟定项\n\n## 待核实项\n\n## 占位清单\n"
LEADS_TEMPLATE = "# 文献线索\n\n## 检索式\n\n## 官方文件\n\n## 未核实线索\n"


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


def unledgered_note(keys: Sequence[str]) -> str:
    """init 时 .bib 中已有、未入台账的条目：提示申请人逐条确认，未入账的不得引用。"""
    return (f"`.bib` 中已有 {len(keys)} 条文献未入引用台账：{'、'.join(keys)}。确认由申请人提供后运行 "
            "`citation_ledger.py register-user --key K`；不是申请人的（如模板示例）从 `.bib` 删去。未入账的条目不得引用。")


def init_proposal(
    project_root: Path,
    *,
    title: str,
    project_type: str,
    sections: Sequence[str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> InitResult:
    """在 project_root/proposal/ 下建立共享文件骨架；已存在的文件不覆盖。

    引用台账只建空文件，不登记 .bib 中已有的条目；这些条目列入警告和「## 待核实项」，经申请人确认后用
    citation_ledger.py register-user --key 登记。
    """
    cfg = config or load_config()
    root = resolve_project_root(project_root)
    if not (root / "extraTex").is_dir():
        raise ProposalError(f"project_root 缺少 extraTex/，不是 NSFC 正文项目：{root}")
    tree = scan_latex_tree(root)
    compiled = {relpath(root, p) for p in tree.tex_files}
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
    if not paths.ledger.exists():
        paths.ledger.write_text("", encoding="utf-8")
        result.created.append(paths.ledger)
        existing = list(bib_entry_texts(tree.bib_files))
        if existing:
            note = unledgered_note(existing)
            result.warnings.append(note)
            if paths.assumptions not in result.created:
                append_under_heading(paths.assumptions, "## 待核实项", f"- {note}")
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


def _load_shared(root: Path) -> tuple[dict, dict | None, dict | None]:
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    evidence = read_yaml(paths.evidence) if paths.evidence.exists() else None
    plan = read_yaml(paths.plan) if paths.plan.exists() else None
    return case, evidence, plan


def cmd_validate(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    case, evidence, plan = _load_shared(root)
    bib = read_bib_index(scan_latex_tree(root).bib_files)
    ledger_path = proposal_paths(root).ledger
    ledger = load_ledger(ledger_path) if ledger_path.exists() else None
    problems = validate_all(case, evidence, plan, bib_keys=set(bib.keys), ledger=ledger)
    for problem in problems:
        print(f"✗ {problem}")
    print("✅ 校验通过" if not problems else f"共 {len(problems)} 处不通过")
    return 0 if not problems else 1


def _render(root: Path) -> Path:
    case, evidence, plan = _load_shared(root)
    paths = proposal_paths(root)
    paths.case_md.write_text(render_case_md(case, evidence, plan), encoding="utf-8")
    return paths.case_md


def cmd_render(args: argparse.Namespace) -> int:
    print(f"已生成：{_render(resolve_project_root(args.project_root))}")
    return 0


def cmd_to_info_form(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    case, _, plan = _load_shared(root)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(info_form(case, plan, args.writer), encoding="utf-8")
    print(f"已生成：{out}")
    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    version = case.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ProposalError("scientific_case.yaml 的 version 不是整数，无法加一")
    case["version"] = version + 1
    case["status"] = "draft"
    write_yaml(paths.case, case)
    _render(root)
    print(f"科学论证升至第 {case['version']} 版")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    case["status"] = args.set
    write_yaml(paths.case, case)
    label = "已确认" if args.set == "confirmed" else "未确认（先继续）"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    append_under_heading(paths.assumptions, "## 确认点状态", f"- {stamp} 第 {case.get('version')} 版：{label}")
    _render(root)
    print(f"确认点状态：{label}")
    return 0


def cmd_mark_written(args: argparse.Namespace) -> int:
    root = resolve_project_root(args.project_root)
    paths = proposal_paths(root)
    case = read_yaml(paths.case)
    plan = read_yaml(paths.plan)
    for entry in plan.get("files") or []:
        if isinstance(entry, dict) and entry.get("file") == args.file:
            entry["written_with_case_version"] = case.get("version")
            write_yaml(paths.plan, plan)
            print(f"{args.file} 依据第 {case.get('version')} 版科学论证")
            return 0
    raise ProposalError(f"section_plan.yaml 中没有文件 {args.file}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="case.py", description="nsfc-proposal 共享文件工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="在 project_root/proposal/ 下建立共享文件骨架（已存在的文件不覆盖）")
    p_init.add_argument("--project-root", required=True)
    p_init.add_argument("--title", required=True)
    p_init.add_argument("--type", dest="project_type", required=True, help="项目类型，如 青年科学基金")
    p_init.add_argument("--sections", help="逗号分隔的章节名；默认全部")
    p_init.set_defaults(func=cmd_init)

    p_validate = sub.add_parser("validate", help="校验 proposal/ 下的三份 YAML")
    p_validate.add_argument("--project-root", required=True)
    p_validate.set_defaults(func=cmd_validate)

    p_render = sub.add_parser("render", help="由 scientific_case.yaml 生成 scientific_case.md")
    p_render.add_argument("--project-root", required=True)
    p_render.set_defaults(func=cmd_render)

    p_form = sub.add_parser("to-info-form", help="为某个写作 skill 生成信息表")
    p_form.add_argument("--project-root", required=True)
    p_form.add_argument("--writer", required=True, choices=list(WRITERS))
    p_form.add_argument("--out", required=True)
    p_form.set_defaults(func=cmd_to_info_form)

    p_bump = sub.add_parser("bump", help="修改科学论证后：版本加一、状态置为 draft")
    p_bump.add_argument("--project-root", required=True)
    p_bump.set_defaults(func=cmd_bump)

    p_status = sub.add_parser("status", help="记录确认点的回答")
    p_status.add_argument("--project-root", required=True)
    p_status.add_argument("--set", required=True, choices=["confirmed", "bypassed"])
    p_status.set_defaults(func=cmd_status)

    p_mark = sub.add_parser("mark-written", help="记录某章依据的科学论证版本")
    p_mark.add_argument("--project-root", required=True)
    p_mark.add_argument("--file", required=True)
    p_mark.set_defaults(func=cmd_mark_written)

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
