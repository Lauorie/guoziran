#!/usr/bin/env python3
"""WisDoc PDF 转 Markdown 客户端。

复制自团队 peer-review skill 的 WisDoc 客户端（wisdoc_parse.py），改动：
- 删去 MCP serve 模式与 serve 子命令，保留 parse_pdf_to_markdown() 和 parse 子命令；
- 并入 peer-review envfile.py 的 .env 读取逻辑，但不在导入时改写 os.environ：查找顺序为已有环境变量 →
  当前目录及其各级父目录的 .env → 调用方传入的额外目录及其各级父目录 → 本 skill 目录；每个文件都读，
  同一个键取先找到的值；
- base URL、轮询超时与间隔可作参数传入；WISDOCRS_BASE_URL 缺失时在发出任何请求前抛出 WisDocNotConfigured；
- 日志与异常信息不输出 base URL 的值；返回结果不含 markdown_url；可指定 Markdown 文件名与资源目录名。

用法：
  python3 wisdoc_client.py parse --pdf-path ./paper.pdf --output-dir ./out
  python3 wisdoc_client.py parse --pdf-url https://example.com/paper.pdf

环境变量（或 .env）：
  WISDOCRS_BASE_URL       WisDoc 服务地址，必需；代码中不写死任何主机。
  WISDOC_CANARY_HEADER    X-Canary 请求头，默认 "grey"。
  WISDOC_POLL_INTERVAL    轮询间隔秒数，默认 5（未以参数传入时使用）。
  WISDOC_POLL_TIMEOUT     轮询超时秒数，默认 1200（未以参数传入时使用）。
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import logging
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CANARY_HEADER = "grey"
DEFAULT_OUTPUT_DIR = "wisdoc_pdf_parse_result"
DEFAULT_POLL_INTERVAL_S = 5.0
DEFAULT_POLL_TIMEOUT_S = 20 * 60.0
REQUEST_TIMEOUT_S = 60
MARKDOWN_PREVIEW_CHARS = 1500
INLINE_THRESHOLD_CHARS = 6000
MAX_ERROR_TEXT_LEN = 400
REDACTED = "<WISDOCRS_BASE_URL>"
IMAGE_REF_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_IMG_RE = re.compile(r"(<img\b[^>]*\bsrc=[\"'])([^\"']+)([\"'][^>]*>)", re.IGNORECASE)

logger = logging.getLogger(__name__)


class WisDocError(RuntimeError):
    """WisDoc 返回了无效或失败的响应。"""


class WisDocNotConfigured(WisDocError):
    """没有配置 WISDOCRS_BASE_URL。"""


class WisDocHTTPError(WisDocError):
    """WisDoc 返回 HTTP 错误；status 为状态码。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class WisDocJobFailed(WisDocError):
    """WisDoc 解析任务以失败告终。"""


# ---------- .env 读取（并入自 peer-review 的 envfile.py） ----------

def dotenv_candidates(extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None) -> list[Path]:
    """按查找顺序列出 .env 候选：当前目录及各级父目录 → 额外目录及各级父目录 → skill 目录。"""
    start = Path(cwd if cwd is not None else Path.cwd()).resolve()
    paths = [d / ".env" for d in (start, *start.parents)]
    for extra in extra_dirs:
        base = Path(extra).expanduser().resolve()
        paths += [d / ".env" for d in (base, *base.parents)]
    paths.append(SKILL_DIR / ".env")
    ordered: list[Path] = []
    for path in paths:
        if path not in ordered:
            ordered.append(path)
    return ordered


def read_dotenv(extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None) -> dict[str, str]:
    """读全部候选 .env，同一个键取先找到的值。不改写 os.environ。"""
    values: dict[str, str] = {}
    for path in dotenv_candidates(extra_dirs, cwd):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, _, val = s.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            if key and key not in values:
                values[key] = val.strip().strip('"').strip("'")
    return values


def resolve_setting(name: str, extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None) -> str:
    """已有环境变量优先，其次按 dotenv_candidates 的顺序找 .env；都没有时返回空串。"""
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    return (read_dotenv(extra_dirs, cwd).get(name) or "").strip()


def _check_base_url(base: str) -> str:
    base = base.strip().rstrip("/")
    if not base:
        raise WisDocNotConfigured(
            "WISDOCRS_BASE_URL 未配置：请设环境变量，或写入当前目录、项目目录及其上级目录的 .env。代码中不写死任何主机。"
        )
    if urllib.parse.urlparse(base).scheme not in ("http", "https") or not urllib.parse.urlparse(base).netloc:
        raise WisDocNotConfigured("WISDOCRS_BASE_URL 不是 http(s) 地址")
    return base


def resolve_base_url(extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None) -> str:
    """查找并校验 WISDOCRS_BASE_URL；缺失或不是 http(s) 地址时抛出 WisDocNotConfigured（信息中不含其值）。"""
    return _check_base_url(resolve_setting("WISDOCRS_BASE_URL", extra_dirs, cwd))


# ---------- HTTP ----------

@dataclass(frozen=True)
class _Conn:
    base_url: str
    canary: str

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"X-Canary": self.canary}
        if extra:
            headers.update(extra)
        return headers

    def redact(self, text: str) -> str:
        """去掉文字中的 base URL 及其主机名。"""
        out = text.replace(self.base_url, REDACTED)
        host = urllib.parse.urlparse(self.base_url).netloc
        return out.replace(host, REDACTED) if host else out


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as err:
        raise WisDocError(f"{name} 必须是数字，实际为 {raw!r}") from err


def _compact_error_text(raw_text: str) -> str:
    text = " ".join(str(raw_text or "").split())
    if not text:
        return "unknown error"
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            error_obj = payload.get("error")
            if isinstance(error_obj, dict):
                message = str(error_obj.get("message") or "").strip()
                if message:
                    text = message
    except ValueError:
        pass
    if len(text) <= MAX_ERROR_TEXT_LEN:
        return text
    return text[:MAX_ERROR_TEXT_LEN].rstrip() + "..."


def _normalize_inputs(pdf_url: str | None, pdf_path: str | None) -> tuple[str | None, str | None]:
    url = (pdf_url or "").strip()
    path = (pdf_path or "").strip()
    if bool(url) == bool(path):
        raise ValueError("Provide exactly one of pdf_url or pdf_path.")
    if url and _looks_like_local_path(url):
        raise ValueError("pdf_url looks like a local path. Use pdf_path instead.")
    if path and _looks_like_remote_uri(path):
        raise ValueError("pdf_path looks like a remote URI. Use pdf_url instead.")
    return url or None, path or None


def _looks_like_local_path(value: str) -> bool:
    text = value.strip()
    lower = text.lower()
    return (
        lower.startswith("file://")
        or text.startswith(("~", "./", "../", ".\\", "..\\"))
        or (len(text) >= 3 and text[0].isalpha() and text[1] == ":" and text[2] in "\\/")
        or text.startswith("\\\\")
        or (text.startswith("/") and not text.startswith("//"))
    )


def _looks_like_remote_uri(value: str) -> bool:
    text = value.strip()
    lower = text.lower()
    return lower.startswith(
        ("file://", "http://", "https://", "s3://", "s3a://", "s3n://", "gs://", "ftp://", "sftp://")
    ) or text.startswith("//")


def _multipart_body(
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"----wisdoc-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    for name, (filename, content, content_type) in files.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
            ).encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _open(conn: _Conn, request: urllib.request.Request) -> tuple[bytes, str]:
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
            return response.read(), response.headers.get_content_type() or "application/octet-stream"
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", errors="replace")
        raise WisDocHTTPError(err.code, f"HTTP {err.code}: {conn.redact(_compact_error_text(text))}") from None


def _request_json(conn: _Conn, method: str, url: str, *, body: bytes | None = None,
                  headers: dict[str, str] | None = None) -> Any:
    raw, _ = _open(conn, urllib.request.Request(url, data=body, headers=headers or {}, method=method))
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as err:
        raise WisDocError("WisDoc 返回的不是 JSON") from err


def _request_text(conn: _Conn, url: str) -> str:
    raw, _ = _open(conn, urllib.request.Request(url, headers=conn.headers(), method="GET"))
    return raw.decode("utf-8")


def _request_bytes(conn: _Conn, url: str) -> tuple[bytes, str]:
    return _open(conn, urllib.request.Request(url, headers=conn.headers(), method="GET"))


def _submit_pdf_url(conn: _Conn, pdf_url: str, *, no_cache: bool) -> str:
    fields = {"oss_path": pdf_url}
    if no_cache:
        fields["no_cache"] = "true"
    body, content_type = _multipart_body(fields, {})
    response = _request_json(conn, "POST", f"{conn.base_url}/api/v2/documents", body=body,
                             headers=conn.headers({"Content-Type": content_type}))
    return _extract_job_id(response)


def _submit_pdf_path(conn: _Conn, pdf_path: str, *, no_cache: bool) -> str:
    path = Path(pdf_path).expanduser().resolve(strict=True)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"pdf_path must end with .pdf, got {path.name!r}")
    content_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
    fields = {"no_cache": "true"} if no_cache else {}
    body, multipart_type = _multipart_body(fields, {"file": (path.name, path.read_bytes(), content_type)})
    response = _request_json(conn, "POST", f"{conn.base_url}/api/v2/documents", body=body,
                             headers=conn.headers({"Content-Type": multipart_type}))
    return _extract_job_id(response)


def _extract_job_id(response: Any) -> str:
    if not isinstance(response, dict):
        raise WisDocError("WisDoc 提交接口返回的不是 JSON 对象")
    job_id = str(response.get("job_id") or "").strip()
    if not job_id:
        raise WisDocError("WisDoc 提交接口没有返回 job_id")
    logger.info("submitted job_id=%s", job_id)
    return job_id


def _poll_until_done(conn: _Conn, job_id: str, *, interval: float, timeout: float) -> dict[str, Any]:
    endpoint = f"{conn.base_url}/api/v2/documents/{job_id}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = _request_json(conn, "GET", endpoint, headers=conn.headers())
        task_status = body.get("task_status") if isinstance(body, dict) else None
        if isinstance(task_status, dict) and task_status.get("ready"):
            if not task_status.get("successful"):
                raise WisDocJobFailed(
                    f"WisDoc job failed job_id={job_id} status={task_status.get('status')!r} "
                    f"info={conn.redact(str(task_status.get('info')))!r}"
                )
            return body
        logger.info("polling job_id=%s status=%s", job_id, (task_status or {}).get("status"))
        time.sleep(interval)
    raise TimeoutError(f"WisDoc job timed out after {int(timeout)}s job_id={job_id}")


def _persist_markdown(target_dir: Path, markdown_name: str, markdown: str) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / markdown_name
    tmp_path = target_dir / f"{markdown_name}.tmp"
    tmp_path.write_text(markdown, encoding="utf-8")
    os.replace(tmp_path, final_path)
    return final_path


def _is_downloadable_asset_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        return True
    return not parsed.scheme and not url.startswith(("#", "data:"))


def _asset_filename(url: str, index: int, content_type: str = "") -> str:
    parsed = urllib.parse.urlparse(url)
    raw_name = Path(urllib.parse.unquote(parsed.path)).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._")
    if not name:
        guessed_ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".bin"
        name = f"asset_{index}{guessed_ext}"
    if "." not in name:
        guessed_ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed_ext:
            name += guessed_ext
    return f"{index:03d}_{name}"


def _download_markdown_assets(conn: _Conn, markdown: str, markdown_url: str, assets_dir: Path) -> tuple[str, list[Path]]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    url_to_local: dict[str, str] = {}

    def localize_url(raw_url: str) -> str:
        url = raw_url.strip()
        if not _is_downloadable_asset_url(url):
            return raw_url
        absolute_url = urllib.parse.urljoin(markdown_url, url)
        if absolute_url not in url_to_local:
            try:
                content, content_type = _request_bytes(conn, absolute_url)
            except (WisDocError, OSError, ValueError, http.client.HTTPException) as err:
                logger.warning("资源下载失败（第 %d 个）：%s", len(url_to_local) + 1, type(err).__name__)
                return raw_url
            filename = _asset_filename(absolute_url, len(url_to_local) + 1, content_type)
            target_path = assets_dir / filename
            target_path.write_bytes(content)
            downloaded.append(target_path)
            url_to_local[absolute_url] = f"{assets_dir.name}/{filename}"
        return url_to_local[absolute_url]

    def replace_markdown_image(match: re.Match[str]) -> str:
        original = match.group(0)
        original_url = match.group(1)
        return original.replace(original_url, localize_url(original_url), 1)

    def replace_html_image(match: re.Match[str]) -> str:
        return f"{match.group(1)}{localize_url(match.group(2))}{match.group(3)}"

    markdown = IMAGE_REF_RE.sub(replace_markdown_image, markdown)
    markdown = HTML_IMG_RE.sub(replace_html_image, markdown)
    return markdown, downloaded


def _build_payload(job_id: str, markdown: str, markdown_path: Path, assets_dir: Path, assets: list[Path]) -> dict[str, Any]:
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    preview = markdown[:MARKDOWN_PREVIEW_CHARS]
    if len(markdown) > MARKDOWN_PREVIEW_CHARS:
        preview += "\n...[truncated]"
    payload: dict[str, Any] = {
        "job_id": job_id,
        "markdown_path": str(markdown_path),
        "assets_dir": str(assets_dir),
        "assets": [str(path) for path in assets],
        "asset_count": len(assets),
        "markdown_len": len(markdown),
        "markdown_sha256": digest,
        "preview": preview,
        "inlined": len(markdown) <= INLINE_THRESHOLD_CHARS,
    }
    if payload["inlined"]:
        payload["markdown"] = markdown
    return payload


def parse_pdf_to_markdown(
    *,
    pdf_url: str | None = None,
    pdf_path: str | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    no_cache: bool = False,
    base_url: str | None = None,
    poll_timeout_s: float | None = None,
    poll_interval_s: float | None = None,
    markdown_name: str | None = None,
    assets_dirname: str | None = None,
) -> dict[str, Any]:
    """用 WisDoc 解析一个 PDF，把 Markdown 与图片资源写入 output_dir。

    base_url 为 None 时按 resolve_base_url() 查找；缺失时在发出请求前抛出 WisDocNotConfigured。
    markdown_name、assets_dirname 默认为 {job_id}.md、{job_id}_assets。
    """
    normalized_url, normalized_path = _normalize_inputs(pdf_url, pdf_path)
    base = _check_base_url(base_url) if base_url else resolve_base_url()
    conn = _Conn(base_url=base, canary=resolve_setting("WISDOC_CANARY_HEADER") or DEFAULT_CANARY_HEADER)
    interval = poll_interval_s if poll_interval_s is not None else _env_float("WISDOC_POLL_INTERVAL", DEFAULT_POLL_INTERVAL_S)
    timeout = poll_timeout_s if poll_timeout_s is not None else _env_float("WISDOC_POLL_TIMEOUT", DEFAULT_POLL_TIMEOUT_S)
    job_id = (
        _submit_pdf_url(conn, normalized_url, no_cache=no_cache)
        if normalized_url
        else _submit_pdf_path(conn, normalized_path or "", no_cache=no_cache)
    )
    result = _poll_until_done(conn, job_id, interval=interval, timeout=timeout)
    metadata = result.get("metadata") if isinstance(result, dict) else None
    markdown_url = str((metadata or {}).get("markdown_url") or "").strip()
    if not markdown_url:
        raise WisDocError("WisDoc 任务完成，但 metadata 中没有 markdown_url")
    markdown = _request_text(conn, markdown_url)
    target_dir = Path(output_dir).expanduser().resolve(strict=False)
    assets_dir = target_dir / (assets_dirname or f"{job_id}_assets")
    markdown, assets = _download_markdown_assets(conn, markdown, markdown_url, assets_dir)
    markdown_path = _persist_markdown(target_dir, markdown_name or f"{job_id}.md", markdown)
    return _build_payload(job_id, markdown, markdown_path, assets_dir, assets)


def _parse_cli(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WisDoc PDF 转 Markdown（命令行）")
    subparsers = parser.add_subparsers(dest="command", required=True)
    parse_cmd = subparsers.add_parser("parse", help="解析一个 PDF 并输出 JSON 结果")
    parse_cmd.add_argument("--pdf-url", default="", help="Public PDF URL or WisDoc oss_path")
    parse_cmd.add_argument("--pdf-path", default="", help="Local .pdf path")
    parse_cmd.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Markdown output directory")
    parse_cmd.add_argument("--no-cache", action="store_true", help="Force WisDoc to re-parse")
    parse_cmd.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.getenv("WISDOC_LOG_LEVEL", "INFO"))
    args = _parse_cli(argv)
    payload = parse_pdf_to_markdown(
        pdf_url=args.pdf_url,
        pdf_path=args.pdf_path,
        output_dir=args.output_dir,
        no_cache=args.no_cache,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
