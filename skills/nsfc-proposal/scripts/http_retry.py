"""HTTP GET 的限流与间歇故障重试（429、500、502、503、504、连接错误与超时）。

等待函数由调用方注入，测试中不真睡眠。第 n 次重试等待 backoff_s * 2**(n-1) 秒；
响应带 Retry-After 且不超过 MAX_RETRY_AFTER_S 秒时改用它。重试用尽后返回最后一次响应，
或重新抛出最后一次连接异常，由调用方照常处理。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

import requests

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER_S = 60.0


def retry_delay(retry_number: int, backoff_s: float, retry_after: Any = None) -> float:
    """第 retry_number（从 1 起）次重试前的等待秒数。"""
    try:
        wanted = float(retry_after)
    except (TypeError, ValueError):
        wanted = -1.0
    if 0 <= wanted <= MAX_RETRY_AFTER_S:
        return wanted
    return backoff_s * 2 ** (retry_number - 1)


def get_with_retry(session: Any, url: str, *, params: Mapping[str, Any] | None, headers: Mapping[str, str] | None,
                   timeout: float | None, retries: int, backoff_s: float,
                   sleep: Callable[[float], None] = time.sleep) -> Any:
    """GET；遇可重试的状态码或连接错误时退避重试，最多 retries 次。"""
    attempt = 0
    while True:
        retry_after = None
        try:
            response = session.get(url, params=params, headers=headers, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout):
            if attempt >= retries:
                raise
        else:
            if getattr(response, "status_code", 200) not in RETRY_STATUSES or attempt >= retries:
                return response
            retry_after = (getattr(response, "headers", None) or {}).get("Retry-After")
        attempt += 1
        sleep(retry_delay(attempt, backoff_s, retry_after))


def failure_label(exc: BaseException) -> str:
    """失败原因的简短描述：异常类型，带 HTTP 状态码时一并写出。"""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"{type(exc).__name__} {status}" if status else type(exc).__name__
