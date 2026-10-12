#!/usr/bin/env python3
"""摘要文件检查：Markdown 标题分段、长度、引号、数字格式、标题候选与主要研究领域。

只认 config.yaml abstract.headings 中的四个 Markdown 标题，不认 [ZH] 之类的标记。
退出码：0 无 ERROR；1 有 ERROR；2 文件读不到或参数错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from proposal_common import ProposalError, load_config

HEADING_KEYS = ("title", "zh", "en", "field")
# 全角、装饰性双引号与直角引号；ASCII 双引号 U+0022 单独统计。双引号只允许 U+201C、U+201D。
NONSTANDARD_QUOTES = "＂〝〞「」『』"
NUMERIC_COMMA_RE = re.compile(r"(?<=\d)[,，](?=\d)")
MARKDOWN_MARK_RE = re.compile(r"\*\*|__|(?m:^\s*#)")
RECOMMENDED_ZH_RE = re.compile(r"(?m)^\s*推荐标题\s*[:：]\s*\S+")
RECOMMENDED_EN_RE = re.compile(r"(?mi)^\s*Recommended Title\s*[:：]\s*\S+")
CANDIDATE_RE = re.compile(r"(?m)^\s*(?:[-*]\s*)?\d+[\)\.、）]\s+\S.*$")
EN_TAG_RE = re.compile(r"EN\s*[:：]")
SENTENCE_END = "。！？!?"


def normalize_for_count(text: str) -> str:
    """连续空白折叠为一个空格后计数（含标点）。"""
    return re.sub(r"\s+", " ", text).strip()


def count_cjk_chars(text: str) -> int:
    """只数汉字（CJK 统一表意文字及扩展 A、B 区）。"""
    return sum(
        1 for ch in text
        if "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿" or "\U00020000" <= ch <= "\U0002a6df"
    )


def _heading_positions(lines: Sequence[str], headings: Mapping[str, str]) -> dict[str, int]:
    positions: dict[str, int] = {}
    for key in HEADING_KEYS:
        wanted = headings[key].strip()
        index = next((i for i, line in enumerate(lines) if line.strip() == wanted), None)
        if index is not None:
            positions[key] = index
    return positions


def _body(lines: Sequence[str], start: int, stop: int) -> str:
    return "\n".join(lines[start + 1:stop]).strip()


def _next_heading_line(lines: Sequence[str], start: int) -> int:
    """start 之后第一条以 # 开头的行（任意级别），没有则返回行数。"""
    return next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("#")), len(lines))


def _check_zh(zh: str, limit: int, errors: list[str]) -> int:
    count = len(normalize_for_count(zh))
    if not zh:
        errors.append("中文摘要内容为空")
        return 0
    if count > limit:
        errors.append(f"中文摘要 {count} 字（含标点），超过上限 {limit} 字（超出 {count - limit}）")
    ascii_quotes = zh.count('"')
    if ascii_quotes:
        errors.append(f"中文摘要含 ASCII 双引号 {ascii_quotes} 个，请改为中文弯引号“…”")
    other = sum(zh.count(ch) for ch in NONSTANDARD_QUOTES)
    if other:
        errors.append(f"中文摘要含非标准引号 {other} 个（全角＂、〝〞、「」『』），双引号只用“”")
    commas = len(NUMERIC_COMMA_RE.findall(zh))
    if commas:
        errors.append(f"中文摘要含千分位逗号 {commas} 处（如 1,000），请写成 1000")
    if MARKDOWN_MARK_RE.search(zh):
        errors.append("中文摘要含 Markdown 标记（** 、__ 或行首 #），请改为纯文本")
    return count


def _check_en(en: str, limit: int, errors: list[str]) -> int:
    count = len(normalize_for_count(en))
    if not en:
        errors.append("English Abstract 内容为空")
    elif count > limit:
        errors.append(f"English Abstract {count} 字符，超过上限 {limit}（超出 {count - limit}）")
    return count


def _check_title(title: str, minimum: int, errors: list[str]) -> int:
    if not title:
        errors.append("标题建议内容为空")
        return 0
    if not RECOMMENDED_ZH_RE.search(title):
        errors.append("标题建议缺少「推荐标题：」一行")
    if not RECOMMENDED_EN_RE.search(title):
        errors.append("标题建议缺少「Recommended Title:」一行")
    candidates = CANDIDATE_RE.findall(title)
    if len(candidates) < minimum:
        errors.append(f"标题候选 {len(candidates)} 条，少于 {minimum} 条")
    for line in candidates:
        label = line.strip()[:20]
        if "理由" not in line:
            errors.append(f"标题候选缺少「理由」：{label}")
        if not EN_TAG_RE.search(line):
            errors.append(f"标题候选缺少「EN:」英文标题：{label}")
    return len(candidates)


def _check_field(field: str, limit: int, errors: list[str]) -> int:
    if not field:
        errors.append("主要研究领域内容为空")
        return 0
    lines = [re.sub(r"^\s*[-*]\s*", "", line).strip() for line in field.splitlines() if line.strip()]
    sentence = lines[0] if lines else ""
    if len(lines) > 1 or any(ch in sentence.rstrip(SENTENCE_END) for ch in SENTENCE_END):
        errors.append("主要研究领域应为一句话")
    count = count_cjk_chars(field)
    if count > limit:
        errors.append(f"主要研究领域 {count} 个汉字，超过上限 {limit}")
    return count


def check_text(text: str, config: Mapping[str, Any]) -> dict[str, Any]:
    """检查摘要文本，返回 {"errors": [...], "warnings": [...], "counts": {...}}。"""
    settings = config["abstract"]
    headings = settings["headings"]
    lines = text.splitlines()
    errors: list[str] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}
    positions = _heading_positions(lines, headings)
    for key in HEADING_KEYS:
        if key not in positions:
            errors.append(f"缺少标题「{headings[key]}」")
    present = [k for k in HEADING_KEYS if k in positions]
    if [positions[k] for k in present] != sorted(positions[k] for k in present):
        order = " → ".join(headings[k] for k in HEADING_KEYS)
        errors.append(f"标题顺序不对，应为：{order}")
        return {"errors": errors, "warnings": warnings, "counts": counts}
    known = sorted(positions.values())

    def stop_at_known(start: int) -> int:
        return next((p for p in known if p > start), len(lines))

    if "title" in positions:
        title = _body(lines, positions["title"], stop_at_known(positions["title"]))
        counts["title_candidates"] = _check_title(title, int(settings["title_candidates"]), errors)
    if "zh" in positions:
        zh = _body(lines, positions["zh"], stop_at_known(positions["zh"]))
        counts["zh_chars"] = _check_zh(zh, int(settings["zh_max_chars"]), errors)
        if "en" in positions and positions["en"] > 0 and not lines[positions["en"] - 1].strip():
            warnings.append("中文摘要正文末行与「# English Abstract」之间不应留空行")
    if "en" in positions:
        en = _body(lines, positions["en"], _next_heading_line(lines, positions["en"]))
        counts["en_chars"] = _check_en(en, int(settings["en_max_chars"]), errors)
    if "field" in positions:
        field = _body(lines, positions["field"], _next_heading_line(lines, positions["field"]))
        counts["field_chars"] = _check_field(field, int(settings["field_max_chars"]), errors)
    return {"errors": errors, "warnings": warnings, "counts": counts}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 NSFC-ABSTRACTS.md 的格式与长度。退出码：0 通过；1 有 ERROR；2 参数或文件错误。")
    parser.add_argument("file", help="摘要文件路径，- 表示标准输入")
    parser.add_argument("--json", action="store_true", help="输出 JSON：{errors, warnings, counts}")
    args = parser.parse_args(argv)
    try:
        if args.file == "-":
            text = sys.stdin.read()
        else:
            text = Path(args.file).read_text(encoding="utf-8")
        result = check_text(text, load_config())
    except (OSError, UnicodeDecodeError, ProposalError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for message in result["errors"]:
            print(f"ERROR 摘要: {message}")
        for message in result["warnings"]:
            print(f"WARN 摘要: {message}")
        counts = "，".join(f"{k}={v}" for k, v in result["counts"].items())
        print(f"{'未通过' if result['errors'] else '通过'}（{counts}）")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
