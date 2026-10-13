"""把本 skill 写出的 LaTeX 正文转成段落块（供 export_docx.py 写 Word）。

覆盖本 skill 与常见 NSFC 模板用到的写法：各级标题（含 \\subsubsubsection、\\paragraph）、段落、加粗与斜体、
\\cite、\\ref、图（\\includegraphics + \\caption + \\label）、tabular 表格、itemize/enumerate、行内与行间公式。
认不出的命令保留其花括号里的文字，丢掉命令名；不改写正文内容。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

HEADING_LEVELS = {"section": 1, "subsection": 2, "subsubsection": 3, "subsubsubsection": 4}
DROP_ARG_COMMANDS = {"label", "vspace", "hspace", "setlength", "addtolength", "bibliographystyle", "includegraphics",
                     "caption", "pagestyle", "thispagestyle", "phantom", "color", "zihao", "linespread", "begin", "end",
                     "input", "include", "bibliography", "punctstyle", "fontsize", "setcounter", "titleformat",
                     "titlespacing", "renewcommand", "newcommand"}
INLINE_STYLES = {"textbf": "bold", "textit": "italic", "emph": "italic", "textsl": "italic", "underline": "underline"}
CITE_COMMANDS = {"cite", "citep", "citet", "upcite", "supercite", "parencite", "textcite", "citeauthor"}
REF_COMMANDS = {"ref", "autoref", "eqref", "cref", "Cref"}
SYMBOLS = {r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\epsilon": "ε", r"\varepsilon": "ε",
           r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ", r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ",
           r"\phi": "φ", r"\varphi": "φ", r"\chi": "χ", r"\omega": "ω", r"\Delta": "Δ", r"\Sigma": "Σ", r"\Omega": "Ω",
           r"\times": "×", r"\cdot": "·", r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\neq": "≠",
           r"\approx": "≈", r"\pm": "±", r"\sim": "∼", r"\infty": "∞", r"\rightarrow": "→", r"\to": "→",
           r"\leftarrow": "←", r"\ldots": "…", r"\cdots": "…", r"\%": "%", r"\degree": "°", r"\circ": "°"}
SUPERSCRIPT = str.maketrans("0123456789+-()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿ")
SUBSCRIPT = str.maketrans("0123456789+-()", "₀₁₂₃₄₅₆₇₈₉₊₋₍₎")
ESCAPES = {"%": "%", "&": "&", "_": "_", "#": "#", "$": "$", "{": "{", "}": "}", " ": " ", ",": " ", ";": " ",
           "!": "", "/": "", "\\": "\n"}
PLACEHOLDER_RE = re.compile(r"(【待补充[^】]*】)")


@dataclass
class Run:
    text: str = ""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    cite: tuple[str, ...] = ()     # 非空时这是一处引用，text 由导出时按编号填写
    ref: str | None = None         # 非空时这是一处图表引用
    placeholder: bool = False


@dataclass
class Block:
    kind: str                      # heading / para / list / figure / table / math / bibliography
    level: int = 0
    runs: list[Run] = field(default_factory=list)
    items: list[list[Run]] = field(default_factory=list)
    ordered: bool = False
    path: str | None = None
    label: str | None = None
    rows: list[list[list[Run]]] = field(default_factory=list)
    text: str = ""


def strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        i = 0
        while True:
            i = line.find("%", i)
            if i < 0:
                out.append(line)
                break
            backslashes = len(line[:i]) - len(line[:i].rstrip("\\"))
            if backslashes % 2 == 0:
                out.append(line[:i])
                break
            i += 1
    return "\n".join(out)


def read_group(text: str, i: int, open_ch: str = "{", close_ch: str = "}") -> tuple[str, int]:
    """text[i] 是开括号；返回（括号内文字, 闭括号后的位置）。没有配对时读到结尾。"""
    depth, j = 0, i
    while j < len(text):
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return text[i + 1:], len(text)


def skip_spaces(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t":
        i += 1
    return i


def command_args(text: str, i: int, max_args: int = 9) -> tuple[list[str], list[str], int]:
    """读命令后的 [可选] 与 {必选} 参数；返回（可选参数, 必选参数, 结束位置）。"""
    opts, args = [], []
    while len(args) < max_args:
        k = skip_spaces(text, i)
        if k < len(text) and text[k] == "[" and not args:
            value, i = read_group(text, k, "[", "]")
            opts.append(value)
        elif k < len(text) and text[k] == "{":
            value, i = read_group(text, k)
            args.append(value)
        else:
            break
    return opts, args, i


def math_text(src: str) -> str:
    text = re.sub(r"\\(?:mathrm|text|mathbf|mathit|operatorname|textrm)\s*\{([^{}]*)\}", r"\1", src)
    text = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", text)
    text = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", text)
    for name in sorted(SYMBOLS, key=len, reverse=True):
        text = re.sub(re.escape(name) + r"(?![A-Za-z])", SYMBOLS[name], text)
    text = re.sub(r"\\left|\\right|\\,|\\;|\\!|\\quad|\\qquad", " ", text)
    text = re.sub(r"\^\{([0-9+\-()n]+)\}|\^([0-9n])", lambda m: (m.group(1) or m.group(2)).translate(SUPERSCRIPT), text)
    text = re.sub(r"_\{([0-9+\-()]+)\}|_([0-9])", lambda m: (m.group(1) or m.group(2)).translate(SUBSCRIPT), text)
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text).replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()


def _text_run(text: str, style: dict[str, bool]) -> list[Run]:
    runs = []
    for part in PLACEHOLDER_RE.split(text):
        if part:
            runs.append(Run(text=part, placeholder=bool(PLACEHOLDER_RE.fullmatch(part)), **style))
    return runs


def inline(text: str, style: dict[str, bool] | None = None) -> list[Run]:
    """把一段 LaTeX 行内文字转成 Run 列表。"""
    style = dict(style or {})
    runs: list[Run] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            runs.extend(_text_run("".join(buf), style))
            buf.clear()

    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            m = re.match(r"\\([A-Za-z]+)\*?", text[i:])
            if not m:
                nxt = text[i + 1:i + 2]
                buf.append(ESCAPES.get(nxt, nxt))
                i += 2
                continue
            name, i = m.group(1), skip_spaces(text, i + m.end())  # 控制词后的空格不出现在排版结果里
            if name in CITE_COMMANDS:
                _opts, args, i = command_args(text, i, 1)
                flush()
                keys = tuple(k.strip() for k in (args[0] if args else "").split(",") if k.strip())
                runs.append(Run(cite=keys, **style))
            elif name in REF_COMMANDS:
                _opts, args, i = command_args(text, i, 1)
                flush()
                runs.append(Run(ref=(args[0].strip() if args else ""), **style))
            elif name in INLINE_STYLES:
                _opts, args, i = command_args(text, i, 1)
                flush()
                runs.extend(inline(args[0] if args else "", {**style, INLINE_STYLES[name]: True}))
            elif name == "href":
                _opts, args, i = command_args(text, i, 2)
                buf.append(args[1] if len(args) > 1 else (args[0] if args else ""))
            elif name in ("url", "texttt", "nolinkurl"):
                _opts, args, i = command_args(text, i, 1)
                buf.append(args[0] if args else "")
            elif name == "footnote":
                _opts, args, i = command_args(text, i, 1)
                flush()
                runs.extend(inline(f"（{args[0]}）" if args else "", style))
            elif name in DROP_ARG_COMMANDS:
                _opts, _args, i = command_args(text, i)
            elif "\\" + name in SYMBOLS:
                buf.append(SYMBOLS["\\" + name])
            elif name in ("par", "newline"):
                buf.append("\n")
            elif name in ("linebreak", "allowbreak", "nobreak"):
                pass  # 模板为排版加的断行，Word 里自动换行
            else:
                _opts, args, i = command_args(text, i)
                flush()
                for arg in args[-1:]:  # 保留最后一个参数的文字（如 \texorpdfstring 取第二个）
                    runs.extend(inline(arg, style))
        elif ch == "$":
            j = text.find("$", i + 1)
            j = len(text) if j < 0 else j
            buf.append(math_text(text[i + 1:j]))
            i = j + 1
        elif ch == "{":
            inner, i = read_group(text, i)
            flush()
            runs.extend(inline(inner, style))
        elif ch == "}":
            i += 1
        elif ch == "~":
            buf.append("\u00a0")
            i += 1
        elif text.startswith("---", i):
            buf.append("—")
            i += 3
        elif text.startswith("--", i):
            buf.append("–")
            i += 2
        elif text.startswith("``", i):
            buf.append("“")
            i += 2
        elif text.startswith("''", i):
            buf.append("”")
            i += 2
        else:
            buf.append(ch)
            i += 1
    flush()
    return _merge_spaces(runs)


CJK_CHAR = r"[\u3000-\u9fff\uff00-\uffef]"


def _merge_spaces(runs: list[Run]) -> list[Run]:
    """LaTeX 源码里的换行与连续空白折成一个空格；汉字之间的空格去掉，跨相邻片段也去掉。"""
    for run in runs:
        if run.text and not run.cite and run.ref is None:
            text = re.sub(r"[ \t]*\n[ \t]*(?!\n)", " ", run.text)
            text = re.sub(r"[ \t]{2,}", " ", text)
            run.text = re.sub(f"(?<={CJK_CHAR}) (?={CJK_CHAR})", "", text)
    runs = [r for r in runs if r.text or r.cite or r.ref is not None]
    for left, right in zip(runs, runs[1:]):
        if left.cite or right.cite or left.ref is not None or right.ref is not None:
            continue
        if left.text.endswith(" ") and re.search(f"{CJK_CHAR} $", left.text) and re.match(CJK_CHAR, right.text):
            left.text = left.text[:-1]
        elif right.text.startswith(" ") and re.search(f"{CJK_CHAR}$", left.text) and re.match(f" {CJK_CHAR}", right.text):
            right.text = right.text[1:]
    return [r for r in runs if r.text or r.cite or r.ref is not None]
