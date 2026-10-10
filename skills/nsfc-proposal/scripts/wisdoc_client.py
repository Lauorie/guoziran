#!/usr/bin/env python3
"""WisDoc PDF 转 Markdown 客户端。

复制自团队 peer-review skill 的 WisDoc 客户端（wisdoc_parse.py），改动：
- 删去 MCP serve 模式与 serve 子命令，保留 parse_pdf_to_markdown() 和 parse 子命令；
- 并入 peer-review envfile.py 的 .env 查找逻辑，不改写 os.environ：已有环境变量 → 当前目录及其各级父目录的
  .env → 调用方传入的额外目录及其各级父目录 → 本 skill 目录；同一个键取先找到的值，只解析需要的键；
  未加引号的值在「空白 + #」处截断（与 python-dotenv 相同）；
- WISDOCRS_BASE_URL 缺失、含空白或 #、不是 http(s) 地址时，在发出任何请求前抛出 WisDocNotConfigured；
- 检查服务器返回的值：所有请求（含每一跳重定向）只许 http/https，主机须为 base 主机、其子域名、与 base 主机
  同属其上级域名的主机（上级域名至少两段；base 为 IP 时不适用）或 WISDOC_ALLOWED_HOSTS 中的主机；job_id 须为
  1–128 个字母、数字或 ._-；响应有大小上限；图片最多 MAX_ASSETS 张，被拒、失败、超限或超时的图片在 Markdown
  中替换为「（图片未下载）」；可设单个文件的总时限；
- 上传文件名用内容 sha256 的前 16 位；User-Agent 固定为 nsfc-proposal-materials/0.1，不带身份信息；
- 日志与异常信息不输出 base URL 的值；返回结果不含 markdown_url；可指定 Markdown 文件名与资源目录名。

用法：
  python3 wisdoc_client.py parse --pdf-path ./paper.pdf --output-dir ./out
  python3 wisdoc_client.py parse --pdf-url https://example.com/paper.pdf

环境变量（或 .env）：
  WISDOCRS_BASE_URL       WisDoc 服务地址，必需；代码中不写死任何主机。
  WISDOC_ALLOWED_HOSTS    额外允许访问的主机，逗号分隔，默认空。
  WISDOC_CANARY_HEADER    X-Canary 请求头，默认 "grey"。
  WISDOC_POLL_INTERVAL    轮询间隔秒数，默认 5（未以参数传入时使用）。
  WISDOC_POLL_TIMEOUT     轮询超时秒数，默认 1200（未以参数传入时使用）。
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
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
USER_AGENT = "nsfc-proposal-materials/0.1"
DEFAULT_CANARY_HEADER = "grey"
DEFAULT_OUTPUT_DIR = "wisdoc_pdf_parse_result"
DEFAULT_POLL_INTERVAL_S = 5.0
DEFAULT_POLL_TIMEOUT_S = 20 * 60.0
REQUEST_TIMEOUT_S = 60.0
MAX_RESPONSE_BYTES = 20 * 1024 * 1024   # JSON、Markdown、单个图片各自的上限
MAX_ASSETS = 200
MAX_ERROR_BYTES = 4096
MARKDOWN_PREVIEW_CHARS = 1500
INLINE_THRESHOLD_CHARS = 6000
MAX_ERROR_TEXT_LEN = 400
REDACTED = "<WISDOCRS_BASE_URL>"
ASSET_PLACEHOLDER = "（图片未下载）"
JOB_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
DOTENV_COMMENT_RE = re.compile(r"\s+#.*$")
IMAGE_REF_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_IMG_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)

logger = logging.getLogger(__name__)


class WisDocError(RuntimeError):
    """WisDoc 返回了无效或失败的响应。"""


class WisDocNotConfigured(WisDocError):
    """WISDOCRS_BASE_URL 缺失或写法不对。"""


class WisDocHTTPError(WisDocError):
    """WisDoc 返回 HTTP 错误；status 为状态码。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class WisDocJobFailed(WisDocError):
    """WisDoc 解析任务以失败告终。"""


class WisDocURLRejected(WisDocError):
    """服务器给出的地址（或重定向目标）的 scheme 或主机不在允许范围内。"""


def _now() -> float:
    return time.monotonic()


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


def _dotenv_value(raw: str) -> str:
    """引号内的值原样取出；未加引号的值在「空白 + #」处截断。"""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        return raw[1:end] if end != -1 else raw[1:]
    return DOTENV_COMMENT_RE.sub("", raw).strip()


def read_dotenv_value(name: str, extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None) -> str | None:
    """按 dotenv_candidates 的顺序找 name，返回第一个找到的值；只解析这一个键。"""
    for path in dotenv_candidates(extra_dirs, cwd):
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
                return _dotenv_value(raw)
    return None


def resolve_setting(name: str, extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None) -> str:
    """已有环境变量优先，其次按 dotenv_candidates 的顺序找 .env；都没有时返回空串。"""
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    return (read_dotenv_value(name, extra_dirs, cwd) or "").strip()


def _check_base_url(base: str) -> str:
    base = base.strip().rstrip("/")
    if not base:
        raise WisDocNotConfigured(
            "WISDOCRS_BASE_URL 未配置：请设环境变量，或写入当前目录、项目目录及其上级目录的 .env。代码中不写死任何主机。"
        )
    if re.search(r"[\s#]", base):
        raise WisDocNotConfigured("WISDOCRS_BASE_URL 含空白或 #：检查 .env 中该行是否带了行尾注释或多余字符")
    try:
        parsed = urllib.parse.urlparse(base)
        host = parsed.hostname
    except ValueError:
        host, parsed = None, None
    if parsed is None or parsed.scheme not in ("http", "https") or not host:
        raise WisDocNotConfigured("WISDOCRS_BASE_URL 不是 http(s) 地址")
    return base


def resolve_base_url(extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None) -> str:
    """查找并校验 WISDOCRS_BASE_URL；不合格时抛出 WisDocNotConfigured（信息中不含其值）。"""
    return _check_base_url(resolve_setting("WISDOCRS_BASE_URL", extra_dirs, cwd))


def resolve_allowed_hosts(extra_dirs: Iterable[Path | str] = (), cwd: Path | str | None = None) -> tuple[str, ...]:
    raw = resolve_setting("WISDOC_ALLOWED_HOSTS", extra_dirs, cwd)
    return tuple(h.strip().lower().rstrip(".") for h in raw.split(",") if h.strip())


# ---------- 地址检查 ----------

def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def host_allowed(host: str, base_host: str, allowed_hosts: Iterable[str] = ()) -> bool:
    """base 主机、其子域名、与 base 主机同属其上级域名（至少两段；base 为 IP 时不适用）的主机，或 allowed_hosts 中的主机。"""
    host, base_host = host.lower().rstrip("."), base_host.lower().rstrip(".")
    if not host or not base_host:
        return False
    if host == base_host or host in set(allowed_hosts):
        return True
    if _is_ip(base_host) or _is_ip(host):
        return False
    if host.endswith("." + base_host):
        return True
    parent = base_host.partition(".")[2]
    return parent.count(".") >= 1 and host.endswith("." + parent)


@dataclass(frozen=True)
class _Conn:
    base_url: str
    canary: str
    allowed_hosts: tuple[str, ...] = ()

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "X-Canary": self.canary}
        if extra:
            headers.update(extra)
        return headers

    def redact(self, text: str) -> str:
        """去掉文字中的 base URL 及其主机名。"""
        out = text.replace(self.base_url, REDACTED)
        host = urllib.parse.urlparse(self.base_url).netloc
        return out.replace(host, REDACTED) if host else out

    def check_url(self, url: str) -> str:
        """返回可访问的绝对地址；scheme 不是 http/https 或主机不在允许范围时抛出 WisDocURLRejected。"""
        base = urllib.parse.urlparse(self.base_url)
        text = str(url).strip()
        if text.startswith("//"):
            text = f"{base.scheme}:{text}"
        try:
            parsed = urllib.parse.urlparse(text)
            host = parsed.hostname or ""
        except ValueError:
            raise WisDocURLRejected("WisDoc 返回的地址无法解析") from None
        if parsed.scheme not in ("http", "https") or not host_allowed(host, base.hostname or "", self.allowed_hosts):
            raise WisDocURLRejected("WisDoc 返回的地址不在允许范围内")
        return text


class _CheckedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """每一跳重定向都按 _Conn.check_url 检查。"""

    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        try:
            target = self._conn.check_url(urllib.parse.urljoin(req.full_url, newurl))
        except WisDocError:
            fp.close()
            raise
        return super().redirect_request(req, fp, code, msg, headers, target)


def _make_opener(conn: _Conn) -> urllib.request.OpenerDirector:
    """只含 HTTP(S) 处理器的 opener：不能打开 file:、ftp:、data:；重定向逐跳检查主机。"""
    opener = urllib.request.OpenerDirector()
    for handler in (urllib.request.ProxyHandler(), urllib.request.UnknownHandler(), urllib.request.HTTPHandler(),
                    urllib.request.HTTPSHandler(), urllib.request.HTTPDefaultErrorHandler(),
                    _CheckedRedirectHandler(conn), urllib.request.HTTPErrorProcessor()):
        opener.add_handler(handler)
    return opener


# ---------- HTTP ----------

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


def _request_timeout(deadline: float | None) -> float:
    """单次请求的超时：不超过 REQUEST_TIMEOUT_S，也不超过总时限的剩余时间。"""
    if deadline is None:
        return REQUEST_TIMEOUT_S
    remaining = deadline - _now()
    if remaining <= 0:
        raise TimeoutError("WisDoc 超过单个文件的总时限")
    return min(REQUEST_TIMEOUT_S, max(remaining, 1.0))


def _open(conn: _Conn, request: urllib.request.Request, *, timeout: float) -> tuple[bytes, str]:
    """发出请求并读响应体（不超过 MAX_RESPONSE_BYTES）；请求地址先经 check_url。"""
    conn.check_url(request.full_url)
    try:
        with _make_opener(conn).open(request, timeout=timeout) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            content_type = response.headers.get_content_type() or "application/octet-stream"
    except urllib.error.HTTPError as err:
        text = ""
        if err.fp is not None:
            try:
                text = err.read(MAX_ERROR_BYTES).decode("utf-8", errors="replace")
            finally:
                err.close()
        raise WisDocHTTPError(err.code, f"HTTP {err.code}: {conn.redact(_compact_error_text(text))}") from None
    if len(data) > MAX_RESPONSE_BYTES:
        raise WisDocError(f"WisDoc 响应超过 {MAX_RESPONSE_BYTES} 字节上限")
    return data, content_type


def _request_json(conn: _Conn, method: str, url: str, *, body: bytes | None = None,
                  headers: dict[str, str] | None = None, deadline: float | None = None) -> Any:
    raw, _ = _open(conn, urllib.request.Request(url, data=body, headers=headers or conn.headers(), method=method),
                   timeout=_request_timeout(deadline))
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as err:
        raise WisDocError("WisDoc 返回的不是 JSON") from err


def _request_text(conn: _Conn, url: str, deadline: float | None) -> str:
    raw, _ = _open(conn, urllib.request.Request(url, headers=conn.headers(), method="GET"), timeout=_request_timeout(deadline))
    return raw.decode("utf-8")


def _submit_pdf_url(conn: _Conn, pdf_url: str, *, no_cache: bool, deadline: float | None) -> str:
    fields = {"oss_path": pdf_url}
    if no_cache:
        fields["no_cache"] = "true"
    body, content_type = _multipart_body(fields, {})
    response = _request_json(conn, "POST", f"{conn.base_url}/api/v2/documents", body=body,
                             headers=conn.headers({"Content-Type": content_type}), deadline=deadline)
    return _extract_job_id(response)


def _submit_pdf_path(conn: _Conn, pdf_path: str, *, no_cache: bool, deadline: float | None) -> str:
    """上传本地 PDF；文件名用内容 sha256 的前 16 位，不发送原文件名。"""
    path = Path(pdf_path).expanduser().resolve(strict=True)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"pdf_path must end with .pdf, got {path.name!r}")
    content = path.read_bytes()
    upload_name = f"{hashlib.sha256(content).hexdigest()[:16]}.pdf"
    fields = {"no_cache": "true"} if no_cache else {}
    body, multipart_type = _multipart_body(fields, {"file": (upload_name, content, "application/pdf")})
    response = _request_json(conn, "POST", f"{conn.base_url}/api/v2/documents", body=body,
                             headers=conn.headers({"Content-Type": multipart_type}), deadline=deadline)
    return _extract_job_id(response)


def _extract_job_id(response: Any) -> str:
    if not isinstance(response, dict):
        raise WisDocError("WisDoc 提交接口返回的不是 JSON 对象")
    raw = response.get("job_id")
    job_id = str(raw).strip() if isinstance(raw, (str, int)) and not isinstance(raw, bool) else ""
    if not JOB_ID_RE.match(job_id) or job_id in (".", ".."):
        raise WisDocError("WisDoc 提交接口返回的 job_id 不合法")
    logger.info("submitted job_id=%s", job_id)
    return job_id


def _poll_until_done(conn: _Conn, job_id: str, *, interval: float, timeout: float,
                     deadline: float | None) -> dict[str, Any]:
    endpoint = f"{conn.base_url}/api/v2/documents/{urllib.parse.quote(job_id, safe='')}"
    poll_deadline = _now() + timeout if deadline is None else min(_now() + timeout, deadline)
    while _now() < poll_deadline:
        body = _request_json(conn, "GET", endpoint, deadline=poll_deadline)
        task_status = body.get("task_status") if isinstance(body, dict) else None
        if isinstance(task_status, dict) and task_status.get("ready"):
            if not task_status.get("successful"):
                raise WisDocJobFailed(
                    f"WisDoc job failed job_id={job_id} status={conn.redact(str(task_status.get('status')))!r} "
                    f"info={conn.redact(str(task_status.get('info')))!r}"
                )
            return body
        logger.info("polling job_id=%s status=%s", job_id, (task_status or {}).get("status"))
        time.sleep(max(0.0, min(interval, poll_deadline - _now())))
    raise TimeoutError(f"WisDoc job timed out after {int(timeout)}s job_id={job_id}")


def _contained(target_dir: Path, name: str) -> Path:
    """target_dir 下的直接子路径；name 含路径分隔或 .. 时抛出 WisDocError。"""
    path = (target_dir / name).resolve()
    if path.parent != target_dir.resolve():
        raise WisDocError("输出文件名不合法")
    return path


def _persist_markdown(target_dir: Path, markdown_name: str, markdown: str) -> Path:
    final_path = _contained(target_dir, markdown_name)
    tmp_path = final_path.with_name(final_path.name + ".tmp")
    tmp_path.write_text(markdown, encoding="utf-8")
    os.replace(tmp_path, final_path)
    return final_path


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


def _download_markdown_assets(conn: _Conn, markdown: str, markdown_url: str, assets_dir: Path,
                              deadline: float | None) -> tuple[str, list[Path]]:
    """下载图片并改写为本地相对路径；没有下载的图片整个替换为 ASSET_PLACEHOLDER。"""
    assets_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    url_to_local: dict[str, str | None] = {}

    def fetch(absolute: str) -> str | None:
        if len(downloaded) >= MAX_ASSETS:
            logger.warning("图片超过 %d 张，其余未下载", MAX_ASSETS)
            return None
        if deadline is not None and _now() >= deadline:
            logger.warning("超过单个文件的总时限，其余图片未下载")
            return None
        try:
            content, content_type = _open(conn, urllib.request.Request(absolute, headers=conn.headers(), method="GET"),
                                          timeout=_request_timeout(deadline))
        except (WisDocError, OSError, ValueError, http.client.HTTPException) as err:
            logger.warning("图片下载失败（第 %d 张）：%s", len(url_to_local) + 1, type(err).__name__)
            return None
        filename = _asset_filename(absolute, len(downloaded) + 1, content_type)
        (assets_dir / filename).write_bytes(content)
        downloaded.append(assets_dir / filename)
        return f"{assets_dir.name}/{filename}"

    def localize(raw_url: str) -> str | None:
        url = raw_url.strip()
        if not url or url.startswith("#"):
            return None
        try:
            absolute = conn.check_url(urllib.parse.urljoin(markdown_url, url))
        except WisDocError:
            logger.warning("图片地址不在允许范围内，未下载")
            return None
        if absolute not in url_to_local:
            url_to_local[absolute] = fetch(absolute)
        return url_to_local[absolute]

    def replace(match: re.Match[str]) -> str:
        local = localize(match.group(1))
        if local is None:
            return ASSET_PLACEHOLDER
        whole, offset = match.group(0), match.start(0)
        return whole[:match.start(1) - offset] + local + whole[match.end(1) - offset:]

    markdown = IMAGE_REF_RE.sub(replace, markdown)
    markdown = HTML_IMG_RE.sub(replace, markdown)
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
    env_dirs: Iterable[Path | str] = (),
    cwd: Path | str | None = None,
    poll_timeout_s: float | None = None,
    poll_interval_s: float | None = None,
    total_timeout_s: float | None = None,
    markdown_name: str | None = None,
    assets_dirname: str | None = None,
) -> dict[str, Any]:
    """用 WisDoc 解析一个 PDF，把 Markdown 与图片资源写入 output_dir。

    base_url 为 None 时按 resolve_base_url(env_dirs, cwd) 查找；WISDOC_CANARY_HEADER、WISDOC_ALLOWED_HOSTS
    用同样的顺序查找。base URL 不合格时在发出请求前抛出 WisDocNotConfigured。total_timeout_s 为本文件的总时限：
    轮询与取 Markdown 超过它时抛出 TimeoutError，图片下载超过它时停止，其余图片替换为占位。
    markdown_name、assets_dirname 默认为 {job_id}.md、{job_id}_assets。
    """
    deadline = _now() + total_timeout_s if total_timeout_s is not None else None
    normalized_url, normalized_path = _normalize_inputs(pdf_url, pdf_path)
    dirs = tuple(env_dirs)
    conn = _Conn(
        base_url=_check_base_url(base_url) if base_url else resolve_base_url(dirs, cwd),
        canary=resolve_setting("WISDOC_CANARY_HEADER", dirs, cwd) or DEFAULT_CANARY_HEADER,
        allowed_hosts=resolve_allowed_hosts(dirs, cwd),
    )
    interval = poll_interval_s if poll_interval_s is not None else _env_float("WISDOC_POLL_INTERVAL", DEFAULT_POLL_INTERVAL_S)
    timeout = poll_timeout_s if poll_timeout_s is not None else _env_float("WISDOC_POLL_TIMEOUT", DEFAULT_POLL_TIMEOUT_S)
    job_id = (
        _submit_pdf_url(conn, normalized_url, no_cache=no_cache, deadline=deadline)
        if normalized_url
        else _submit_pdf_path(conn, normalized_path or "", no_cache=no_cache, deadline=deadline)
    )
    result = _poll_until_done(conn, job_id, interval=interval, timeout=timeout, deadline=deadline)
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        raise WisDocError("WisDoc 返回的 metadata 不是对象")
    raw_url = metadata.get("markdown_url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise WisDocError("WisDoc 任务完成，但 metadata 中没有 markdown_url")
    markdown_url = conn.check_url(urllib.parse.urljoin(conn.base_url + "/", raw_url.strip()))
    markdown = _request_text(conn, markdown_url, deadline)
    target_dir = Path(output_dir).expanduser().resolve(strict=False)
    target_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = _contained(target_dir, assets_dirname or f"{job_id}_assets")
    _contained(target_dir, markdown_name or f"{job_id}.md")
    markdown, assets = _download_markdown_assets(conn, markdown, markdown_url, assets_dir, deadline)
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
