#!/usr/bin/env python3
"""各章的确定性检查：内部编号、绝对化措辞、占位写法、年度标题、风险条数、工作条件、摘要格式。

章节名取 config.yaml sections[].name；文件路径优先取 proposal/section_plan.yaml 中该章条目的 file，
没有 proposal/section_plan.yaml 或没有该章条目时取配置的 file（file 不存在时再试 fallback_file）。
退出码：0 无 ERROR；1 有 ERROR；2 参数错误或未知章节。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from abstract_check import check_text as check_abstract
from plan_years import CN_NUMERALS, duration_years, load_yearly_plan, year_label
from proposal_common import (
    ProposalError, load_config, project_path, proposal_paths, read_yaml, resolve_project_root, section_for,
    split_latex_comment,
)

# S1–S4 只用于内部规划。紧跟在字母、数字或连字符后的 S+数字（如 L5–S1、T12-S2）是解剖节段等写法，不算编号。
INTERNAL_SUBGOAL_ID_RE = re.compile(r"(?<![A-Za-z0-9\-‐‑–—−])S\d+(?![A-Za-z0-9])")
# 年度标题：「第1年」「第 1 年」「第一年」……「第十年」；「第N年度」同样算第N年
YEAR_HEADER_RE = re.compile(rf"第\s*(\d{{1,2}}|[{CN_NUMERALS}]{{1,3}})\s*年")
LEGACY_PLACEHOLDERS = ("[请补充：", "[需补充：", "[待补充：")
RESPONSE_WORDS = ("应对", "预案", "替代")
HAVE_WORDS = ("已具备", "具备")
LACK_WORDS = ("尚缺", "缺少", "不足")
INNOVATION_SECTION = "特色与创新"
YEARLY_SECTION = "年度研究计划"
FOUNDATION_SECTION = "研究基础"
CONDITIONS_SECTION = "工作条件"
ABSTRACT_SECTION = "摘要"


def strip_latex_comments(text: str) -> str:
    return "\n".join(split_latex_comment(line)[0] for line in text.splitlines())


def find_leaked_ids(text: str, allowed_tokens: Sequence[str]) -> list[str]:
    """正文中疑似内部子目标编号的 S+数字；先去掉允许的专业写法（长的先去）。"""
    for token in sorted((t for t in allowed_tokens if t), key=len, reverse=True):
        text = text.replace(token, " ")
    return sorted(set(INTERNAL_SUBGOAL_ID_RE.findall(text)))


def find_risk_phrases(text: str, phrases: Sequence[str]) -> list[str]:
    """文中出现的绝对化措辞，每个短语报一次；被更长的已列短语包住的出现不单独计。"""
    unique = list(dict.fromkeys(p for p in phrases if p))
    spans = {p: [(m.start(), m.end()) for m in re.finditer(re.escape(p), text)] for p in unique}
    found = []
    for phrase in unique:
        longer = [span for q in unique if q != phrase and phrase in q for span in spans[q]]
        if any(not any(lo <= s and e <= hi for lo, hi in longer) for s, e in spans[phrase]):
            found.append(phrase)
    return found


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


_NUMERALS = {c: str(i) for i, c in enumerate("一二三四五六七八九十", 1)}
_ORDINAL = r"(?:\d+|[一二三四五六七八九十])"


def _norm(ordinal: str) -> str:
    """序号归一：一 == 1。"""
    return _NUMERALS.get(ordinal, str(int(ordinal)) if ordinal.isdigit() else ordinal)


def count_risks(text: str) -> int:
    """研究风险条数：按条目计数，取三种写法中最大的一个，不相加（它们描述的是同一批风险）。

    - 序号：只在条目开头计数（行首，可带 \\item、标题命令开括号、\\textbf{ 或 # ），
      正文里的「针对风险一」「上述风险一」不算。「风险」后接一…十或阿拉伯数字，再接 ：: 、 . ) } 或空白（「风险一的应对」「风险一，」是行文，不算）；
      按（开头到「风险」之间 0-8 个汉字的类别前缀，归一序号）去重，
      「风险一」与「风险1」同一条，「技术风险一」与「资源风险一」是两条。
    - 标题：\\subsubsubsection、\\subsubsection 与 # 标题中含「风险」的，
      同时含「应对/措施」的（如「研究风险的应对措施」）是章节标题，不计。
    - 标签：行首（可带 \\item、\\textbf{}）的「<1-8 个汉字>风险[序号]：」，
      按整个标签（序号归一）去重，含「应对/措施」的不计。
    """
    ordinals = {
        (prefix, _norm(num))
        for prefix, num in re.findall(
            rf"(?m)^[ \t]*(?:\\item\s*)?(?:\\(?:subsubsubsection|subsubsection|paragraph)\*?\{{)?"
            rf"(?:\\textbf\{{)?(?:#+[ \t]*)?([\u4e00-\u9fff]{{0,8}})风险\s*({_ORDINAL})(?=[：:、.．)）}}\s]|$)", text)
    }
    headings = [
        h for h in (
            re.findall(r"\\subsubsubsection\*?\{([^}]*)\}", text)
            + re.findall(r"\\subsubsection\*?\{([^}]*)\}", text)
            + re.findall(r"(?m)^[ \t]*#+[ \t]*(.*)$", text)
        )
        if "风险" in h and "应对" not in h and "措施" not in h
    ]
    labels = {
        (prefix, _norm(num) if num else "")
        for prefix, num in re.findall(
            rf"(?m)^[ \t]*(?:\\item\s*)?(?:\\textbf\{{)?([\u4e00-\u9fff]{{1,8}})风险(?:[ \t]*({_ORDINAL}))?\}}?[：:]", text)
        if "应对" not in prefix and "措施" not in prefix
    }
    return max(len(ordinals), len(headings), len(labels))


class Report:
    """按文件收集 ERROR / WARN。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, label: str, message: str) -> None:
        self.errors.append(f"{label}: {message}")

    def warn(self, label: str, message: str) -> None:
        self.warnings.append(f"{label}: {message}")


def resolve_file(root: Path, config: Mapping[str, Any], section: Mapping[str, Any], plan: Mapping[str, Any] | None) -> str:
    """章节对应的相对路径：计划条目 > 配置 file（不存在且有 fallback_file 时用后者）。"""
    name = section["name"]
    for entry in (plan or {}).get("files") or []:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("file"), str):
            continue
        matched = section_for(config, entry)
        if matched is not None and matched.get("name") == name:
            return entry["file"]
    primary = str(section["file"])
    fallback = section.get("fallback_file")
    if fallback and not project_path(root, primary).exists() and project_path(root, str(fallback)).exists():
        return str(fallback)
    return primary


def determine_years(args: argparse.Namespace, root: Path, label: str, report: Report) -> int:
    """研究期限：--years > --project-type > scientific_case.yaml 的 project.type > 默认年数（给 WARN）。"""
    plan = load_yearly_plan()
    if args.years is not None:
        if not 1 <= args.years <= plan.max_years:
            raise ProposalError(f"--years 须在 1..{plan.max_years} 之间")
        return args.years
    project_type = args.project_type
    if project_type is None:
        case_path = proposal_paths(root).case
        case = read_yaml(case_path) if case_path.exists() else {}
        project = case.get("project") if isinstance(case.get("project"), dict) else {}
        value = project.get("type")
        project_type = value if isinstance(value, str) and value.strip() else None
    if project_type is None:
        report.warn(label, f"未给出项目类型，按默认 {plan.default_years} 年检查（请用 --project-type 或 --years 指定，并记入 assumptions.md）")
        return plan.default_years
    years, matched = duration_years(project_type)
    if not matched:
        report.warn(label, f"项目类型「{project_type}」不在年数表中，按默认 {years} 年检查（请记入 assumptions.md）")
    return years


def check_generic(label: str, text: str, name: str, checks: Mapping[str, Any], report: Report) -> None:
    leaked = find_leaked_ids(text, checks.get("allowed_s_tokens") or [])
    if leaked:
        report.error(label, f"正文出现内部编号 {'、'.join(leaked)}，请改成自然语言；若是专业写法，把它加到 config.yaml 的 chapter_checks.allowed_s_tokens")
    for phrase in find_risk_phrases(text, checks.get("risk_phrases") or []):
        (report.error if name == INNOVATION_SECTION else report.warn)(label, f"含绝对化措辞「{phrase}」，请改为可核验的表述")
    for legacy in LEGACY_PLACEHOLDERS:
        if legacy in text:
            report.error(label, f"占位写法「{legacy}」不规范，请改成「【待补充：……】」")


def check_yearly(label: str, text: str, years: int, report: Report) -> None:
    present = years_mentioned(text)
    for year in range(1, years + 1):
        if year not in present:
            report.error(label, f"缺少{year_label(year)}的年度标题（研究期限 {years} 年）")
    # 只看第 N+1 年：计划写多了年份必然先出现它；更远的「第十年」多是随访等叙述，不报
    if years + 1 in present:
        report.error(label, f"出现超出研究期限 {years} 年的年度标题（{year_label(years + 1)}）")


def check_foundation(label: str, text: str, min_risks: int, report: Report) -> None:
    if "风险" not in text:
        report.error(label, "没有「风险」内容，研究基础需写明研究风险及应对")
        return
    if not any(word in text for word in RESPONSE_WORDS):
        report.warn(label, "提到了风险但没有「应对/预案/替代」，请确认每条风险都有应对")
    count = count_risks(text)
    if count < min_risks:
        report.error(label, f"风险条目 {count} 条，少于 {min_risks} 条")


def check_conditions(label: str, text: str, report: Report) -> None:
    if not any(word in text for word in HAVE_WORDS):
        report.warn(label, "没有「已具备/具备」，请确认写明了现有条件")
    if not any(word in text for word in LACK_WORDS):
        report.warn(label, "没有「尚缺/缺少/不足」，请确认写明了缺少的条件及解决办法")


def check_section(
    root: Path, config: Mapping[str, Any], section: Mapping[str, Any], plan: Mapping[str, Any] | None,
    args: argparse.Namespace, report: Report,
) -> None:
    name = str(section["name"])
    rel = resolve_file(root, config, section, plan)
    label = Path(rel).as_posix()
    path = project_path(root, rel)
    if not path.is_file():
        report.error(label, "文件不存在")
        return
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".tex":
        text = strip_latex_comments(raw)
        if not text.strip():
            report.error(label, "去掉注释后正文为空")
            return
        check_generic(label, text, name, config.get("chapter_checks") or {}, report)
    else:
        text = raw
        if not text.strip():
            report.error(label, "文件内容为空")
            return
    if name == YEARLY_SECTION:
        check_yearly(label, text, determine_years(args, root, label, report), report)
    elif name == FOUNDATION_SECTION:
        check_foundation(label, text, int((config.get("chapter_checks") or {}).get("min_risks", 3)), report)
    elif name == CONDITIONS_SECTION:
        check_conditions(label, text, report)
    elif name == ABSTRACT_SECTION:
        result = check_abstract(raw, config)
        for message in result["errors"]:
            report.error(label, message)
        for message in result["warnings"]:
            report.warn(label, message)


def run(args: argparse.Namespace) -> Report:
    config = load_config()
    names = list(dict.fromkeys(args.section))
    sections = {str(s.get("name")): s for s in config.get("sections") or [] if isinstance(s, Mapping)}
    unknown = [n for n in names if n not in sections]
    if unknown:
        raise ProposalError(f"未知章节：{'、'.join(unknown)}（可用：{'、'.join(sections)}）")
    root = resolve_project_root(args.project_root)
    plan_path = proposal_paths(root).plan
    plan = read_yaml(plan_path) if plan_path.exists() else None
    report = Report()
    for name in names:
        check_section(root, config, sections[name], plan, args, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查申请书各章的确定性规则。退出码：0 无 ERROR；1 有 ERROR；2 参数错误或未知章节。")
    parser.add_argument("--project-root", required=True, help="申请书项目根目录")
    parser.add_argument("--section", action="append", required=True, help="章节名（config.yaml sections[].name），可重复")
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument("--years", type=int, help="研究期限（年）；年度研究计划须覆盖第 1 至第 N 年")
    duration.add_argument("--project-type", help="项目类型，如 面上项目；按 config.yaml yearly_plan 取年数")
    parser.add_argument("--json", action="store_true", help='输出 JSON：{"errors": [...], "warnings": [...]}')
    args = parser.parse_args(argv)
    try:
        report = run(args)
    except ValueError as exc:  # ProposalError 是 ValueError 的子类；yearly_plan 配置不合法时也走这里
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"errors": report.errors, "warnings": report.warnings}, ensure_ascii=False))
    else:
        for message in report.errors:
            print(f"ERROR {message}")
        for message in report.warnings:
            print(f"WARN {message}")
        if not report.errors:
            print("通过：未发现 ERROR")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
