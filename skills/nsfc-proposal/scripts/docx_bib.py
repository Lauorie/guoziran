"""读 .bib 并按 GB/T 7714—2015 顺序编码制写参考文献条目（供 export_docx.py 调用）。

解析器要容忍申请人上传的 .bib：字段值可用花括号、双引号或裸数字，大小写混用，条目间有注释。
只做排版，不补任何字段：缺的字段就不写，不凭记忆补。
"""

from __future__ import annotations

import re
from typing import Iterable, Iterator

ENTRY_RE = re.compile(r"@([A-Za-z]+)\s*[{(]\s*([^,\s]+)\s*,", re.S)
SKIP_TYPES = {"comment", "string", "preamble"}
CJK_RE = re.compile(r"[\u3400-\u9fff]")
TYPE_MARKS = {"article": "J", "inproceedings": "C", "conference": "C", "incollection": "M", "book": "M",
              "phdthesis": "D", "mastersthesis": "D", "techreport": "R", "misc": "Z", "online": "EB/OL"}
LATEX_TEXT = [(r"\&", "&"), (r"\%", "%"), (r"\_", "_"), (r"\#", "#"), (r"\$", "$"), ("~", " "), ("--", "–")]


def _scan_value(text: str, i: int) -> tuple[str, int]:
    """从 i 开始读一个字段值（{...}、"..." 或裸词），返回（值, 结束位置）。"""
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        return "", i
    if text[i] == "{":
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{" and (j == 0 or text[j - 1] != "\\"):
                depth += 1
            elif text[j] == "}" and text[j - 1] != "\\":
                depth -= 1
                if depth == 0:
                    return text[i + 1:j], j + 1
            j += 1
        return text[i + 1:], len(text)
    if text[i] == '"':
        j = i + 1
        while j < len(text) and not (text[j] == '"' and text[j - 1] != "\\"):
            j += 1
        return text[i + 1:j], j + 1
    m = re.match(r"[^,}\s]+", text[i:])
    return (m.group(0), i + m.end()) if m else ("", i)


def _entry_body(text: str, start: int) -> tuple[str, int]:
    """条目从「@type{」后开始，按括号配对找到结尾。"""
    depth, j = 1, start
    while j < len(text) and depth:
        if text[j] in "{(":
            depth += 1
        elif text[j] in "})":
            depth -= 1
        j += 1
    return text[start:j - 1], j


def parse_bib(text: str) -> dict[str, dict[str, str]]:
    """返回 {key: {"_type": 类型, 字段名小写: 值}}；同一 key 出现多次时取第一次。"""
    entries: dict[str, dict[str, str]] = {}
    pos = 0
    for match in ENTRY_RE.finditer(text):
        if match.start() < pos:
            continue
        kind, key = match.group(1).lower(), match.group(2).strip()
        body, pos = _entry_body(text, match.end())
        if kind in SKIP_TYPES or key in entries:
            continue
        fields: dict[str, str] = {"_type": kind}
        i = 0
        while i < len(body):
            m = re.compile(r"\s*,?\s*([A-Za-z][\w-]*)\s*=").match(body, i)
            if not m:
                break
            value, i = _scan_value(body, m.end())
            fields[m.group(1).lower()] = re.sub(r"\s+", " ", value).strip()
        entries[key] = fields
    return entries


def clean(text: str) -> str:
    """去掉 BibTeX 的保护括号与常见转义。"""
    for old, new in LATEX_TEXT:
        text = text.replace(old, new)
    text = re.sub(r"\\[a-zA-Z]+\s*\{([^{}]*)\}", r"\1", text)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()


def _western(name: str) -> str:
    """「Family, Given」或「Given Family」→「Family G M」。"""
    name = re.sub(r"\([^)]*\)", "", clean(name)).strip()  # 去掉括号里的昵称，如 Shixiang (Shane)
    if "," in name:
        family, given = [part.strip() for part in name.split(",", 1)]
    else:
        parts = name.split()
        family, given = (parts[-1], " ".join(parts[:-1])) if len(parts) > 1 else (name, "")
    initials = " ".join(p[0].upper() for p in re.split(r"[\s.-]+", given) if p)
    return f"{family} {initials}".strip()


def format_authors(raw: str) -> str:
    names = [n.strip() for n in re.split(r"\s+and\s+", raw or "") if n.strip()]
    if not names:
        return ""
    chinese = any(CJK_RE.search(n) for n in names)
    shown = [clean(n).replace(",", "") if CJK_RE.search(n) else _western(n) for n in names[:3]]
    text = ", ".join(shown)
    if len(names) > 3:
        text += ", 等" if chinese else ", et al"
    return text


def reference_text(entry: dict[str, str]) -> str:
    """一条参考文献，GB/T 7714 顺序编码制；缺的字段跳过。"""
    kind = entry.get("_type", "misc")
    mark = "EB/OL" if kind == "misc" and entry.get("url") else TYPE_MARKS.get(kind, "Z")  # 预印本等网络文献
    authors = format_authors(entry.get("author", ""))
    title = clean(entry.get("title", ""))
    year = clean(entry.get("year", ""))
    head = f"{authors}. {title}[{mark}]" if authors else f"{title}[{mark}]"
    if kind == "article":
        tail = clean(entry.get("journal", ""))
        if year:
            tail = f"{tail}, {year}" if tail else year
        volume, number = clean(entry.get("volume", "")), clean(entry.get("number", ""))
        pages = clean(entry.get("pages", "").replace("--", "-"))
        if volume:
            tail += f", {volume}"
        if number:
            tail += f"({number})"
        if pages:
            tail += f": {pages}"
    elif kind in ("inproceedings", "conference", "incollection"):
        tail = "//" + clean(entry.get("booktitle", "")) if entry.get("booktitle") else ""
        place = ", ".join(x for x in (clean(entry.get("publisher", "")), year) if x)
        tail = f"{tail}. {place}" if place else tail
        if entry.get("pages"):
            tail += f": {clean(entry['pages'].replace('--', '-'))}"
    elif kind in ("phdthesis", "mastersthesis"):
        tail = ", ".join(x for x in (clean(entry.get("school", "")), year) if x)
    else:
        tail = ", ".join(x for x in (clean(entry.get("howpublished", "")), clean(entry.get("publisher", "")), year) if x)
    joiner = "" if tail.startswith("//") else ". "
    text = f"{head}{joiner}{tail}".rstrip(". ") if tail else head
    doi = clean(entry.get("doi", ""))
    text = text.rstrip(".") + "."
    if doi:
        return f"{text} DOI: {doi}."
    url = entry.get("url", "").strip()
    return f"{text} {url}." if mark == "EB/OL" and url else text


def iter_bib_keys(command_args: str) -> Iterator[str]:
    for key in command_args.split(","):
        key = key.strip()
        if key:
            yield key


def cite_label(keys: Iterable[str], cites: dict[str, int]) -> str:
    numbers = sorted({cites[k] for k in keys if k in cites})
    if not numbers:
        return "[?]"
    parts, start = [], numbers[0]
    for prev, cur in zip(numbers, numbers[1:] + [None]):
        if cur != prev + 1:
            parts.append(str(start) if start == prev else (f"{start},{prev}" if prev == start + 1 else f"{start}-{prev}"))
            start = cur
    return "[" + ",".join(parts) + "]"
