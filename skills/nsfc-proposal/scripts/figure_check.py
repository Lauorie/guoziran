"""一致性检查中与 \\includegraphics 有关的部分：找出指向不存在文件的命令，以及在过程说明扫描前删去这些命令。

都在逐行去注释、跨行拼接后的文本上进行。支持 \\includegraphics*、命令与 [ 之间的空白、] 与 { 之间的空白或换行。
"""

from __future__ import annotations

import re
from pathlib import Path

from proposal_common import ProposalError, project_path

INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics\*?\s*(\[[^\]]*\])?\s*\{([^}]*)\}")
FIGURE_EXTENSIONS = (".png", ".pdf", ".jpg", ".jpeg")


def figure_found(root: Path, arg: str) -> bool:
    """路径相对 P 解析，须仍在 P 内；原样找不到时依次加 .png、.pdf、.jpg、.jpeg 再找。"""
    if not arg:
        return False
    try:
        return any(project_path(root, arg + ext).is_file() for ext in ("", *FIGURE_EXTENSIONS))
    except ProposalError:
        return False


def missing_figures(root: Path, text: str) -> list[tuple[int, str]]:
    """text 中指向不存在文件的 \\includegraphics：返回（命令起点偏移，detail），detail 写参数与命令原文。"""
    found = []
    for match in INCLUDEGRAPHICS_RE.finditer(text):
        arg = match.group(2).strip()
        if not figure_found(root, arg):
            command = re.sub(r"\s+", " ", match.group(0))
            found.append((match.start(), f"{arg or '（空）'}：{command}"))
    return found


def strip_includegraphics(text: str) -> str:
    """删去 \\includegraphics 命令，保留其中的换行，使行号不变。图片路径含 nsfc-proposal/，不算过程说明。"""
    return INCLUDEGRAPHICS_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
