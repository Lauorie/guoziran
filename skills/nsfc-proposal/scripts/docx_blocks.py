"""把 LaTeX 正文切成块：标题、段落、列表、图、表、公式（供 export_docx.py 调用）。"""

from __future__ import annotations

import re
from pathlib import Path

from docx_latex import HEADING_LEVELS, Block, Run, command_args, inline, math_text, read_group, strip_comments

ENV_RE = re.compile(r"\\begin\{(figure\*?|table\*?|itemize|enumerate|description|equation\*?|align\*?|gather\*?|"
                    r"tabular\*?|center|quote|quotation)\}")
HEAD_RE = re.compile(r"\\(section|subsection|subsubsection|subsubsubsection)\*?(?=\s*[\[{])")
PARAGRAPH_RE = re.compile(r"\\paragraph\*?\s*\{")
RULE_RE = re.compile(r"\\(?:toprule|midrule|bottomrule|hline|cline\s*\{[^}]*\}|cmidrule\s*(?:\([^)]*\))?\s*\{[^}]*\})")
INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")


def env_body(text: str, start: int, env: str) -> tuple[str, int]:
    """start 在 \\begin{env} 之后；按同名环境嵌套找到配对的 \\end{env}。"""
    pattern = re.compile(r"\\(begin|end)\{" + re.escape(env) + r"\}")
    depth = 1
    for m in pattern.finditer(text, start):
        depth += 1 if m.group(1) == "begin" else -1
        if depth == 0:
            return text[start:m.start()], m.end()
    return text[start:], len(text)


def _runin_paragraphs(text: str) -> str:
    """\\paragraph{标题} 是段首加粗的小标题：改写成新段落开头的加粗文字。"""
    out, pos = [], 0
    for m in PARAGRAPH_RE.finditer(text):
        if m.start() < pos:
            continue
        title, end = read_group(text, m.end() - 1)
        out.append(text[pos:m.start()] + "\n\n\\textbf{" + title.strip() + "}\u3000")
        pos = end
    return "".join(out) + text[pos:]


def _paragraphs(chunk: str) -> list[Block]:
    blocks: list[Block] = []
    pos = 0
    chunk = _runin_paragraphs(chunk)
    for m in HEAD_RE.finditer(chunk):
        if m.start() < pos:
            continue
        blocks += _plain(chunk[pos:m.start()])
        _opts, args, pos = command_args(chunk, m.end(), 1)
        runs = inline(args[0] if args else "")
        for run in runs:
            run.text = run.text.replace("\n", "")
        blocks.append(Block("heading", level=HEADING_LEVELS[m.group(1)] + 0, runs=runs))
    blocks += _plain(chunk[pos:])
    return blocks


def _plain(chunk: str) -> list[Block]:
    blocks = []
    for part in re.split(r"\n\s*\n", chunk):
        runs = inline(part.strip())
        if any((r.text.strip() or r.cite or r.ref is not None) for r in runs):
            if runs and runs[0].text:
                runs[0].text = runs[0].text.lstrip()
            blocks.append(Block("para", runs=runs))
    return blocks


def _caption_label(body: str) -> tuple[list[Run], str | None]:
    caption, label = [], None
    m = re.search(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", body)
    if m:
        text, _end = read_group(body, m.end() - 1)
        caption = inline(text)
    m = re.search(r"\\label\s*\{([^}]*)\}", body)
    if m:
        label = m.group(1).strip()
    return caption, label


def table_rows(body: str) -> list[list[list[Run]]]:
    m = re.search(r"\\begin\{tabular\*?\}", body)
    inner = env_body(body, m.end(), m.group(0)[7:-1])[0] if m else body
    inner = inner.lstrip()
    for _ in range(2 if m and m.group(0).endswith("*}") else 1):  # 列格式 {lcc}；tabular* 前面还有宽度
        if inner.startswith("{"):
            inner = inner[read_group(inner, 0)[1]:].lstrip()
    inner = RULE_RE.sub("", inner)
    rows = []
    for row in re.split(r"\\\\(?:\[[^\]]*\])?", inner):
        if not row.strip():
            continue
        cells = re.split(r"(?<!\\)&", row)
        rows.append([inline(cell.strip()) for cell in cells])
    return rows


def _env_block(env: str, body: str) -> list[Block]:
    base = env.rstrip("*")
    if base == "figure":
        caption, label = _caption_label(body)
        paths = [args[0] for args in (command_args(body, m.end(), 1)[1] for m in
                 re.finditer(r"\\includegraphics", body)) if args]
        if not paths:
            return [Block("para", runs=caption)] if caption else []
        blocks = [Block("figure", path=p.strip()) for p in paths]
        blocks[-1].runs, blocks[-1].label = caption, label
        return blocks
    if base in ("table", "tabular"):
        caption, label = _caption_label(body) if base == "table" else ([], None)
        return [Block("table", runs=caption, label=label, rows=table_rows(body if base == "table" else
                                                                           "\\begin{tabular}" + body + "\\end{tabular}"))]
    if base in ("itemize", "enumerate", "description"):
        items = []
        for part in re.split(r"\\item\b", body)[1:]:
            opts, _args, end = command_args(part, 0, 0)
            runs = (inline(opts[0], {"bold": True}) + [Run(text="\u3000")] if opts else []) + inline(part[end:].strip())
            items.append(runs)
        return [Block("list", items=items, ordered=(base == "enumerate"))]
    if base in ("equation", "align", "gather"):
        text = re.sub(r"\\label\s*\{[^}]*\}", "", body).replace("&", "").replace("\\\\", "；")
        return [Block("math", text=math_text(text))]
    return parse_chapter(body)  # center、quote：按普通正文处理


def parse_chapter(text: str) -> list[Block]:
    text = strip_comments(text)
    blocks: list[Block] = []
    pos = 0
    while True:
        m = ENV_RE.search(text, pos)
        blocks += _paragraphs(text[pos:m.start() if m else len(text)])
        if not m:
            return blocks
        body, pos = env_body(text, m.end(), m.group(1))
        blocks += _env_block(m.group(1), body)


def expand_inputs(text: str, root: Path, depth: int = 0) -> str:
    """把正文文件中嵌套的 \\input 展开（只展开项目目录内的文件，最多 5 层）。"""
    if depth > 5:
        return text

    def repl(m: re.Match) -> str:
        target = (root / m.group(1).strip()).with_suffix(".tex") if not m.group(1).strip().endswith(".tex") \
            else root / m.group(1).strip()
        target = target.resolve()
        if root.resolve() not in target.parents or not target.is_file():
            return ""
        return expand_inputs(strip_comments(target.read_text(encoding="utf-8")), root, depth + 1)

    return INPUT_RE.sub(repl, text)
