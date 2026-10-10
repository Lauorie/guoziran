"""申请人材料的本机文字抽取与 WisDoc 覆盖率计算（供 materials.py 调用）。

PyMuPDF（fitz）、pypdf、pdftotext 命令、pandoc 命令都是可选后备：import 失败或命令不存在就跳过，
记一条警告，不是必需依赖。
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

SUBPROCESS_TIMEOUT_S = 120
HORIZONTAL_SIN_MAX = 0.05      # 行方向与水平线夹角的正弦上限（约 3°）
SLANT_DEG_MIN = 5.0            # 单个 span 首尾字符连线倾角超过此值视为倾斜
LARGE_FONT_RATIO = 1.5         # 字号大于正文此倍数视为「明显大于正文」
HAN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
WORD_RE = re.compile(r"[a-z]+")
SENTENCE_SPLIT_RE = re.compile(r"[。！？；!?;\n]|\.(?=\s)")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
HTML_TAG_RE = re.compile(r"<[^>]+>")
MIN_HAN, KEY_HAN, MIN_WORDS, KEY_WORDS = 15, 12, 8, 8
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030")
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class BackendUnavailable(RuntimeError):
    """可选的抽取工具未安装。"""


@dataclass(frozen=True)
class LocalText:
    """本机 PDF 文字。text 为 None 表示没有可用的抽取工具；"" 表示抽到的文字为空。"""

    text: str | None
    backend: str | None
    warnings: tuple[str, ...] = ()


# ---------- PDF ----------

def _horizontal(direction: Any) -> bool:
    try:
        cos, sin = float(direction[0]), float(direction[1])
    except (TypeError, ValueError, IndexError):
        return True
    return cos > 0 and abs(sin) <= HORIZONTAL_SIN_MAX


def _span_text(span: dict) -> str:
    if "chars" in span:
        return "".join(c.get("c", "") for c in span["chars"])
    return str(span.get("text") or "")


def _span_slanted(span: dict) -> bool:
    chars = span.get("chars") or []
    if len(chars) < 2:
        return False
    (x0, y0), (x1, y1) = chars[0]["origin"], chars[-1]["origin"]
    if x0 == x1 and y0 == y1:
        return False
    return abs(math.degrees(math.atan2(y1 - y0, x1 - x0))) > SLANT_DEG_MIN


def _body_font_size(pages: list[dict]) -> float:
    sizes: Counter[float] = Counter()
    for page in pages:
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                if _horizontal(line.get("dir")):
                    for span in line.get("spans", []):
                        sizes[round(float(span.get("size", 0)) * 2) / 2] += len(_span_text(span))
    return sizes.most_common(1)[0][0] if sizes else 0.0


def _fitz_text(path: Path) -> str:
    """PyMuPDF：跳过非水平方向的行（斜向水印），以及字号明显大于正文且倾斜的 span。"""
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise BackendUnavailable("PyMuPDF") from exc
    with fitz.open(str(path)) as doc:
        pages = [page.get_text("rawdict") for page in doc]
    body = _body_font_size(pages)
    out_pages = []
    for page in pages:
        lines = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                if not _horizontal(line.get("dir")):
                    continue
                spans = [s for s in line.get("spans", [])
                         if not (body > 0 and float(s.get("size", 0)) > body * LARGE_FONT_RATIO and _span_slanted(s))]
                text = "".join(_span_text(s) for s in spans)
                if text.strip():
                    lines.append(text)
        out_pages.append("\n".join(lines))
    return "\n\n".join(out_pages)


def _pypdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as exc:
        raise BackendUnavailable("pypdf") from exc
    parts = []
    for page in PdfReader(str(path)).pages:
        try:
            parts.append(page.extract_text(orientations=(0,)) or "")
        except TypeError:
            parts.append(page.extract_text() or "")
    return "\n\n".join(parts)


def _pdftotext_text(path: Path) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise BackendUnavailable("pdftotext")
    for options in (["-enc", "UTF-8", "-nodiag"], ["-enc", "UTF-8"]):
        proc = subprocess.run([exe, *options, str(path), "-"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_S, check=False)
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8", errors="replace")
    raise RuntimeError(f"pdftotext 退出码 {proc.returncode}")


PDF_BACKENDS: tuple[tuple[str, Callable[[Path], str]], ...] = (
    ("PyMuPDF", _fitz_text), ("pypdf", _pypdf_text), ("pdftotext", _pdftotext_text),
)


def clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def local_pdf_text(path: Path) -> LocalText:
    """依次试 PyMuPDF → pypdf → pdftotext；用第一种不出错的结果（即使为空）。"""
    warnings: list[str] = []
    for name, extract in PDF_BACKENDS:
        try:
            text = extract(Path(path))
        except BackendUnavailable:
            warnings.append(f"本机没有 {name}，跳过")
            continue
        except Exception as exc:  # noqa: BLE001 — 第三方解析库对损坏文件抛出的异常类型不一
            warnings.append(f"{name} 抽取失败（{type(exc).__name__}），改试下一种")
            continue
        return LocalText(clean_text(text), name, tuple(warnings))
    warnings.append("本机没有可用的 PDF 文字抽取工具（PyMuPDF、pypdf、pdftotext），local.txt 未写")
    return LocalText(None, None, tuple(warnings))


# ---------- DOCX、文本 ----------

def pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


def docx_via_pandoc(path: Path) -> str:
    exe = shutil.which("pandoc")
    if not exe:
        raise BackendUnavailable("pandoc")
    proc = subprocess.run([exe, "--from=docx", "--to=gfm", "--wrap=none", str(path)],
                          capture_output=True, timeout=SUBPROCESS_TIMEOUT_S, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"pandoc 退出码 {proc.returncode}")
    return proc.stdout.decode("utf-8", errors="replace")


def _para_text(paragraph: ET.Element) -> str:
    parts = []
    for el in paragraph.iter():
        if el.tag == f"{W_NS}t":
            parts.append(el.text or "")
        elif el.tag == f"{W_NS}tab":
            parts.append("\t")
        elif el.tag in (f"{W_NS}br", f"{W_NS}cr"):
            parts.append("\n")
    return "".join(parts)


def _block_elements(parent: ET.Element) -> Iterator[ET.Element]:
    """正文中的段落与表格，展开内容控件（w:sdt）。"""
    for child in parent:
        if child.tag in (f"{W_NS}p", f"{W_NS}tbl"):
            yield child
        elif child.tag == f"{W_NS}sdt":
            content = child.find(f"{W_NS}sdtContent")
            if content is not None:
                yield from _block_elements(content)


def _table_lines(table: ET.Element) -> list[str]:
    lines = []
    for row in table.findall(f"{W_NS}tr"):
        cells = [" ".join(_para_text(p).strip() for p in cell.iter(f"{W_NS}p")).strip().replace("|", "\\|")
                 for cell in row.findall(f"{W_NS}tc")]
        lines.append("| " + " | ".join(cells) + " |")
        if len(lines) == 1:
            lines.append("|" + "---|" * len(cells))
    return lines


def docx_via_xml(path: Path) -> str:
    """标准库解析：读 word/document.xml，按段落与表格行抽文字；表格写成 Markdown 表。"""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{W_NS}body")
    blocks = []
    for element in _block_elements(body if body is not None else root):
        if element.tag == f"{W_NS}p":
            text = _para_text(element).strip()
            if text:
                blocks.append(text)
        else:
            blocks.append("\n".join(_table_lines(element)))
    return "\n\n".join(blocks) + "\n"


def read_text_file(path: Path) -> tuple[str, str]:
    """依次试 utf-8、utf-8-sig、gb18030；返回（文字，编码）。都失败时抛出 UnicodeDecodeError。"""
    data = Path(path).read_bytes()
    for encoding in TEXT_ENCODINGS[:-1]:
        try:
            return data.decode(encoding).lstrip("﻿"), encoding
        except UnicodeDecodeError:
            continue
    return data.decode(TEXT_ENCODINGS[-1]).lstrip("﻿"), TEXT_ENCODINGS[-1]


# ---------- 覆盖率 ----------

def _normalize(text: str) -> str:
    """只留汉字与字母数字，转小写。"""
    return "".join(ch for ch in text if ch.isalnum())


def comparable_text(markdown: str) -> str:
    """WisDoc Markdown 去掉图片引用与 HTML 标签后，归一化为只含汉字与字母数字的小写串。"""
    text = HTML_TAG_RE.sub(" ", MD_IMAGE_RE.sub(" ", markdown))
    return _normalize(unicodedata.normalize("NFKC", text).lower())


def sentence_key(sentence: str) -> str | None:
    """较长句子（不少于 15 个汉字，或不少于 8 个英文词）的比对键：句首 12 个汉字或前 8 个词；短句返回 None。"""
    s = unicodedata.normalize("NFKC", sentence).lower()
    han = [m.end() for m in HAN_RE.finditer(s)]
    if len(han) >= MIN_HAN:
        return _normalize(s[:han[KEY_HAN - 1]])
    words = list(WORD_RE.finditer(s))
    if len(words) >= MIN_WORDS:
        return _normalize(s[:words[KEY_WORDS - 1].end()])
    return None


def coverage(local_text: str, wisdoc_markdown: str) -> float | None:
    """本机文字中较长句子的键（去重）有多少出现在 WisDoc 文本中；没有较长句子时返回 None。"""
    keys = {k for k in (sentence_key(s) for s in SENTENCE_SPLIT_RE.split(local_text)) if k}
    if not keys:
        return None
    target = comparable_text(wisdoc_markdown)
    return sum(1 for k in keys if k in target) / len(keys)
