#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""与 LaTeX 语法无关的预览/写入范围检查。"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence


STRUCTURE_COMMAND_RE = re.compile(
    r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|input|include|begin|end|label|newcommand|renewcommand|documentclass|usepackage)\b"
)


@dataclass(frozen=True)
class ChangeGuardResult:
    ok: bool
    changed_lines: int
    structural_hits: List[str]
    diff: str


def inspect_proposal(
    *,
    original: str,
    proposed: str,
    target_path: Path,
    project_root: Path,
    allowed_new_headings: Sequence[str] = (),
) -> ChangeGuardResult:
    """生成 diff，并提示新增/删除行是否触碰结构或配置命令。

    ``allowed_new_headings`` 列出允许出现在新增行中的标题命令（如 ``subsubsection``）。
    删除行中的结构命令一律计入 hits，所以删改已有标题仍会被拒绝。
    """
    root = Path(project_root).resolve()
    target = Path(target_path).resolve()
    target.relative_to(root)  # 越界时抛出 ValueError，由 CLI 转成安全错误
    diff_lines = list(
        difflib.unified_diff(
            (original or "").splitlines(),
            (proposed or "").splitlines(),
            fromfile=str(target),
            tofile=str(target),
            lineterm="",
        )
    )
    allowed = {"\\" + name.strip().lstrip("\\") for name in allowed_new_headings if name and name.strip()}
    hits: set[str] = set()
    changed_lines = 0
    for line in diff_lines:
        if line.startswith(("+++", "---")) or not line.startswith(("+", "-")):
            continue
        changed_lines += 1
        is_added = line.startswith("+")
        for match in STRUCTURE_COMMAND_RE.finditer(line[1:]):
            command = match.group(0)
            if is_added and command in allowed:
                continue
            hits.add(command)
    return ChangeGuardResult(
        ok=not hits,
        changed_lines=changed_lines,
        structural_hits=sorted(hits),
        diff="\n".join(diff_lines) + ("\n" if diff_lines else ""),
    )
