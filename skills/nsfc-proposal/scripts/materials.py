#!/usr/bin/env python3
"""解析申请人提供的材料（PDF、DOCX、Markdown、TXT），结果写入任务目录。

PDF：不加 --local-only 时交 WisDoc 解析（带图片资源），同时在本机抽文字；两者比对覆盖率，决定 agent 读哪一份。
DOCX：有 pandoc 时转 Markdown，否则用标准库抽段落与表格行；不上传。MD、TXT：原样转写为 UTF-8。
输出：T/shared/materials/<序号>-<文件名>/ 与 T/shared/materials/index.json。输入文件可在 project_root 之外（只读）。
退出码：0 完成（单个文件失败只记警告）；2 用法或路径错误。
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import wisdoc_client
from material_text import (comparable_text, coverage, docx_via_pandoc, docx_via_xml, local_pdf_text, pandoc_available,
                           read_text_file)
from proposal_common import ProposalError, load_config, resolve_project_root

SCHEMA = "nsfc-proposal.materials.v1"
KINDS = {".pdf": "pdf", ".docx": "docx", ".md": "md", ".txt": "txt"}
MIN_WISDOC_CHARS = 200
DIR_RE = re.compile(r"^(\d{2,})-[^/\\]+$")
WISDOC_FAILURES = (wisdoc_client.WisDocError, OSError, ValueError, http.client.HTTPException)
CONVERT_FAILURES = (zipfile.BadZipFile, KeyError, ET.ParseError, UnicodeDecodeError, OSError, RuntimeError,
                    subprocess.SubprocessError)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    min_coverage: float = 0.9
    poll_timeout_s: float = 520.0
    poll_interval_s: float = 5.0

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "Settings":
        materials = config.get("materials") or {}
        return cls(
            min_coverage=float(materials.get("min_wisdoc_coverage", 0.9)),
            poll_timeout_s=float(materials.get("wisdoc_poll_timeout_s", 520)),
            poll_interval_s=float(materials.get("wisdoc_poll_interval_s", 5)),
        )


@dataclass(frozen=True)
class Options:
    project_root: Path
    local_only: bool
    no_cache: bool
    settings: Settings
    cwd: Path | None


def wisdoc_parse(pdf: Path, out_dir: Path, *, env_dirs: Sequence[Path], cwd: Path | None, no_cache: bool,
                 settings: Settings) -> Path:
    """交 WisDoc 解析：Markdown 写成 out_dir/wisdoc.md，图片写进 out_dir/assets/。测试中替换本函数。"""
    base_url = wisdoc_client.resolve_base_url(env_dirs, cwd)
    payload = wisdoc_client.parse_pdf_to_markdown(
        pdf_path=str(pdf), output_dir=out_dir, no_cache=no_cache, base_url=base_url,
        poll_timeout_s=settings.poll_timeout_s, poll_interval_s=settings.poll_interval_s,
        markdown_name="wisdoc.md", assets_dirname="assets",
    )
    return Path(payload["markdown_path"])


def failure_category(exc: BaseException) -> str:
    """WisDoc 失败的类别；不含 URL 和服务端返回的文字。"""
    if isinstance(exc, wisdoc_client.WisDocNotConfigured):
        return "未配置 WISDOCRS_BASE_URL"
    if isinstance(exc, wisdoc_client.WisDocHTTPError):
        return f"HTTP 错误 {exc.status}"
    if isinstance(exc, wisdoc_client.WisDocJobFailed):
        return "解析任务失败"
    if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
        return "超时"
    if isinstance(exc, (urllib.error.URLError, ConnectionError, http.client.HTTPException)):
        return "连接失败"
    if isinstance(exc, (wisdoc_client.WisDocError, ValueError)):
        return "返回内容异常"
    return type(exc).__name__


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(filename: str) -> str:
    stem = re.sub(r"[^\w.\-]+", "_", Path(filename).stem).strip("._-")
    return stem[:60] or "file"


def _inside(base: Path, rel: str) -> Path | None:
    target = (base / rel).resolve()
    return target if base.resolve() in target.parents else None


def _valid_dir(rel: Any, base: Path) -> bool:
    return isinstance(rel, str) and bool(DIR_RE.match(rel)) and _inside(base, rel) is not None


def _next_dir(entries: list[dict], base: Path, filename: str) -> str:
    names = [e.get("dir") for e in entries] + [p.name for p in base.iterdir() if p.is_dir()]
    numbers = [int(m.group(1)) for m in (DIR_RE.match(n) for n in names if isinstance(n, str)) if m]
    return f"{max(numbers, default=0) + 1:02d}-{_safe_name(filename)}"


def _load_index(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("index.json 无法读取，重建索引")
        return []
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("files"), list):
        logger.warning("index.json 格式不符，重建索引")
        return []
    return [entry for entry in data["files"] if isinstance(entry, dict)]


def _save_index(path: Path, entries: list[dict]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"schema": SCHEMA, "files": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _cache_usable(entry: dict, base: Path, local_only: bool) -> bool:
    """记录的目录合法、引用的文件都在；--local-only 时不复用含 WisDoc 结果的记录。"""
    if entry.get("kind") not in KINDS.values() or not _valid_dir(entry.get("dir"), base):
        return False
    if local_only and entry.get("wisdoc_md"):
        return False
    for key in ("primary", "wisdoc_md", "local_txt"):
        rel = entry.get(key)
        if rel and not (isinstance(rel, str) and (target := _inside(base, rel)) is not None and target.is_file()):
            return False
    return True


def _entry(src: Path, sha: str, kind: str, rel: str | None, **fields: Any) -> dict:
    entry = {"source": src.name, "sha256": sha, "kind": kind, "dir": rel, "primary": None, "wisdoc_md": None,
             "local_txt": None, "parser": None, "chars": 0, "coverage": None, "warnings": []}
    entry.update(fields)
    return entry


def _primary_chars(base: Path, primary: str | None) -> int:
    return len((base / primary).read_text(encoding="utf-8")) if primary else 0


def _process_pdf(src: Path, sha: str, base: Path, rel: str, opts: Options) -> dict:
    item = base / rel
    warnings: list[str] = []
    local = local_pdf_text(src)
    warnings.extend(local.warnings)
    local_rel = None
    if (local.text or "").strip():
        (item / "local.txt").write_text(local.text + "\n", encoding="utf-8")
        local_rel = f"{rel}/local.txt"
    wis_text, failure = None, None
    if not opts.local_only:
        try:
            md_path = Path(wisdoc_parse(src, item, env_dirs=[opts.project_root], cwd=opts.cwd, no_cache=opts.no_cache,
                                        settings=opts.settings))
            wis_text = md_path.read_text(encoding="utf-8")
            if md_path.resolve() != (item / "wisdoc.md").resolve():
                (item / "wisdoc.md").write_text(wis_text, encoding="utf-8")
        except WISDOC_FAILURES as exc:
            failure = failure_category(exc)
            logger.warning("WisDoc 解析失败：%s（%s）", src.name, type(exc).__name__)
        if wis_text is not None and not comparable_text(wis_text):
            wis_text, failure = None, "返回空"
        if wis_text is None:
            (item / "wisdoc.md").unlink(missing_ok=True)
            shutil.rmtree(item / "assets", ignore_errors=True)
    cov = None
    if wis_text is not None:
        parser, wis_rel, primary = "wisdoc", f"{rel}/wisdoc.md", f"{rel}/wisdoc.md"
        if local_rel:
            cov = coverage(local.text or "", wis_text)
            if cov is not None and cov < opts.settings.min_coverage:
                primary = local_rel
                warnings.append(f"WisDoc 漏字（覆盖率 {cov:.0%}），正文以 local.txt 为准，表格与图看 wisdoc.md")
        else:
            if local.text is not None:
                warnings.append("本机抽不到文字，可能是扫描件，以 WisDoc 结果为准")
            if len(comparable_text(wis_text)) < MIN_WISDOC_CHARS:
                warnings.append("解析结果过短")
    else:
        parser, wis_rel, primary = "local", None, local_rel
        if failure:
            warnings.append(f"WisDoc 解析失败（{failure}）" + ("，正文以 local.txt 为准" if local_rel else ""))
        if primary is None:
            warnings.append("未取得文字")
    return _entry(src, sha, "pdf", rel, primary=primary, wisdoc_md=wis_rel, local_txt=local_rel, parser=parser,
                  chars=_primary_chars(base, primary), coverage=round(cov, 3) if cov is not None else None,
                  warnings=warnings)


def _process_converted(src: Path, sha: str, kind: str, base: Path, rel: str) -> dict:
    warnings: list[str] = []
    text, parser = "", None
    try:
        if kind != "docx":
            text, _encoding = read_text_file(src)
            parser = "text"
        else:
            if not pandoc_available():
                warnings.append("本机没有 pandoc，用内置解析抽取段落与表格行")
            else:
                try:
                    text, parser = docx_via_pandoc(src), "pandoc"
                except CONVERT_FAILURES as exc:
                    warnings.append(f"pandoc 转换失败（{type(exc).__name__}），改用内置解析")
            if parser is None:
                text, parser = docx_via_xml(src), "docx-xml"
    except CONVERT_FAILURES as exc:
        warnings.append(f"无法读取（{type(exc).__name__}）")
        text, parser = "", None
    primary = None
    if text.strip():
        (base / rel / "converted.md").write_text(text, encoding="utf-8")
        primary = f"{rel}/converted.md"
    else:
        warnings.append("未取得文字")
    return _entry(src, sha, kind, rel, primary=primary, parser=parser, chars=len(text) if primary else 0,
                  warnings=warnings)


def _check_task_root(task_root: Path | str) -> Path:
    task = Path(task_root).expanduser().resolve()
    if not task.name.startswith("task-") or task.parent.name != ".bensz-api":
        raise ProposalError(f"--task-root 必须指向 .bensz-api/task-*/ 目录：{task}")
    return task


def _check_files(files: Sequence[Path | str]) -> list[Path]:
    if not files:
        raise ProposalError("没有给出要解析的文件")
    sources = []
    for raw in files:
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise ProposalError(f"文件不存在或不是普通文件：{raw}")
        sources.append(path)
    return sources


def index_path(task_root: Path | str) -> Path:
    return _check_task_root(task_root) / "shared" / "materials" / "index.json"


def run(project_root: Path | str, task_root: Path | str, files: Sequence[Path | str], *, local_only: bool = False,
        no_cache: bool = False, cwd: Path | None = None, settings: Settings | None = None) -> list[tuple[dict, bool]]:
    """逐个解析文件，每个文件处理完就写一次 index.json。返回 [(记录, 是否命中缓存)]。"""
    root = resolve_project_root(project_root)
    base = index_path(task_root).parent
    sources = _check_files(files)
    opts = Options(project_root=root, local_only=local_only, no_cache=no_cache,
                   settings=settings or Settings.from_config(load_config()), cwd=cwd)
    base.mkdir(parents=True, exist_ok=True)
    entries = _load_index(base / "index.json")
    results: list[tuple[dict, bool]] = []
    for src in sources:
        sha = _sha256(src)
        kind = KINDS.get(src.suffix.lower())
        old = next((e for e in entries if e.get("sha256") == sha and e.get("dir")), None)
        if kind and old and not no_cache and _cache_usable(old, base, local_only):
            results.append((old, True))
            continue
        if kind is None:
            suffix = src.suffix.lower() or "（无后缀）"
            entry = _entry(src, sha, src.suffix.lower().lstrip(".") or "unknown", None,
                           warnings=[f"不支持的文件类型 {suffix}，已跳过"])
            entries = [e for e in entries if not (e.get("sha256") == sha and not e.get("dir"))] + [entry]
        else:
            rel = old["dir"] if old and _valid_dir(old.get("dir"), base) else _next_dir(entries, base, src.name)
            shutil.rmtree(base / rel, ignore_errors=True)
            (base / rel).mkdir(parents=True)
            print(f"解析 {src.name} ……", file=sys.stderr, flush=True)
            entry = (_process_pdf(src, sha, base, rel, opts) if kind == "pdf"
                     else _process_converted(src, sha, kind, base, rel))
            entries = [e for e in entries if e.get("sha256") != sha] + [entry]
        _save_index(base / "index.json", entries)
        results.append((entry, False))
    return results


def summary_line(entry: dict, cached: bool) -> str:
    cov = f"{entry['coverage']:.0%}" if isinstance(entry.get("coverage"), (int, float)) else "-"
    line = (f"{entry.get('source')}  parser={entry.get('parser') or '-'}  primary={entry.get('primary') or '-'}  "
            f"覆盖率={cov}  警告={len(entry.get('warnings') or [])}")
    return line + ("  （缓存）" if cached else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="materials.py", description="解析申请人材料（PDF 经 WisDoc，另抽本机文字对照）")
    sub = parser.add_subparsers(dest="command", required=True)
    parse = sub.add_parser("parse", help="解析文件，写入 T/shared/materials/")
    parse.add_argument("--project-root", required=True)
    parse.add_argument("--task-root", required=True, help="本任务的 .bensz-api/task-*/ 目录")
    parse.add_argument("--local-only", action="store_true", help="不上传 WisDoc，只在本机解析")
    parse.add_argument("--no-cache", action="store_true", help="忽略已有结果，重新解析")
    parse.add_argument("files", nargs="+", metavar="FILE")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        results = run(Path(args.project_root), Path(args.task_root), args.files, local_only=args.local_only,
                      no_cache=args.no_cache)
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    for entry, cached in results:
        print(summary_line(entry, cached))
    print(f"索引：{index_path(args.task_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
