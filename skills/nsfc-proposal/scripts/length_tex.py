"""LaTeX 篇幅统计的文本解析：去注释、取可见文本、按章节切分、沿 main.tex 收集被编译的文件。"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Iterable

from proposal_common import ProposalError


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def strip_tex_comments(text: str) -> str:
    out_lines: list[str] = []
    for line in text.splitlines():
        buf: list[str] = []
        escaped = False
        for ch in line:
            if escaped:
                buf.append(ch)
                escaped = False
                continue
            if ch == "\\":
                buf.append(ch)
                escaped = True
                continue
            if ch == "%":
                break
            buf.append(ch)
        out_lines.append("".join(buf))
    return "\n".join(out_lines)


def mask_tex_comments(text: str) -> str:
    """Replace TeX comments with spaces, preserving string length.

    Useful when we need stable character offsets (e.g. for section splitting).
    """

    out_lines: list[str] = []
    for line in text.splitlines(keepends=False):
        buf: list[str] = []
        escaped = False
        in_comment = False
        for ch in line:
            if in_comment:
                buf.append(" ")
                continue
            if escaped:
                buf.append(ch)
                escaped = False
                continue
            if ch == "\\":
                buf.append(ch)
                escaped = True
                continue
            if ch == "%":
                buf.append(" ")
                in_comment = True
                continue
            buf.append(ch)
        out_lines.append("".join(buf))
    return "\n".join(out_lines)


_RE_MATH_INLINE = re.compile(r"\$(?:\\.|[^$\\])*\$")
_RE_MATH_PAREN = re.compile(r"\\\((?:.|\n)*?\\\)")
_RE_MATH_BRACK = re.compile(r"\\\[(?:.|\n)*?\\\]")
_RE_COMMAND = re.compile(r"\\[A-Za-z@]+\*?")
_RE_ENV = re.compile(r"\\(begin|end)\s*\{[^}]+\}")


def tex_visible_text(text: str, *, strip_math: bool, strip_commands: bool) -> str:
    text = strip_tex_comments(text)
    text = _RE_ENV.sub(" ", text)
    if strip_math:
        text = _RE_MATH_BRACK.sub(" ", text)
        text = _RE_MATH_PAREN.sub(" ", text)
        text = _RE_MATH_INLINE.sub(" ", text)
    if strip_commands:
        text = _RE_COMMAND.sub(" ", text)
    text = text.replace("~", " ")
    text = text.replace("\\\\", " ")
    text = re.sub(r"[{}\[\]]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def md_visible_text(text: str) -> str:
    # Extremely lightweight markdown text extraction.
    text = re.sub(r"```(?:.|\n)*?```", " ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^\)]+\)", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def count_unit(text: str, unit: str) -> int:
    if not text:
        return 0
    if unit == "cjk_chars":
        return len(re.findall(r"[\u4e00-\u9fff]", text))
    if unit == "chars":
        return len(re.sub(r"\s+", "", text))
    raise ProposalError(f"不支持的篇幅单位：{unit!r}（支持 cjk_chars、chars）")

def count_all_units(text: str) -> dict[str, int]:
    return {
        "cjk_chars": count_unit(text, "cjk_chars"),
        "chars": count_unit(text, "chars"),
    }


def read_balanced_braces(text: str, brace_start: int) -> tuple[str, int] | None:
    """Return (inner_text, end_idx_after_closing_brace) for a {...} block.

    This is a minimal TeX-ish brace reader to make section title parsing robust
    against nested braces (e.g. \\texorpdfstring{...}{...}) and line breaks.
    """

    if brace_start < 0 or brace_start >= len(text) or text[brace_start] != "{":
        return None
    depth = 1
    i = brace_start + 1
    buf: list[str] = []
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            # Preserve escapes so downstream stripping stays consistent.
            buf.append(ch)
            i += 1
            if i < len(text):
                buf.append(text[i])
                i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return "".join(buf), i + 1
        buf.append(ch)
        i += 1
    return None

def split_tex_sections(
    raw_tex: str,
    *,
    commands: list[str],
    strip_math: bool,
    strip_commands: bool,
) -> list[tuple[str, str]]:
    safe = [c.strip() for c in commands if c and str(c).strip()]
    if not safe:
        safe = ["section", "subsection", "subsubsection"]
    joined = "|".join(re.escape(c) for c in safe)
    marker_re = re.compile(rf"\\({joined})\*?\s*\{{")

    markers: list[tuple[int, int, str]] = []
    # Mask comments (preserve offsets) to avoid treating commented-out headings as real.
    hay = mask_tex_comments(raw_tex)
    for m in marker_re.finditer(hay):
        brace_start = m.end() - 1  # points to the '{' matched by the pattern
        parsed = read_balanced_braces(hay, brace_start)
        if not parsed:
            continue
        title_raw, title_end = parsed
        title = tex_visible_text(title_raw, strip_math=strip_math, strip_commands=strip_commands) or m.group(1)
        markers.append((m.start(), title_end, title))

    if not markers:
        return []

    sections: list[tuple[str, str]] = []
    last_title = "(no section)"
    last_start = 0
    for start_pos, title_end, title in markers:
        sections.append((last_title, raw_tex[last_start:start_pos]))
        last_title = title
        last_start = title_end
    sections.append((last_title, raw_tex[last_start:]))

    # If we have real sections, drop the leading "(no section)" chunk to reduce noise.
    if len(sections) > 1 and sections and sections[0][0] == "(no section)":
        sections = sections[1:]
    return sections


def iter_input_files(
    root: Path,
    *,
    include_globs: list[str],
    exclude_globs: list[str],
) -> Iterable[Path]:
    def _matches(path: str, pattern: str) -> bool:
        # Make common glob patterns behave intuitively for root-relative paths:
        # - "**/foo/**" should also match "foo/..."
        # - "./foo/**" should also match "foo/..."
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]):
            return True
        if pattern.startswith("./") and fnmatch.fnmatch(path, pattern[2:]):
            return True
        return False

    if root.is_file():
        rel = root.name
        if any(_matches(rel, g) for g in exclude_globs):
            return []
        if any(_matches(rel, g) for g in include_globs):
            return [root]
        return []

    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        if any(_matches(rel, g) for g in exclude_globs):
            continue
        if any(_matches(p.name, g) for g in include_globs) or any(_matches(rel, g) for g in include_globs):
            out.append(p)
    return out


_RE_DOC_CLASS = re.compile(r"\\documentclass\b")
_RE_BEGIN_DOC = re.compile(r"\\begin\s*\{document\}")
_RE_INPUT = re.compile(r"\\(input|include|subfile)\s*\{([^}]+)\}")


def looks_like_main_tex(text: str) -> bool:
    # Heuristic: a main TeX file usually has both markers.
    return bool(_RE_DOC_CLASS.search(text) and _RE_BEGIN_DOC.search(text))


def detect_main_tex(root: Path, *, exclude_globs: list[str]) -> Path | None:
    """Best-effort detection of the proposal's main LaTeX file.

    Preference order:
    1) <root>/main.tex (common in both NSFC_Young and NSFC_General templates)
    2) any .tex under root that contains both \\documentclass and \\begin{document}
    """

    def _glob_match(path: str, pattern: str) -> bool:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]):
            return True
        if pattern.startswith("./") and fnmatch.fnmatch(path, pattern[2:]):
            return True
        return False

    def _excluded(p: Path) -> bool:
        rel = str(p.relative_to(root))
        return any(_glob_match(rel, g) or _glob_match(p.name, g) for g in exclude_globs)

    if root.is_file():
        if root.suffix.lower() != ".tex":
            return None
        if looks_like_main_tex(read_text(root)):
            return root
        return None

    main = root / "main.tex"
    if main.exists() and main.is_file() and not _excluded(main):
        if looks_like_main_tex(read_text(main)):
            return main

    # Fallback: scan for a file that looks like a main entry.
    candidates = [p for p in sorted(root.rglob("*.tex")) if p.is_file() and not _excluded(p)]
    for p in candidates:
        try:
            if looks_like_main_tex(read_text(p)):
                return p
        except Exception:
            continue
    return None


def resolve_input_path(current_file: Path, arg: str) -> Path | None:
    arg = arg.strip()
    if not arg or "\\" in arg:
        # Likely a macro, or an invalid path for our simple resolver.
        return None
    # TeX allows extensionless inputs.
    candidates = [arg]
    if not Path(arg).suffix:
        candidates.append(arg + ".tex")
    for cand in candidates:
        p = (current_file.parent / cand).resolve()
        if p.exists() and p.is_file():
            return p
    return None


def collect_included_files(main_tex: Path) -> list[Path]:
    """Collect TeX/MD files reachable from a main TeX via \\input/\\include.

    Notes:
    - Commented-out \\input lines are ignored.
    - This is a best-effort resolver; it intentionally skips macro-driven inputs.
    """

    seen: set[Path] = set()
    order: list[Path] = []
    queue: list[Path] = [main_tex]

    while queue:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        order.append(cur)

        try:
            raw = read_text(cur)
        except Exception:
            continue

        # Strip comments first so optional blocks (commented inputs) won't be counted.
        for _, arg in _RE_INPUT.findall(strip_tex_comments(raw)):
            resolved = resolve_input_path(cur, arg)
            if not resolved:
                continue
            if resolved.suffix.lower() in {".tex", ".md", ".markdown"}:
                queue.append(resolved)

    return order

