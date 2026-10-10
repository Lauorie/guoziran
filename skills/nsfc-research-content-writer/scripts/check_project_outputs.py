#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

from _yaml_utils import extract_yaml_list_under_block, extract_yaml_value_under_block
from plan_years import CN_NUMERALS, duration_years, load_yearly_plan, year_label

# 只按短语匹配；单独的「首次」（如「首次测试前」）是叙述先后，不报
DEFAULT_RISK_PHRASES = [
    "首次提出", "首次发现", "首次实现", "首次揭示", "首次构建", "首次建立", "国内首次", "国际首次", "世界首次",
    "领先", "填补空白", "突破性", "国际领先", "世界领先",
]
# 含 S+数字、但不是内部编号的专业写法；config.yaml 的 checks.allowed_s_tokens 缺失时使用
DEFAULT_ALLOWED_S_TOKENS = ["L5-S1", "L5–S1", "S100", "S100β", "S1P", "S1 受体", "S1受体"]

# SKILL.md 规定 S1–S4 只用于内部规划，禁止出现在 .tex 正文中。
# 紧跟在字母、数字或连字符后的 S+数字（如 L5–S1、T12-S2 中的 S1、S2）是解剖节段等写法，不算编号。
INTERNAL_SUBGOAL_ID_RE = re.compile(r"(?<![A-Za-z0-9\-‐‑–—−])S\d+(?![A-Za-z0-9])")
LATEX_COMMENT_RE = re.compile(r"(?<!\\)%.*$")
# 年度标题：「第1年」「第 1 年」「第一年」……「第十年」；「第N年度」不算
YEAR_HEADER_RE = re.compile(rf"第\s*(\d{{1,2}}|[{CN_NUMERALS}]{{1,3}})\s*年(?!度)")


def _err(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _read_targets_from_config(config_yaml: Path) -> dict[str, str]:
    lines = config_yaml.read_text(encoding="utf-8").splitlines()
    research = extract_yaml_value_under_block(lines, "targets", "research_content_tex")
    innovation = extract_yaml_value_under_block(lines, "targets", "innovation_tex")
    yearly = extract_yaml_value_under_block(lines, "targets", "yearly_plan_tex")
    if not research or not innovation or not yearly:
        raise ValueError("config.yaml missing targets.*_tex")
    return {
        "research_content_tex": research,
        "innovation_tex": innovation,
        "yearly_plan_tex": yearly,
    }


def _read_checks_from_config(config_yaml: Path) -> list[str]:
    lines = config_yaml.read_text(encoding="utf-8").splitlines()
    return extract_yaml_list_under_block(lines, "checks", "risk_phrases") or DEFAULT_RISK_PHRASES


def _read_allowed_s_tokens(config_yaml: Path) -> list[str]:
    lines = config_yaml.read_text(encoding="utf-8").splitlines()
    return extract_yaml_list_under_block(lines, "checks", "allowed_s_tokens") or DEFAULT_ALLOWED_S_TOKENS


def find_leaked_ids(text: str, allowed_tokens: Sequence[str]) -> list[str]:
    """正文中疑似内部子目标编号的 S+数字；先去掉允许的专业写法（长的先去）。"""
    for token in sorted((t for t in allowed_tokens if t), key=len, reverse=True):
        text = text.replace(token, " ")
    return sorted(set(INTERNAL_SUBGOAL_ID_RE.findall(text)))


def _year_number(token: str) -> int | None:
    """「4」「四」「十一」等转成整数；认不出时返回 None。"""
    if token.isdigit():
        return int(token)
    digits = {ch: i for i, ch in enumerate(CN_NUMERALS[:9], start=1)}
    if "十" not in token:
        return digits.get(token) if len(token) == 1 else None
    tens, _, ones = token.partition("十")
    if (tens and tens not in digits) or (ones and ones not in digits):
        return None
    return digits.get(tens, 1) * 10 + digits.get(ones, 0)


def years_mentioned(text: str) -> set[int]:
    """正文中出现的年度序号（第N年）。"""
    found = (_year_number(m.group(1)) for m in YEAR_HEADER_RE.finditer(text))
    return {n for n in found if n}


def _check_file_exists(project_root: Path, relpath: str) -> str | None:
    path = project_root / relpath
    if not path.exists():
        return f"missing file: {path}"
    if not path.is_file():
        return f"not a file: {path}"
    return None


def _strip_latex_comments(text: str) -> str:
    return "\n".join(LATEX_COMMENT_RE.sub("", line) for line in text.splitlines())


def _check_minimal_content(
    path: Path, *, kind: str, allowed_s_tokens: Sequence[str] = (), years: int = 3
) -> list[str]:
    text = _strip_latex_comments(path.read_text(encoding="utf-8", errors="replace"))
    problems: list[str] = []

    leaked = find_leaked_ids(text, allowed_s_tokens)
    if leaked:
        problems.append(
            f"{path}: internal subgoal IDs leaked into body: {', '.join(leaked)} (use natural language instead; "
            "if this is a correct technical term, add it to checks.allowed_s_tokens in config.yaml)"
        )

    if kind == "research":
        if not text.strip():
            problems.append(f"{path}: research content is empty")
    elif kind == "innovation":
        if not text.strip():
            problems.append(f"{path}: innovation content is empty")
    elif kind == "yearly":
        present = years_mentioned(text)
        for year in range(1, years + 1):
            if year not in present:
                problems.append(f"{path}: missing yearly header ({year_label(year)}) for a {years}-year duration")
        # 只看第 N+1 年：计划写多了年份必然先出现它；更远的「第十年」多是随访等叙述，不报
        if years + 1 in present:
            problems.append(f"{path}: yearly header beyond the {years}-year duration ({year_label(years + 1)})")
    else:
        problems.append(f"{path}: unknown kind {kind}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lightweight checker for nsfc-research-content-writer outputs under a given project_root.",
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="NSFC LaTeX project root (must contain extraTex/).",
    )
    parser.add_argument(
        "--no-content-check",
        action="store_true",
        help="Only check that target files exist (skip content heuristics).",
    )
    parser.add_argument(
        "--no-risk-scan",
        action="store_true",
        help="Skip scanning for risk phrases like '首次提出/领先' (default: scan and warn).",
    )
    parser.add_argument(
        "--fail-on-risk-phrases",
        action="store_true",
        help="Treat risk phrases as errors (default: warnings).",
    )
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument(
        "--years",
        type=int,
        help="Research duration in years; the yearly plan must cover year 1..N and nothing beyond "
        "(default without --years/--project-type: yearly_plan.default_years).",
    )
    duration.add_argument(
        "--project-type",
        help="Project type, e.g. 面上项目; years come from yearly_plan.duration_by_keyword in config.yaml.",
    )
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    config_yaml = skill_root / "config.yaml"
    if not config_yaml.exists():
        return _err(f"missing config.yaml: {config_yaml}")

    project_root = Path(args.project_root).expanduser().resolve()
    if not project_root.exists() or not project_root.is_dir():
        return _err(f"project_root does not exist or is not a directory: {project_root}")
    if not (project_root / "extraTex").exists():
        return _err(f"project_root missing extraTex/: {project_root}")

    try:
        targets = _read_targets_from_config(config_yaml)
    except ValueError as exc:
        return _err(str(exc))

    try:
        plan = load_yearly_plan(config_yaml)
    except ValueError as exc:
        return _err(str(exc))
    if args.years is not None:
        if not 1 <= args.years <= plan.max_years:
            parser.error(f"--years must be in 1..{plan.max_years}")
        years = args.years
    elif args.project_type is not None:
        years, matched = duration_years(args.project_type, config_yaml)
        if not matched:
            # 立即输出：年份检查报错时也要让人看到年数从哪来
            print(
                f"WARN: project type {args.project_type!r} matches no keyword in yearly_plan.duration_by_keyword; "
                f"using {years} years (record this in assumptions.md as an AI-proposed item)",
                file=sys.stderr,
            )
    else:
        years = plan.default_years

    risk_phrases = _read_checks_from_config(config_yaml)
    allowed_s_tokens = _read_allowed_s_tokens(config_yaml)

    errors: list[str] = []
    errors.extend(
        e
        for e in [
            _check_file_exists(project_root, targets["research_content_tex"]),
            _check_file_exists(project_root, targets["innovation_tex"]),
            _check_file_exists(project_root, targets["yearly_plan_tex"]),
        ]
        if e
    )
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not args.no_content_check:
        checks = [
            (targets["research_content_tex"], "research"),
            (targets["innovation_tex"], "innovation"),
            (targets["yearly_plan_tex"], "yearly"),
        ]
        for relpath, kind in checks:
            errors.extend(
                _check_minimal_content(
                    project_root / relpath, kind=kind, allowed_s_tokens=allowed_s_tokens, years=years
                )
            )

    warnings: list[str] = []
    if not args.no_risk_scan:
        for relpath in [
            targets["research_content_tex"],
            targets["innovation_tex"],
            targets["yearly_plan_tex"],
        ]:
            path = project_root / relpath
            text = path.read_text(encoding="utf-8", errors="replace")
            for phrase in risk_phrases:
                if phrase in text:
                    msg = f"{path}: contains risk phrase '{phrase}'"
                    if args.fail_on_risk_phrases:
                        errors.append(msg)
                    else:
                        warnings.append(msg)

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    print("OK: project outputs check passed")
    print(f"- project_root: {project_root}")
    print(f"- research duration: {years} years")
    print("- targets:")
    print(f"  - {targets['research_content_tex']}")
    print(f"  - {targets['innovation_tex']}")
    print(f"  - {targets['yearly_plan_tex']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
