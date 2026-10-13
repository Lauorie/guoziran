"""按键读取 .env，不改写 os.environ。WisDoc 客户端与出图脚本共用（并入自 peer-review 的 envfile.py）。

查找顺序：已有环境变量 → 当前目录及其各级父目录的 .env → 调用方传入的额外目录及其各级父目录 → skill 目录。
同一个键取先找到的值，只解析需要的键；未加引号的值在「空白 + #」处截断（与 python-dotenv 相同）。
skill 目录由调用方传入，测试可以换成临时目录。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

DOTENV_COMMENT_RE = re.compile(r"\s+#.*$")


def dotenv_candidates(extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None, *,
                      skill_dir: Path | str) -> list[Path]:
    """按查找顺序列出 .env 候选：当前目录及各级父目录 → 额外目录及各级父目录 → skill 目录。"""
    start = Path(cwd if cwd is not None else Path.cwd()).resolve()
    paths = [d / ".env" for d in (start, *start.parents)]
    for extra in extra_dirs:
        base = Path(extra).expanduser().resolve()
        paths += [d / ".env" for d in (base, *base.parents)]
    paths.append(Path(skill_dir) / ".env")
    ordered: list[Path] = []
    for path in paths:
        if path not in ordered:
            ordered.append(path)
    return ordered


def dotenv_value(raw: str) -> str:
    """引号内的值原样取出；未加引号的值在「空白 + #」处截断。"""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        return raw[1:end] if end != -1 else raw[1:]
    return DOTENV_COMMENT_RE.sub("", raw).strip()


def read_dotenv_value(name: str, extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None, *,
                      skill_dir: Path | str) -> str | None:
    """按 dotenv_candidates 的顺序找 name，返回第一个找到的值；只解析这一个键。"""
    for path in dotenv_candidates(extra_dirs, cwd, skill_dir=skill_dir):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            key, sep, raw = line.strip().partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            if sep and key == name:
                return dotenv_value(raw)
    return None


def resolve_setting(name: str, extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None, *,
                    skill_dir: Path | str) -> str:
    """已有环境变量优先，其次按 dotenv_candidates 的顺序找 .env；都没有时返回空串。"""
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    return (read_dotenv_value(name, extra_dirs, cwd, skill_dir=skill_dir) or "").strip()
