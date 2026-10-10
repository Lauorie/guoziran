#!/usr/bin/env python3
"""wispaper 检索：经 MCP 会话调用 quick_search / deep_search，原始返回逐字落盘，再汇成 rls.host_results.v1。

传输层并入自团队 academic-literature skill 的 wis_mcp_search.py（2026-10-10）：Streamable HTTP 会话
initialize → notifications/initialized → tools/call，兼容 SSE 与 JSON 响应，按业务错误码区分鉴权、限流与后端故障。
与原脚本的差别：凭据经 envfile 读取，不写 os.environ；按检索式文件批量执行；每条检索式的原始返回存一个文件，
再跑时已存档的直接复用，中断后原样重跑即可续上。

退出码：0 全部完成；1 有检索式失败（其余照常写入）；2 参数或路径错误；3 未配置凭据或凭据被拒；
4 到了单次运行时限，还有检索式未查（原样再跑一次）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional

import requests

import envfile
from proposal_common import ProposalError, load_config
from wis_mcp_client import McpAuthError, McpClient, McpError  # 测试经本模块引用这三个名字

SKILL_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = "nsfc-proposal/output/wispaper"
URL_KEY, TOKEN_KEY, CONSUMER_KEY = "WIS_MCP_URL", "WIS_MCP_TOKEN", "WIS_MCP_CONSUMER"
NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")  # 用 fullmatch
TOOLS = ("quick_search", "deep_search")
HOST_SCHEMA = "rls.host_results.v1"
MIN_TOP_N, MAX_TOP_N = 1, 100
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_NOT_CONFIGURED, EXIT_PENDING = 0, 1, 2, 3, 4


class WispaperNotConfigured(RuntimeError):
    """凭据缺失或写法不对；信息不含值。"""


def clamp_top_n(value: Any, default: int) -> int:
    try:
        n = int(value) if value is not None else default
    except (TypeError, ValueError):
        n = default
    return max(MIN_TOP_N, min(n, MAX_TOP_N))


def load_credentials(task_root: Path, *, cwd: Path | str | None = None,
                     skill_dir: Path | str | None = None) -> tuple[str, str, Optional[str]]:
    """环境变量优先，其次任务目录与当前目录各级父目录的 .env；缺失或写法不对时抛出 WispaperNotConfigured。"""
    skill = skill_dir if skill_dir is not None else SKILL_DIR
    values = {key: envfile.resolve_setting(key, [task_root], cwd, skill_dir=skill) for key in (URL_KEY, TOKEN_KEY, CONSUMER_KEY)}
    missing = [key for key in (URL_KEY, TOKEN_KEY) if not values[key]]
    if missing:
        raise WispaperNotConfigured(f"缺 {'、'.join(missing)}")
    url = values[URL_KEY]
    if re.search(r"[\s#]", url) or not url.lower().startswith(("https://", "http://")):
        raise WispaperNotConfigured(f"{URL_KEY} 写法不对：须以 http(s):// 开头，不含空白或 #（检查 .env 中该行是否带了行尾注释）")
    for key in (TOKEN_KEY, CONSUMER_KEY):
        if re.search(r"\s", values[key]) or not values[key].isascii():
            raise WispaperNotConfigured(f"{key} 含空白或非 ASCII 字符")
    return url, values[TOKEN_KEY], values[CONSUMER_KEY] or None


def read_queries(path: Path) -> list[str]:
    """读取 {"queries": [...]} 或数组；元素可为字符串或 {"query": ...}；去首尾空白，去空，去重（保持顺序）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProposalError(f"--query-file 读不了（{type(exc).__name__}）：{path}") from exc
    items = data.get("queries") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ProposalError('--query-file 须为 {"queries": [...]} 或数组')
    queries: list[str] = []
    for item in items:
        text = item if isinstance(item, str) else (item.get("query") if isinstance(item, dict) else None)
        text = str(text or "").strip()
        if text and text not in queries:
            queries.append(text)
    if not queries:
        raise ProposalError(f"--query-file 没有检索式：{path}")
    return queries


def raw_file_name(tool: str, top_n: int, query: str) -> str:
    return hashlib.sha256(f"{tool}\n{top_n}\n{query}".encode("utf-8")).hexdigest()[:12] + ".json"


@dataclass(frozen=True)
class BatchJob:
    task_root: Path
    name: str
    tool: str
    top_n: int
    queries: tuple[str, ...]
    workers: int
    budget_s: float
    timeout_s: float
    force: bool = False

    @property
    def out_dir(self) -> Path:
        return self.task_root / OUTPUT_DIR

    @property
    def raw_dir(self) -> Path:
        return self.out_dir / "raw" / self.name

    @property
    def host_path(self) -> Path:
        return self.out_dir / f"{self.name}_host.json"

    @property
    def summary_path(self) -> Path:
        return self.out_dir / f"{self.name}_host.summary.json"

    def raw_path(self, query: str) -> Path:
        return self.raw_dir / raw_file_name(self.tool, self.top_n, query)


def prepare_job(task_root: Path | str, name: str, tool: str, query_file: Path | str, top_n: Optional[int] = None,
                force: bool = False, *, config: Mapping[str, Any] | None = None) -> BatchJob:
    """校验参数与路径；不合格时抛出 ProposalError（退出码 2），此时还没有读凭据。"""
    task = Path(task_root).expanduser().resolve()
    if not task.name.startswith("task-") or task.parent.name != ".bensz-api" or not task.is_dir():
        raise ProposalError(f"--task-root 必须指向 .bensz-api/task-*/ 目录：{task}")
    if not NAME_RE.fullmatch(name or ""):
        raise ProposalError(f"--name 须匹配 {NAME_RE.pattern}：{name!r}")
    if tool not in TOOLS:
        raise ProposalError(f"--tool 须为 {'|'.join(TOOLS)}：{tool!r}")
    source = Path(query_file).expanduser().resolve()
    if task not in source.parents or not source.is_file():
        raise ProposalError(f"--query-file 必须是任务目录下的文件：{query_file}")
    lit = (config if config is not None else load_config()).get("literature") or {}
    default_n = int(lit.get("quick_search_top_n" if tool == "quick_search" else "deep_search_top_n") or 10)
    return BatchJob(task_root=task, name=name, tool=tool, top_n=clamp_top_n(top_n, default_n),
                    queries=tuple(read_queries(source)), workers=max(1, int(lit.get("wispaper_workers") or 4)),
                    budget_s=float(lit.get("wispaper_batch_budget_s") or 240),
                    timeout_s=float(lit.get("wispaper_timeout_s") or 300), force=force)


@dataclass
class BatchReport:
    fetched: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    auth_failed: bool = False

    @property
    def exit_code(self) -> int:
        if self.auth_failed:
            return EXIT_NOT_CONFIGURED
        if self.pending:
            return EXIT_PENDING
        return EXIT_FAILED if self.failed else EXIT_OK


def _read_raw(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _redact(text: str, client: Any) -> str:
    """遮盖文字中的 token、完整地址与主机名（地址与主机名不区分大小写）。"""
    token, url = getattr(client, "token", ""), getattr(client, "url", "")
    text = text.replace(token, "<已隐藏>") if token else text
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        host = ""
    for secret in (url, host):
        if secret:
            text = re.sub(re.escape(secret), "<已隐藏>", text, flags=re.IGNORECASE)
    return text


def _error_text(exc: Exception, client: Any = None) -> str:
    """MCP 错误照录（含 request-id），先遮盖 token 与地址；网络错误只写类型，因为 requests 的信息会带出主机名与地址；
    其他意外异常只写类型。"""
    if isinstance(exc, requests.RequestException):
        return f"网络错误（{type(exc).__name__}）"
    if isinstance(exc, McpError):
        return _redact(str(exc), client)
    return f"意外错误（{type(exc).__name__}）"


def _env_client_factory(job: BatchJob) -> Callable[[], McpClient]:
    url, token, consumer = load_credentials(job.task_root)
    return lambda: McpClient(url, token, consumer, timeout=(30, job.timeout_s))


def run_batch(job: BatchJob, client_factory: Optional[Callable[[], McpClient]] = None, *,
              clock: Callable[[], float] = time.monotonic) -> BatchReport:
    """查未存档的检索式（并发 job.workers 条），每条的返回存一个 raw 文件；最后从 raw 文件汇出 host 与汇总。"""
    report = BatchReport()
    todo: list[str] = []
    for query in job.queries:
        if not job.force and _read_raw(job.raw_path(query)) is not None:
            report.reused.append(query)
        else:
            todo.append(query)
    if todo:
        factory = client_factory or _env_client_factory(job)  # 缺凭据时在发出任何请求前抛出
        start, lock, local = clock(), threading.Lock(), threading.local()

        def fetch(query: str) -> None:
            with lock:
                stop = report.auth_failed or clock() - start > job.budget_s
                if stop:
                    report.pending.append(query)
            if stop:
                return
            client = getattr(local, "client", None)
            try:
                if client is None:
                    client = local.client = factory()
                data = client.call_tool(job.tool, {"query": query, "top_n": job.top_n})
                if not isinstance(data, dict) or not isinstance(data.get("papers", []), list):
                    raise ValueError("payload")
                _write_json(job.raw_path(query), data)
            except McpAuthError as exc:
                with lock:
                    report.auth_failed = True
                    report.failed.append({"query": query, "error": _error_text(exc, client)})
                return
            except Exception as exc:  # 单条失败不得中断整批：记为失败，汇总照常写出
                with lock:
                    report.failed.append({"query": query, "error": _error_text(exc, client)})
                return
            with lock:
                report.fetched.append(query)

        with ThreadPoolExecutor(max_workers=min(job.workers, len(todo))) as pool:
            list(pool.map(fetch, todo))
    write_outputs(job, report)
    return report


def write_outputs(job: BatchJob, report: BatchReport) -> None:
    """host 文件按检索式文件的顺序列出有 raw 存档的检索式；论文对象原样带出，只去掉没有标题的残记录。"""
    entries = []
    for query in job.queries:
        data = _read_raw(job.raw_path(query))
        if data is None:
            continue
        papers = [p for p in (data.get("papers") or []) if isinstance(p, dict) and str(p.get("title") or "").strip()]
        entries.append({"query": query, "tool": job.tool, "papers": papers,
                        "raw_file": job.raw_path(query).relative_to(job.out_dir).as_posix()})
    _write_json(job.host_path, {"schema": HOST_SCHEMA, "provider": "wispaper", "queries": entries})
    order = {q: i for i, q in enumerate(job.queries)}
    _write_json(job.summary_path, {
        "tool": job.tool, "top_n": job.top_n, "total": len(job.queries),
        "fetched": len(report.fetched), "reused": len(report.reused),
        "failed": sorted(report.failed, key=lambda f: order[f["query"]]),
        "pending": sorted(report.pending, key=lambda q: order[q]),
        "host_file": job.host_path.name,
    })


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="wispaper 检索：原始返回落盘，汇成 rls.host_results.v1")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("run", help="按检索式文件批量检索")
    cmd.add_argument("--task-root", required=True, help="本任务的 .bensz-api/task-*/ 目录")
    cmd.add_argument("--name", required=True, help="本批名称，如 keyword、claims_1")
    cmd.add_argument("--tool", required=True, choices=TOOLS)
    cmd.add_argument("--query-file", required=True, help="任务目录下的检索式文件")
    cmd.add_argument("--top-n", type=int, default=None, help="默认取 config.yaml 的 quick_search_top_n / deep_search_top_n")
    cmd.add_argument("--force", action="store_true", help="重查已存档的检索式（重查成功才覆盖）")
    args = parser.parse_args(argv)
    try:
        job = prepare_job(args.task_root, args.name, args.tool, args.query_file, args.top_n, args.force)
    except ProposalError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_USAGE
    try:
        report = run_batch(job)
    except WispaperNotConfigured as exc:
        print(f"wispaper 未配置：{exc}。WIS_MCP_URL、WIS_MCP_TOKEN 由环境变量或上级目录的 .env 提供；"
              "按 SKILL.md「wispaper 不可用」处理。", file=sys.stderr)
        return EXIT_NOT_CONFIGURED
    for item in report.failed:
        print(f"失败：{item['query'][:80]}：{item['error']}", file=sys.stderr)
    print(f"wispaper {job.tool}：共 {len(job.queries)} 条，新查 {len(report.fetched)}，复用 {len(report.reused)}，"
          f"失败 {len(report.failed)}，未查 {len(report.pending)}；写入 {job.host_path}")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
