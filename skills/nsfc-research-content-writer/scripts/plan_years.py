"""按项目类型定研究期限（年）。

年数表只写在本 skill 的 config.yaml（yearly_plan 段）。nsfc-proposal 用 importlib 按路径加载本文件，
所以这里只依赖标准库和 PyYAML，不导入同目录的其他模块。
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import NamedTuple

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"
CN_NUMERALS = "一二三四五六七八九十"


class YearlyPlan(NamedTuple):
    """config.yaml 的 yearly_plan 段：按顺序匹配的（关键词, 年数），默认年数，年数上限。"""

    rules: tuple[tuple[str, int], ...]
    default_years: int
    max_years: int


def _int_in_range(value: object, low: int, high: int, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"config.yaml yearly_plan: {what} must be an integer in {low}..{high}, got {value!r}")
    return value


def load_yearly_plan(config_path: Path | None = None) -> YearlyPlan:
    """读取并校验 yearly_plan；缺段、写法不对或年数超出 1..max_years 时抛 ValueError。"""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read {path.name}: {exc}") from exc
    section = data.get("yearly_plan") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        raise ValueError(f"{path.name} missing yearly_plan")
    max_years = _int_in_range(section.get("max_years"), 1, len(CN_NUMERALS), "max_years")
    default_years = _int_in_range(section.get("default_years"), 1, max_years, "default_years")
    entries = section.get("duration_by_keyword")
    if not isinstance(entries, list) or not entries:
        raise ValueError("config.yaml yearly_plan: duration_by_keyword must be a non-empty list of [keyword, years]")
    rules = []
    for entry in entries:
        if not (isinstance(entry, list) and len(entry) == 2 and isinstance(entry[0], str) and normalize_type(entry[0])):
            raise ValueError(f"config.yaml yearly_plan: bad duration_by_keyword entry {entry!r}")
        rules.append((entry[0].strip(), _int_in_range(entry[1], 1, max_years, f"years for {entry[0]!r}")))
    return YearlyPlan(tuple(rules), default_years, max_years)


def normalize_type(text: str) -> str:
    """NFKC 规范化并去掉所有空白：「（Ａ 类）」与「(A类)」视为相同。"""
    return "".join(unicodedata.normalize("NFKC", text).split())


def duration_years(project_type: str, config_path: Path | None = None) -> tuple[int, bool]:
    """返回（年数, 是否命中关键词）。

    项目类型与表中关键词都先规范化（normalize_type）再比较；按表中顺序匹配，先命中先用；
    都不命中时用 default_years。
    """
    plan = load_yearly_plan(config_path)
    text = normalize_type(project_type) if isinstance(project_type, str) else ""
    for keyword, years in plan.rules:
        if normalize_type(keyword) in text:
            return years, True
    return plan.default_years, False


def year_label(year: int) -> str:
    """「第4年/第四年」形式的标签；十年以上只给阿拉伯数字写法。"""
    if 1 <= year <= len(CN_NUMERALS):
        return f"第{year}年/第{CN_NUMERALS[year - 1]}年"
    return f"第{year}年"
