"""MCP 传输层（Streamable HTTP）：initialize → notifications/initialized → tools/call。

并入自团队 academic-literature skill 的 wis_mcp_search.py（2026-10-10）。兼容 SSE 与 JSON 响应，
按业务错误码区分鉴权、限流与后端故障。与原文件的差别：sleep 可注入；默认读超时 300 秒；
不含 .env 加载、环境变量读取与命令行（凭据由 wispaper_search.py 经 envfile 读取，不写 os.environ）。
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import uuid
from typing import Any, Callable, Dict, List, Optional

import requests

PROTOCOL_VERSION = "2025-03-26"
REQUEST_TIMEOUT: tuple[float, float] = (30, 300)
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0
CLIENT_INFO = {"name": "nsfc-proposal-wispaper", "version": "0.1"}

# 业务错误码（见《MCP 远端功能测试说明 v0.2》第 7 节）
CODE_PARAM = "40001"
CODE_DOWNSTREAM = "40002"
CODE_AUTH = "40101"
CODE_RATE_LIMIT = "42901"
CODE_SYSTEM = "50001"


class McpError(RuntimeError):
    """协议层或业务层错误；绝不静默成空结果。"""


class McpAuthError(McpError):
    """鉴权失败（HTTP 401 或业务码 40101）。"""


class McpRateLimited(McpError):
    """限流（HTTP 429 或业务码 42901），重试耗尽后抛出。"""


PostFn = Callable[[Dict[str, Any], Dict[str, str]], Any]

REDACTED = "<已隐藏>"
ERROR_TEXT_LIMIT = 200


def redact_secrets(text: str, url: str = "", token: str = "") -> str:
    """遮盖文字中的 token、完整地址与主机名（地址与主机名不区分大小写；空值跳过）。"""
    token = (token or "").strip()
    text = text.replace(token, REDACTED) if token else text
    try:
        host = urllib.parse.urlparse(url or "").hostname or ""
    except ValueError:
        host = ""
    for secret in (url, host):
        if secret:
            text = re.sub(re.escape(secret), REDACTED, text, flags=re.IGNORECASE)
    return text


def _decode_body(resp: Any) -> str:
    """把响应正文按 UTF-8 取出。

    ``text/event-stream`` 不带 charset，requests 依 RFC 2616 按 ISO-8859-1 解码；
    UTF-8 中文里凡含字节 ``0x85`` 的字（如"先"= E5 85 88）会变成 U+0085(NEL)，而
    ``str.splitlines()`` 把 NEL 当换行——一条 SSE 事件被切碎，JSON 再也闭合不了。
    实测 ``tools/list`` 的中文工具描述就会踩中。所以一律从 ``content`` 解 UTF-8。
    """
    raw = getattr(resp, "content", None)
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode("utf-8", errors="replace")
    return getattr(resp, "text", "") or ""


def _parse_sse_or_json(text: str) -> Optional[Dict[str, Any]]:
    """响应可能是纯 JSON，也可能是 SSE；取最后一条完整的 JSON-RPC 消息。

    按 SSE 规范，一个事件可以有多行 ``data:``，以空行结束。只在真正的 ``\\n`` 上
    切行——绝不用 ``splitlines()``，它还会在 NEL / LS / PS 等字符上断开。
    """
    body = (text or "").strip()
    if not body:
        return None
    if body.startswith("{"):
        return json.loads(body)

    last: Optional[Dict[str, Any]] = None
    pending: List[str] = []

    def flush() -> None:
        nonlocal last, pending
        if not pending:
            return
        for joiner in ("\n", ""):  # 规范用 \n；有网关直接按字节切块，退回无缝拼接
            try:
                msg = json.loads(joiner.join(pending))
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                last = msg
            break
        pending = []

    for line in body.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("data:"):
            pending.append(line[5:].lstrip())
        elif not line.strip():
            flush()
    flush()
    return last


class McpClient:
    """最小 Streamable HTTP MCP 客户端：只做本 skill 需要的 tools/call。

    ``post`` 可注入（测试用）；默认用一个 ``requests.Session``，保住网关下发的
    SERVERID cookie，让同一 MCP 会话始终落到同一后端实例。
    """

    def __init__(
        self,
        url: str,
        token: str,
        consumer: Optional[str] = None,
        post: Optional[PostFn] = None,
        timeout: tuple[float, float] = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.url = url.strip()
        self.token = token.strip()
        self.consumer = (consumer or "").strip() or None
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep
        self.session_id: Optional[str] = None
        self.last_request_id: Optional[str] = None
        self._next_id = 1
        self._post: PostFn = post or self._default_post
        self._http: Optional[requests.Session] = None

    def _clip(self, text: Any, limit: int = ERROR_TEXT_LIMIT) -> str:
        """先脱敏再截断，避免地址或 token 被截在边界上而漏过遮盖。"""
        return redact_secrets(str(text), self.url, self.token)[:limit]

    # ------------------------------------------------------------ transport
    def _default_post(self, payload: Dict[str, Any], headers: Dict[str, str]) -> requests.Response:
        if self._http is None:
            self._http = requests.Session()
        return self._http.post(self.url, json=payload, headers=headers, timeout=self.timeout)

    def _headers(self, request_id: Optional[str] = None) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        if self.consumer:
            h["X-Mse-Consumer"] = self.consumer
        if request_id:
            # 服务端原值回显该头，是把客户端日志与网关/服务端日志对上的唯一线索。
            h["X-DashScope-Request-ID"] = request_id
        return h

    def _rpc(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        notify: bool = False,
        request_id: Optional[str] = None,
    ) -> Any:
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notify:
            payload["id"] = self._next_id
            self._next_id += 1
        resp = self._post(payload, self._headers(request_id))
        status = int(getattr(resp, "status_code", 0))
        text = _decode_body(resp)
        where = f" [request-id {request_id}]" if request_id else ""
        if status == 401:
            raise McpAuthError(f"HTTP 401: {self._clip(text.strip()) or 'unauthorized'}{where}")
        if status == 404 and self.session_id:
            # Streamable HTTP：会话过期时服务端回 404，须重新 initialize。
            self.session_id = None
            raise McpError("HTTP 404: MCP session expired")
        if status == 429:
            raise McpRateLimited(f"HTTP 429: {self._clip(text.strip())}{where}")
        if status >= 400:
            raise McpError(f"HTTP {status}: {self._clip(text.strip())}{where}")
        if notify:
            return None
        msg = _parse_sse_or_json(text)
        if msg is None:
            raise McpError(f"{method}: empty or unparsable response body{where}")
        if "error" in msg:
            err = msg["error"] or {}
            raise McpError(f"{method}: JSON-RPC error {err.get('code')}: {self._clip(err.get('message'))}{where}")
        return msg.get("result"), getattr(resp, "headers", {}) or {}

    # -------------------------------------------------------------- session
    def _ensure_session(self) -> None:
        if self.session_id:
            return
        _, headers = self._rpc(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO},
        )
        sid = next((v for k, v in headers.items() if k.lower() == "mcp-session-id"), None)
        if not sid:
            raise McpError("initialize succeeded but no Mcp-Session-Id header was returned")
        self.session_id = str(sid).strip()
        self._rpc("notifications/initialized", notify=True)

    # ----------------------------------------------------------------- tools
    @staticmethod
    def _unwrap_tool_result(result: Any) -> tuple[Dict[str, Any], bool]:
        content = (result or {}).get("content") or []
        text = next((c.get("text") for c in content if c.get("type") == "text"), None)
        if text is None:
            raise McpError("tools/call returned no text content")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise McpError(f"tools/call text is not JSON: {exc}") from exc
        return data, bool((result or {}).get("isError"))

    @staticmethod
    def _agent_error(data: Dict[str, Any]) -> Optional[str]:
        """后端曾把 deep_search 的失败报成 ``isError=false`` + ``onAgentError`` 事件
        （2026-09-20 实测，v0.1 已修）。留着这道检查：这种"成功外壳裹着失败"再回来
        时，静默返回零论文比报错更难查。
        """
        for ev in data.get("events") or []:
            if ev.get("event") == "onAgentError":
                err = (ev.get("data") or {}).get("error")
                return str(err or "agent error")
        return None

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            request_id = f"wis-mcp-{uuid.uuid4().hex[:16]}"
            self.last_request_id = request_id
            try:
                self._ensure_session()
                result, _ = self._rpc(
                    "tools/call", {"name": name, "arguments": arguments}, request_id=request_id
                )
            except McpRateLimited as exc:
                last_exc = exc
                self._sleep(BACKOFF_BASE_SECONDS * (2**attempt))
                continue
            except McpError as exc:
                if "session expired" in str(exc) and attempt + 1 < self.max_retries:
                    last_exc = exc
                    continue
                raise
            data, is_error = self._unwrap_tool_result(result)
            if is_error:
                code = str(data.get("code") or "")
                message = f"{name}: error {code}: {self._clip(data.get('message'))} [request-id {request_id}]"
                if code == CODE_AUTH:
                    raise McpAuthError(message)
                if code == CODE_RATE_LIMIT:
                    last_exc = McpRateLimited(message)
                    self._sleep(BACKOFF_BASE_SECONDS * (2**attempt))
                    continue
                # 40001/40002/50001：重试同一请求只会得到同一个错误，直接抛。
                raise McpError(message)
            if agent_err := self._agent_error(data):
                raise McpError(f"{name}: backend agent failed: {self._clip(agent_err)} [request-id {request_id}]")
            return data
        raise last_exc or McpError(f"{name}: retries exhausted")
