#!/usr/bin/env python3
"""跨章确定性检查（设计文档 4.7 节）。语义一致性由 AI 判断，不在本脚本内。

errors：必须修正（含没有引用台账）。needs_review：交给 AI 复核，例如疑似内部编号可能是「T1 加权」这类误报。
placeholders：正文中全部可见占位。numbers：各章带单位的数值清单，供 AI 跨章对照，不是错误，不影响退出码。退出码：0 无 errors；1 有 errors；2 输入或路径错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from case_validate import case_ids, claim_ids
from citation_ledger import entry_sha256, load_ledger
from latex_files import bib_entry_texts, read_bib_index, relpath, scan_latex_tree
from proposal_common import ProposalError, load_config, project_path, proposal_paths, read_yaml, resolve_project_root, split_latex_comment

CITE_RE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\]){0,2}\{([^}]*)\}")
NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?(?:\s?(?:---|--|[–\-~～至到])\s?\d+(?:\.\d+)?)?[\s~]?(?:\\(?=%))?"
    r"(?P<unit>mm|cm|毫米|厘米|例(?!如)|名|家|年|个月|月|%|HU|kV|mAs|层|项|个(?!别))(?![A-Za-z])"
)
SENTENCE_END = "。；！？"
SENTENCE_SPLIT_RE = re.compile(f"[{SENTENCE_END}]")
REF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|label|pageref)\{[^}]*\}")
DECIMAL_RE = re.compile(r"(?<![\d.])\d+\.\d+(?!\d)")
YEAR_RE = re.compile(r"(?:19|20)\d\d")
PROCESS_DESCRIBING_WRITER = "nsfc-proposal"  # 生成式人工智能使用说明本就描述过程，不查过程说明
DEFAULT_PLACEHOLDER = "【待补充：[^】]*】"
LABELS = {
    "hidden_placeholder": "注释中的隐藏占位",
    "placeholder_unlisted": "占位未列入 assumptions.md",
    "missing_bibkey": "引用 key 不在 .bib",
    "term_unused": "界定过的术语未在正文出现",
    "stale_section": "章节依据旧版科学论证",
    "internal_id": "疑似内部编号（请 AI 复核）",
    "file_not_compiled": "文件未被 main.tex 引用",
    "no_citation_ledger": "没有引用台账（无法核对条目来源）",
    "cite_not_in_ledger": "引用的文献不在引用台账中（手写条目？）",
    "bib_entry_modified": ".bib 条目与引用台账哈希不一致（被手改？）",
    "number_not_in_evidence": "引用句中的数字不见于所引文献摘要（请 AI 复核）",
    "no_abstract_for_numbers": "引用句含数字，但所引文献在台账中都没有摘要（请 AI 复核）",
    "process_text_in_body": "正文含写作过程说明",
    "placeholder_nonstandard": "占位写法不规范",
    "few_citations": "立项依据引用偏少",
}
JUSTIFICATION_WRITER = "nsfc-justification-writer"
DEFAULT_MIN_REFS_JUSTIFICATION = 30


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
    numbers: list[Finding] = field(default_factory=list)
    citations: dict[str, int] = field(default_factory=dict)  # 文件 -> 正文（去掉注释）引用的不同 key 数

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {name: [asdict(f) for f in getattr(self, name)] for name in ("errors", "needs_review", "placeholders", "numbers")}
        data["citations"] = dict(self.citations)
        return data


@dataclass(frozen=True)
class JoinedText:
    """一个文件逐行去注释后用换行拼接的文本。\\cite 和引用句可以跨行，在这上面查。

    starts：各行在 text 中的起点偏移；breaks：原文空行（段落分隔）的起点偏移。只含注释的行不算空行。
    """

    text: str
    starts: list[int]
    breaks: list[int]

    @classmethod
    def from_lines(cls, raw_lines: Sequence[str], bodies: Sequence[str]) -> "JoinedText":
        starts: list[int] = []
        offset = 0
        for body in bodies:
            starts.append(offset)
            offset += len(body) + 1
        breaks = [start for start, raw in zip(starts, raw_lines) if not raw.strip()]
        return cls("\n".join(bodies), starts, breaks)

    def line_of(self, pos: int) -> int:
        """偏移 pos 所在的行号（从 1 起）。"""
        return bisect_right(self.starts, pos)

    def sentences(self) -> Iterator[tuple[int, str]]:
        """按句末标点和原文空行切句，返回（句首偏移，句子）；句子可以跨行。"""
        cuts = sorted([(m.start(), m.end()) for m in SENTENCE_SPLIT_RE.finditer(self.text)] + [(b, b) for b in self.breaks])
        start = 0
        for end, resume in cuts:
            yield start, self.text[start:end]
            start = resume
        yield start, self.text[start:]


def _id_regex(ids: Iterable[str], extra_patterns: Iterable[str]) -> re.Pattern[str] | None:
    patterns = [re.escape(i) for i in sorted(ids)] + [str(p) for p in extra_patterns]
    if not patterns:
        return None
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(patterns) + r")(?![A-Za-z0-9])")


_CITED_NUMBER_RE = re.compile(
    r"(?<![\d.])(?P<a>\d+(?:\.\d+)?)(?:\s?(?P<sep>---|--|[–\-~～至到])\s?(?P<b>\d+(?:\.\d+)?))?[\s~]?(?:\\)?"
    r"(?:(?P<pct>[%％])|(?P<unit>mm|cm|毫米|厘米|例(?!如)|名|家|年|个月|月|HU|kV|mAs|层|项|个(?!别))(?![A-Za-z]))"
)
_THOUSANDS_RE = re.compile(r"(?<=\d)(?:\{,\}|\\,|,)(?=\d{3}(?!\d))")
_SPACE_THOUSANDS_RE = re.compile(r"(?<![\d,.])(\d{1,3})[ \u2009\u202f\u00a0](?=\d{3}(?!\d))")
_TRAILING_ZEROS_RE = re.compile(r"(?<![\d.])(\d+)\.(\d+)(?!\d|\.\d)")
_NUMBER_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
_NUMBER_WORD_RE = re.compile(r"(?<![\w-])(" + "|".join(w for w in _NUMBER_WORDS if w not in ("zero", "one")) + r")(?!\w|-(?:one|two|three|four|five|six|seven|eight|nine)\b)", re.IGNORECASE)
_LATEX_LENGTH_RE = re.compile(r"\s?(?:em|pt|ex)(?![A-Za-z])")


def sentence_numbers(sentence: str) -> list[str]:
    """引用句中需要对照摘要的数字：百分数（含 %）、小数、带单位的整数；排除年份、年后的月份、LaTeX 长度。"""
    text = _THOUSANDS_RE.sub("", REF_RE.sub("", CITE_RE.sub("", sentence)))
    found: list[str] = []
    spans: list[tuple[int, int]] = []
    for match in _CITED_NUMBER_RE.finditer(text):
        spans.append(match.span())
        unit = match.group("unit")
        if unit == "月" and text[: match.start()].endswith("年"):
            continue
        for group in ("a", "b"):
            digits = match.group(group)
            if not digits:
                continue
            if match.group("pct"):
                is_leading_decimal = group == "a" and match.group("sep") in ("至", "到") and "." in digits
                found.append(digits if is_leading_decimal else digits + "%")
            elif not (YEAR_RE.fullmatch(digits) and unit == "年"):
                found.append(digits)
    for match in DECIMAL_RE.finditer(text):
        if any(a <= match.start() < b for a, b in spans) or _LATEX_LENGTH_RE.match(text, match.end()):
            continue
        found.append(match.group(0))
    return list(dict.fromkeys(found))


def _evidence_readings(text: str) -> list[str]:
    """摘要的两种读法：原样，以及把空格类千分位并回；数字声称见于任一读法即算有据。"""
    text = re.sub(r"\\%", "%", text).replace("％", "%")
    text = re.sub(r"\s+%", "%", text)
    text = _NUMBER_WORD_RE.sub(lambda m: _NUMBER_WORDS[m.group(1).lower()], _THOUSANDS_RE.sub("", text))
    return [text, _SPACE_THOUSANDS_RE.sub(r"\1", text)]


def _strip_trailing_zeros(text: str) -> str:
    """0.620 -> 0.62，2.50 -> 2.5，2.00 -> 2.0（至少留一位小数，不与整数混同）；版本号式的 1.0.2 不动。"""
    def fix(match: re.Match[str]) -> str:
        return f"{match.group(1)}.{match.group(2).rstrip('0') or '0'}"
    return _TRAILING_ZEROS_RE.sub(fix, text)


def number_in_text(number: str, text: str) -> bool:
    """number 是否作为独立数字出现在 text（已规范化）中；不接受 0.91 匹配 0.913 或 10.91；0.62 与 0.620 视为同一数；英文数词 two 至 twenty（含 two-year 写法）按数字比对。"""
    wanted = _strip_trailing_zeros(number)
    pattern = re.compile(r"(?<![\d.])" + re.escape(wanted) + r"(?!\d|\.\d)")
    return any(pattern.search(_strip_trailing_zeros(reading)) for reading in _evidence_readings(text))


def sentence_containing(line: str, pos: int) -> str:
    start = max(line.rfind(c, 0, pos) for c in SENTENCE_END) + 1
    ends = [i for i in (line.find(c, pos) for c in SENTENCE_END) if i >= 0]
    return line[start: min(ends) if ends else len(line)].strip()


def _excerpt(text: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _any_of(patterns: Iterable[Any] | None) -> re.Pattern[str] | None:
    parts = [str(p) for p in patterns or [] if str(p)]
    return re.compile("|".join(f"(?:{p})" for p in parts)) if parts else None


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
    nonstandard_re = _any_of(settings.get("nonstandard_placeholder_patterns"))
    process_patterns = [str(w) for w in settings.get("process_text_patterns") or [] if str(w)]
    ledger = load_ledger(paths.ledger) if paths.ledger.exists() else None
    entry_texts = bib_entry_texts(tree.bib_files) if ledger is not None else {}
    ledger_flagged: set[tuple[str, str]] = set()
    min_refs = int(((config or load_config()).get("literature") or {}).get("min_distinct_refs_justification", DEFAULT_MIN_REFS_JUSTIFICATION))
    entries = [e for e in plan.get("files") or [] if isinstance(e, Mapping) and isinstance(e.get("file"), str)]

    report = Report()
    if ledger is None:
        report.errors.append(Finding("no_citation_ledger", "proposal/citation_ledger.jsonl", None, "没有引用台账，未核对 .bib 条目来源与引用句中的数字"))
    bodies: list[str] = []
    for entry in entries:
        rel = entry["file"]
        path = project_path(root, rel)
        if not path.is_file():
            continue
        is_tex = rel.endswith(".tex")
        if is_tex and rel not in compiled:
            report.needs_review.append(Finding("file_not_compiled", rel, None, "main.tex 未引用该文件，内容不会进入 PDF"))
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        file_bodies: list[str] = []
        for number, raw in enumerate(raw_lines, 1):
            body, comment = split_latex_comment(raw) if is_tex else (raw, "")
            file_bodies.append(body)
            if comment and any(word in comment for word in hidden_words):
                report.errors.append(Finding("hidden_placeholder", rel, number, comment.strip()[:80]))
            for match in NUMBER_RE.finditer(body):
                report.numbers.append(Finding("number", rel, number, match.group(0)))
            if id_re:
                for match in id_re.finditer(body):
                    report.needs_review.append(Finding("internal_id", rel, number, match.group(0)))
            for match in placeholder_re.finditer(body):
                report.placeholders.append(Finding("placeholder", rel, number, match.group(0)))
                if match.group(0) not in assumptions:
                    report.errors.append(Finding("placeholder_unlisted", rel, number, match.group(0)))
            if nonstandard_re:
                scanned = placeholder_re.sub("", body)
                for match in nonstandard_re.finditer(scanned):
                    detail = f"{_excerpt(scanned[match.start():], 40)}；请改成「【待补充：……】」并列入占位清单"
                    report.errors.append(Finding("placeholder_nonstandard", rel, number, detail))
            if process_patterns and entry.get("writer") != PROCESS_DESCRIBING_WRITER:
                _check_process_text(report, rel, number, placeholder_re.sub("", body), process_patterns)
        bodies.extend(file_bodies)
        if is_tex:
            joined = JoinedText.from_lines(raw_lines, file_bodies)
            cited: set[str] = set()
            for match in CITE_RE.finditer(joined.text):
                number = joined.line_of(match.start())
                for key in (k.strip() for k in match.group(1).split(",")):
                    if key:
                        cited.add(key)
                    if key and key not in bib_keys:
                        report.errors.append(Finding("missing_bibkey", rel, number, key))
                    elif key and ledger is not None:
                        _check_ledger_key(report, ledger, entry_texts, ledger_flagged, rel, number, key)
            if ledger is not None:
                _check_cite_numbers(report, ledger, rel, joined)
            report.citations[rel] = len(cited)
            if entry.get("writer") == JUSTIFICATION_WRITER and len(cited) < min_refs:
                report.needs_review.append(Finding("few_citations", rel, None, f"引用 {len(cited)} 篇不同文献，下限 {min_refs} 篇"))

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


def _check_ledger_key(report: Report, ledger: Mapping[str, Mapping[str, Any]], entry_texts: Mapping[str, str],
                      flagged: set[tuple[str, str]], rel: str, number: int, key: str) -> None:
    """被引 key 必须在台账有效记录中，且 .bib 条目哈希与台账一致；每个 key 只报一次。"""
    if key not in ledger:
        kind, detail = "cite_not_in_ledger", key
    elif ledger[key].get("entry_sha256") != entry_sha256(entry_texts.get(key, "")):
        kind, detail = "bib_entry_modified", key
    else:
        return
    if (kind, key) not in flagged:
        flagged.add((kind, key))
        report.errors.append(Finding(kind, rel, number, detail))


def _check_cite_numbers(report: Report, ledger: Mapping[str, Mapping[str, Any]], rel: str, joined: JoinedText) -> None:
    """逐句（可跨行）对照引用句中的数字与所引文献的台账摘要；行号取句首所在行。"""
    for start, sentence in joined.sentences():
        keys = [k.strip() for m in CITE_RE.finditer(sentence) for k in m.group(1).split(",") if k.strip()]
        numbers = sentence_numbers(sentence) if keys else []
        if not numbers:
            continue
        number = joined.line_of(start + len(sentence) - len(sentence.lstrip()))
        abstracts = [str(ledger[k]["abstract"]) for k in keys if k in ledger and ledger[k].get("abstract")]
        excerpt = _excerpt(sentence)
        if not abstracts:
            report.needs_review.append(Finding("no_abstract_for_numbers", rel, number, f"{'、'.join(numbers)}：{excerpt}"))
            continue
        for value in numbers:
            if not any(number_in_text(value, text) for text in abstracts):
                report.needs_review.append(Finding("number_not_in_evidence", rel, number, f"{value}：{excerpt}"))


def _check_process_text(report: Report, rel: str, number: int, text: str, patterns: list[str]) -> None:
    """正文（占位已删）里的写作过程说明；同一句的多个命中合并为一条。"""
    reported: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(re.escape(pattern), text):
            sentence = sentence_containing(text, match.start())
            if sentence in reported:
                continue
            reported.add(sentence)
            hits = [p for p in patterns if p in sentence]
            report.needs_review.append(Finding("process_text_in_body", rel, number, f"命中「{'、'.join(hits)}」：{_excerpt(sentence)}"))


def _print_numbers(report: Report) -> None:
    groups: dict[str, list[Finding]] = {}
    for f in report.numbers:
        match = NUMBER_RE.search(f.detail)
        groups.setdefault(match.group("unit") if match else "?", []).append(f)
    print(f"## 数值清单（{len(report.numbers)}）")
    for unit, items in groups.items():
        print(f"### {unit}（{len(items)}）")
        for f in items:
            print(f"- {f.file}:{f.line} {f.detail}")


def _print_human(report: Report) -> None:
    for title, items in (("必须修正", report.errors), ("需要复核", report.needs_review)):
        print(f"## {title}（{len(items)}）")
        for f in items:
            where = f"{f.file}:{f.line}" if f.line else (f.file or "全文")
            print(f"- [{LABELS.get(f.kind, f.kind)}] {where} {f.detail}")
    print(f"## 正文占位（{len(report.placeholders)}）")
    for f in report.placeholders:
        print(f"- {f.file}:{f.line} {f.detail}")
    counts = "；".join(f"{file} {n}" for file, n in report.citations.items())
    print(f"各章引用的不同文献数：{counts or '无'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="consistency_check.py", description="nsfc-proposal 跨章一致性检查")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（numbers 总在其中）")
    parser.add_argument("--numbers", action="store_true", help="人类可读输出末尾追加数值清单")
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
        if args.numbers:
            _print_numbers(report)
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
