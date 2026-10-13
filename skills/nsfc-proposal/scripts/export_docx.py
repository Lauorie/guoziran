#!/usr/bin/env python3
"""把 NSFC 正文项目导出为一个 Word 文档：按 main.tex 的提纲与 \\input 顺序写各章，引用按出现顺序编号，
参考文献按 GB/T 7714 写在 \\bibliography 所在位置，图按原尺寸比例插入，最后附题目与中英文摘要。

不编译 LaTeX，不打开 PDF。需要 python-docx（缺时退出码 3，先 pip install --user python-docx）。
输出：P/<config.yaml 的 export.docx_name>（默认 申请书正文.docx）；标准输出给出一行 JSON 汇总。
退出码：0 已导出（有警告也算）；2 参数或项目错误；3 缺 python-docx。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from docx_bib import cite_label, parse_bib, reference_text  # noqa: F401  cite_label 供测试引用
from docx_blocks import expand_inputs, parse_chapter
from docx_latex import Block, Run, command_args, inline, strip_comments
from latex_files import scan_latex_tree
from proposal_common import ProposalError, load_config, resolve_project_root

MAIN_RE = re.compile(r"\\(section|subsection|subsubsection)\*?(?=\s*[\[{])|\\(input|include)\s*\{([^}]+)\}|"
                     r"\\(bibliography|printbibliography)\b")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
CJK_RE = re.compile(r"[\u3400-\u9fff]")
MD_HEADING_RE = re.compile(r"^#{1,3}\s+(.*)$")
CHARS_PER_PAGE = 700  # Word 版（小四、1.25 倍行距、含图）实测约每页 700 个汉字


def document_blocks(root: Path) -> tuple[list[Block], list[str]]:
    """按 main.tex 的顺序收集块：提纲标题、各章正文、参考文献位置。返回（块, 被引入的文件相对路径）。"""
    main = strip_comments((root / "main.tex").read_text(encoding="utf-8"))
    begin, end = main.find("\\begin{document}"), main.find("\\end{document}")
    body = main[begin + len("\\begin{document}"): end if end > 0 else len(main)] if begin >= 0 else main
    blocks: list[Block] = []
    inputs: list[str] = []
    for m in MAIN_RE.finditer(body):
        if m.group(1):
            _opts, args, _ = command_args(body, m.end(), 1)
            runs = inline(args[0] if args else "")
            for run in runs:
                run.text = run.text.replace("\n", "")
            blocks.append(Block("heading", level={"section": 1, "subsection": 2, "subsubsection": 3}[m.group(1)],
                                runs=runs))
        elif m.group(2):
            rel = m.group(3).strip()
            path = (root / (rel if rel.endswith(".tex") else rel + ".tex")).resolve()
            if root.resolve() not in path.parents or not path.is_file():
                continue
            inputs.append(path.relative_to(root.resolve()).as_posix())
            text = strip_comments(path.read_text(encoding="utf-8"))
            if re.search(r"\\(bibliography|printbibliography)\b", text):
                blocks.append(Block("bibliography"))
                continue
            blocks += parse_chapter(expand_inputs(text, root))
        else:
            blocks.append(Block("bibliography"))
    return blocks, inputs


def _all_runs(blocks: Iterable[Block]) -> Iterable[Run]:
    for block in blocks:
        yield from block.runs
        for item in block.items:
            yield from item
        for row in block.rows:
            for cell in row:
                yield from cell


def number_things(blocks: list[Block]) -> tuple[dict[str, int], dict[str, str]]:
    """引用按首次出现编号；图、表各自按出现顺序编号，标签映射到编号。"""
    cites: dict[str, int] = {}
    labels: dict[str, str] = {}
    counters = {"figure": 0, "table": 0}
    for block in blocks:
        numbered = block.kind == "table" or (block.kind == "figure" and (block.runs or block.label))
        if numbered:
            counters[block.kind] += 1
            block.text = str(counters[block.kind])  # 写 Word 时用作图号、表号
            if block.label:
                labels[block.label] = block.text
        for run in _all_runs([block]):
            for key in run.cite:
                cites.setdefault(key, len(cites) + 1)
    return cites, labels


def _bib_entries(root: Path) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for path in scan_latex_tree(root).bib_files:
        if path.is_file():
            for key, value in parse_bib(path.read_text(encoding="utf-8")).items():
                entries.setdefault(key, value)
    return entries


def _abstract_sections(path: Path) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = MD_HEADING_RE.match(line.strip())
        if m:
            sections.append((m.group(1).strip(), []))
        elif sections and line.strip():
            sections[-1][1].append(line.strip())
    return sections


def export(project_root: Path | str, out: Path | str | None = None, *, config: dict | None = None) -> dict[str, Any]:
    try:
        import docx_writer
    except ImportError as exc:  # python-docx 缺失
        raise ModuleNotFoundError(str(exc)) from exc
    root = resolve_project_root(project_root)
    if not (root / "main.tex").is_file():
        raise ProposalError(f"项目中没有 main.tex：{root}")
    cfg = (config if config is not None else load_config()).get("export") or {}
    target = Path(out) if out else root / str(cfg.get("docx_name") or "申请书正文.docx")
    blocks, inputs = document_blocks(root)
    cites, labels = number_things(blocks)
    entries = _bib_entries(root)
    warnings: list[str] = []
    missing_keys = [k for k in cites if k not in entries]
    if missing_keys:
        warnings.append(f".bib 中找不到 {len(missing_keys)} 个引用键：{'、'.join(missing_keys[:10])}")
    references = [(n, reference_text(entries[k]) if k in entries else f"【待补充：参考文献 {k} 不在 .bib 中】")
                  for k, n in sorted(cites.items(), key=lambda kv: kv[1])]
    appendix: list[tuple[str, list[tuple[str, list[str]]]]] = []
    abstracts = root / "NSFC-ABSTRACTS.md"
    if abstracts.is_file():
        appendix.append(("附：题目与摘要", _abstract_sections(abstracts)))
    declaration = root / "proposal" / "ai_declaration.md"
    if declaration.is_file() and not any("生成式人工智能" in rel for rel in inputs):
        appendix.append(("附：生成式人工智能使用说明（请核对后放入申请书的相应位置）", _abstract_sections(declaration)
                         or [("", [l.strip() for l in declaration.read_text(encoding="utf-8").splitlines() if l.strip()])]))
    stats = docx_writer.write(target, blocks, cites=cites, labels=labels, references=references, appendix=appendix,
                              root=root, superscript=bool(cfg.get("cite_superscript", True)), warnings=warnings)
    cjk = sum(len(CJK_RE.findall(r.text)) for r in _all_runs(blocks))
    return {"docx": str(target), "chapters": len(inputs), "citations": len(cites), "references": len(references),
            **stats, "cjk_chars": cjk, "estimated_pages": math.ceil(cjk / CHARS_PER_PAGE) if cjk else 0,
            "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把 NSFC 正文项目导出为 Word（申请书正文.docx）")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--out", help="输出路径；默认 P/申请书正文.docx")
    args = parser.parse_args(argv)
    try:
        summary = export(args.project_root, args.out)
    except ModuleNotFoundError:
        print("缺少 python-docx：先运行 pip install --user python-docx，再重跑本命令", file=sys.stderr)
        return 3
    except (ProposalError, OSError, UnicodeDecodeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
