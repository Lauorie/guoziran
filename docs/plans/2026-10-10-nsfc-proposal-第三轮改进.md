# nsfc-proposal 第三轮改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修掉 funded-2 验证运行暴露的问题：wispaper 检索结果由脚本落盘存档，不再靠模型手抄；出图标签不带括号；神经测量加动作匹配对照的规则；一致性检查、风险计数、参考文献类型、研究基础占位四处小缺陷。改完后换一个与中标书无关的题目（青年科学基金）重跑验证。

**Architecture:** wispaper 检索照搬团队 academic-literature skill 的做法：脚本经 MCP 会话调用 `quick_search`、`deep_search`，原始返回写文件，下游只读文件；MCP 工具只用于一次性探测。传输层代码并入 `skills/nsfc-proposal/scripts/wispaper_search.py`，凭据走现有的 `envfile.py`。其余改动分在 nsfc-proposal（文档、一致性检查、bib_resolve、信息表）和 nsfc-research-foundation-writer（风险计数）。

**Tech Stack:** Python 3 标准库、PyYAML、requests；pytest（unittest 风格）。

**Spec:** `docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md`。本轮要求来自申请人 2026-10-10 在对话中的决定：

- 换一个题目重跑。
- wispaper 原始返回的存档，参考 academic-literature 的做法。
- deep_search 不稳定是后端切换所致，产品级服务，之后会稳定：退路接不住问句的问题本轮不改代码。
- 其余小问题「按你的想法改」。
- 网页版不动。

## Global Constraints

- 分支 `nsfc-proposal`，远程 `lauorie`（git@github.com:Lauorie/guoziran.git）。各任务不推送，由控制者在终审后统一推送。
- 不新增必需的第三方依赖：只用标准库、PyYAML、requests。
- 脚本用 `Path(__file__).resolve()` 定位 skill 资产；文件读写显式 `encoding="utf-8"`。
- 输出路径限制在 project_root（P）或任务目录（T，目录名以 `task-` 开头且父目录名为 `.bensz-api`）内；越界报错，退出码 2。
- 仓库中不得出现本机用户目录的绝对路径和团队服务的域名；检查用的 `git grep` 模式由控制者在派发任务时给出，不写进仓库。
- 凭据（`WIS_MCP_TOKEN` 等）和网关地址不得出现在标准输出、标准错误、汇总文件、存档文件或测试快照中。
- HTTP 请求不附带个人邮箱或身份信息。
- 正文占位格式固定为 `【待补充：……】`；内部编号不进正文。
- 示例不得回显对比基准（中标书）的题材：创造力、具身、物化、照样制作、近红外、综合实践活动课程、课时、班级等词不进 skill 文档的示例。
- 版本号不再改动（本分支的版本已经提升且尚未发布）：nsfc-proposal 0.1.0、nsfc-research-foundation-writer 0.2.0。改动记入各自 CHANGELOG 的现有版本段落，BAC 行仍在段落最后；根 `CHANGELOG.md` `[Unreleased]` 同步一句。
- 测试放 `tests/<skill名>/`，unittest 风格，文件名全仓唯一（带 skill 缩写前缀）。测试不联网，产物写系统临时目录。测试命令（仓库根目录）：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider -W ignore::pytest.PytestConfigWarning tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/nsfc-research-foundation-writer tests/research-literature-search`。基线 360 passed。
- 提交信息 `<type>(<skill>): <中文摘要>`，末尾附 `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`（写实际完成提交的模型）。每次提交前测试 0 failed；`find skills tests -name __pycache__ -o -name .pytest_cache` 无输出。
- 文档风格：短句，少副词，不写宣传用语。

## Review Focus

1. 检索中途被打断（Bash 时限、网络中断）后原样重跑：已存档的检索式不重查；全部已存档时，没有凭据也能汇出 host 文件。测试在 Task 1。
2. 某条检索式报 40002，或中途鉴权失败：失败的检索式不进 host 文件，汇总列出，退出码分别为 1、3；任何输出都不含网关地址与 token。测试在 Task 1。
3. 检索式文件含重复、空白、`{"query": ...}` 对象写法：host 文件的 `query` 与 search_runner 的匹配键（去首尾空白的原文）一致，重复只查一次。测试在 Task 1。
4. 正文只是在说明占位格式（`【待补充：……】`，内文只有省略号）：不计入占位，也不报未列入；带真实内容的未列入占位仍报错。测试在 Task 3。
5. CrossRef 返回的书章缺 `container-title` 或 `publisher`：照常生成条目，缺的字段不写，不报错。测试在 Task 5。

---

### Task 1: wispaper 检索由脚本落盘（参照 academic-literature）

funded-2 中，宿主经 MCP 工具调用 wispaper，返回只出现在对话里，没有文件路径（`raw_path` 为 null）。280 条记录由模型逐条手抄进 host_results 文件，无法校验是否逐字一致。academic-literature 的做法是：用脚本开一个 MCP 会话调用检索工具，把返回写成文件，台账只从文件读；MCP 工具只用于一次性探测。本任务照这个做法改。

**Files:**
- Create: `skills/nsfc-proposal/scripts/wis_mcp_client.py`（MCP 传输层）
- Create: `skills/nsfc-proposal/scripts/wispaper_search.py`（批量检索、落盘、汇总、CLI）
- Modify: `skills/nsfc-proposal/config.yaml`（`literature` 段加三项）
- Modify: `skills/nsfc-proposal/SKILL.md`（第 3 步第 4、5 项；「失败与恢复」表中 wispaper 一行）
- Modify: `skills/nsfc-proposal/README.md`（凭据一节加 `WIS_MCP_URL`、`WIS_MCP_TOKEN`、可选 `WIS_MCP_CONSUMER`）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`（0.1.0 段）、根 `CHANGELOG.md`
- Create: `tests/nsfc-proposal/test_np_wispaper_search.py`

**Interfaces:**
- Consumes: `envfile.resolve_setting(name, extra_dirs, cwd, *, skill_dir) -> str`；`proposal_common.ProposalError`、`load_config()`；research-literature-search 的 `providers.host_results.load_host_results(path)`（只在测试中用来验证输出）。
- Produces:
  - CLI：`python3 S/scripts/wispaper_search.py run --task-root T --name <名称> --tool quick_search|deep_search --query-file <T 下的文件> [--top-n N] [--force]`。
  - 写 `T/nsfc-proposal/output/wispaper/raw/<名称>/<12 位哈希>.json`（每条检索式一份，内容是服务端返回的工具结果，逐字），`T/nsfc-proposal/output/wispaper/<名称>_host.json`（`rls.host_results.v1`），`T/nsfc-proposal/output/wispaper/<名称>_host.summary.json`。
  - 退出码：0 全部完成；1 有检索式失败；2 参数或路径错误；3 未配置凭据或凭据被拒；4 到了单次运行时限，还有检索式未查。

- [ ] **Step 1: 写失败的测试**

`tests/nsfc-proposal/test_np_wispaper_search.py`：

```python
"""wispaper 检索脚本：MCP 会话、原始返回落盘、断点续查、汇成 rls.host_results.v1。不联网。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "skills/research-literature-search/scripts"))

import wispaper_search as ws  # noqa: E402
from providers.host_results import load_host_results  # noqa: E402

PAPER = {"paper_id": None, "title": "Peritumoral radiomics adds value", "authors": ["A Author"],
         "abstract": "We tested peritumoral features.", "url": "https://doi.org/10.1000/xyz1", "pdf_url": None,
         "venue": "J Test", "year": 2023, "citations": 3, "doi": "10.1000/xyz1", "arxiv_id": None,
         "relevance_score": 0.8, "research_field": None, "source_url": None,
         "flags": {"no": False, "partial": False, "perfect": True}}
SECRET_URL = "https://gateway.invalid/api/v1/mcp"
SECRET_TOKEN = "tok-secret-123"


class FakeResponse:
    def __init__(self, status: int, body: str, headers: dict | None = None) -> None:
        self.status_code, self._body, self.headers = status, body, headers or {}

    @property
    def content(self) -> bytes:
        return self._body.encode("utf-8")

    @property
    def text(self) -> str:  # 模拟 requests 对无 charset 的 text/event-stream 按 latin-1 解码
        return self._body.encode("utf-8").decode("latin-1") if self.headers.get("content-type", "").startswith("text/") else self._body


def rpc(rid: int, result: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


def tool_text(payload: dict, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": is_error}


class FakeServer:
    """按方法名应答；tools/call 的结果由 answer(query) 决定，可返回 dict 或 (dict, is_error)。"""

    def __init__(self, answer=None) -> None:
        self.calls: list[dict] = []
        self.answer = answer or (lambda q: {"papers": [dict(PAPER, title=f"{PAPER['title']} {q}")], "stats": {"total": 1}})

    def post(self, payload: dict, headers: dict) -> FakeResponse:
        self.calls.append({"payload": payload, "headers": headers})
        method = payload.get("method")
        if method == "initialize":
            return FakeResponse(200, rpc(payload["id"], {"protocolVersion": "2025-03-26"}), {"Mcp-Session-Id": "s-1"})
        if method == "notifications/initialized":
            return FakeResponse(202, "")
        result = self.answer(payload["params"]["arguments"]["query"])
        data, is_error = result if isinstance(result, tuple) else (result, False)
        return FakeResponse(200, rpc(payload["id"], tool_text(data, is_error)))

    def tool_calls(self) -> list[dict]:
        return [c for c in self.calls if c["payload"].get("method") == "tools/call"]

    def client(self) -> ws.McpClient:
        return ws.McpClient(SECRET_URL, SECRET_TOKEN, post=self.post, sleep=lambda s: None)


class TaskDir:
    def __init__(self, base: Path, queries) -> None:
        self.root = base / "proj" / ".bensz-api" / "task-20261010-0000-t"
        (self.root / "nsfc-proposal" / "input").mkdir(parents=True)
        self.query_file = self.root / "nsfc-proposal" / "input" / "q.json"
        self.query_file.write_text(json.dumps({"queries": queries}, ensure_ascii=False), encoding="utf-8")
        self.out = self.root / "nsfc-proposal" / "output" / "wispaper"


CONFIG = {"literature": {"quick_search_top_n": 20, "deep_search_top_n": 10, "wispaper_workers": 2,
                         "wispaper_batch_budget_s": 480, "wispaper_timeout_s": 300}}


class ClientTest(unittest.TestCase):
    def test_handshake_then_session_reused(self) -> None:
        server = FakeServer()
        client = server.client()
        client.call_tool("quick_search", {"query": "a", "top_n": 3})
        client.call_tool("quick_search", {"query": "b", "top_n": 3})
        methods = [c["payload"]["method"] for c in server.calls]
        self.assertEqual(methods, ["initialize", "notifications/initialized", "tools/call", "tools/call"])
        self.assertEqual(server.calls[-1]["headers"]["Mcp-Session-Id"], "s-1")
        self.assertEqual(server.calls[-1]["headers"]["Authorization"], f"Bearer {SECRET_TOKEN}")

    def test_sse_chinese_survives_latin1_trap(self) -> None:
        payload = {"papers": [dict(PAPER, title="先验知识与瘤周特征")], "stats": {}}
        body = "event: message\ndata: " + rpc(3, tool_text(payload)) + "\n\n"
        state = {"n": 0}

        def post(p: dict, h: dict) -> FakeResponse:
            state["n"] += 1
            if p["method"] == "initialize":
                return FakeResponse(200, rpc(p["id"], {}), {"Mcp-Session-Id": "s"})
            if p["method"] == "notifications/initialized":
                return FakeResponse(202, "")
            return FakeResponse(200, body, {"content-type": "text/event-stream"})

        data = ws.McpClient(SECRET_URL, SECRET_TOKEN, post=post, sleep=lambda s: None).call_tool("quick_search", {"query": "x", "top_n": 1})
        self.assertEqual(data["papers"][0]["title"], "先验知识与瘤周特征")

    def test_http_401_and_40101_are_auth_errors(self) -> None:
        def post401(p: dict, h: dict) -> FakeResponse:
            return FakeResponse(401, "unauthorized")
        with self.assertRaises(ws.McpAuthError):
            ws.McpClient(SECRET_URL, SECRET_TOKEN, post=post401, sleep=lambda s: None).call_tool("quick_search", {"query": "x", "top_n": 1})
        server = FakeServer(lambda q: ({"code": "40101", "message": "denied"}, True))
        with self.assertRaises(ws.McpAuthError):
            server.client().call_tool("quick_search", {"query": "x", "top_n": 1})

    def test_40002_is_raised_without_retry(self) -> None:
        server = FakeServer(lambda q: ({"code": "40002", "message": "search request could not be processed"}, True))
        with self.assertRaises(ws.McpError) as ctx:
            server.client().call_tool("deep_search", {"query": "x", "top_n": 1})
        self.assertIn("40002", str(ctx.exception))
        self.assertEqual(len(server.tool_calls()), 1)

    def test_42901_retries_then_succeeds(self) -> None:
        state = {"n": 0}

        def answer(q: str):
            state["n"] += 1
            return ({"code": "42901", "message": "slow down"}, True) if state["n"] == 1 else {"papers": [PAPER], "stats": {}}

        data = FakeServer(answer).client().call_tool("quick_search", {"query": "x", "top_n": 1})
        self.assertEqual(data["papers"][0]["title"], PAPER["title"])


class BatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def job(self, task: TaskDir, tool: str = "quick_search", **kw) -> ws.BatchJob:
        return ws.prepare_job(task.root, "keyword", tool, task.query_file, config=CONFIG, **kw)

    def test_raw_files_are_verbatim_and_host_loads(self) -> None:
        task = TaskDir(self.base, ["  peritumoral radiomics  ", {"query": "intratumoral heterogeneity", "rationale": "r"}, "peritumoral radiomics", ""])
        server = FakeServer()
        report = ws.run_batch(self.job(task), client_factory=server.client)
        self.assertEqual(report.exit_code, 0)
        self.assertEqual(len(server.tool_calls()), 2)  # 重复与空白只查一次
        sent = [c["payload"]["params"]["arguments"] for c in server.tool_calls()]
        self.assertEqual({a["top_n"] for a in sent}, {20})
        raws = sorted((task.out / "raw" / "keyword").glob("*.json"))
        self.assertEqual(len(raws), 2)
        for raw in raws:
            data = json.loads(raw.read_text(encoding="utf-8"))
            self.assertEqual(set(data), {"papers", "stats"})  # 服务端返回原样
        hosts = load_host_results(task.out / "keyword_host.json")
        self.assertEqual(set(hosts), {"peritumoral radiomics", "intratumoral heterogeneity"})
        host = json.loads((task.out / "keyword_host.json").read_text(encoding="utf-8"))
        self.assertEqual(host["queries"][0]["papers"][0]["title"], f"{PAPER['title']} peritumoral radiomics")
        self.assertTrue(host["queries"][0]["raw_file"].startswith("raw/keyword/"))

    def test_rerun_reuses_raw_without_credentials(self) -> None:
        task = TaskDir(self.base, ["a b c", "d e f"])
        ws.run_batch(self.job(task), client_factory=FakeServer().client)
        (task.out / "keyword_host.json").unlink()
        with mock.patch.object(ws, "load_credentials", side_effect=AssertionError("全部已存档时不应读取凭据")):
            report = ws.run_batch(self.job(task))  # 不传 client_factory：只要试图联网就会先读凭据
        self.assertEqual((report.exit_code, len(report.reused), len(report.fetched)), (0, 2, 0))
        self.assertTrue((task.out / "keyword_host.json").is_file())

    def test_failed_query_is_left_out_and_retried_next_time(self) -> None:
        task = TaskDir(self.base, ["good one", "bad one"])
        flaky = FakeServer(lambda q: ({"code": "40002", "message": "down"}, True) if q == "bad one" else {"papers": [PAPER], "stats": {}})
        report = ws.run_batch(self.job(task, tool="deep_search"), client_factory=flaky.client)
        self.assertEqual(report.exit_code, 1)
        summary = json.loads((task.out / "keyword_host.summary.json").read_text(encoding="utf-8"))
        self.assertEqual([f["query"] for f in summary["failed"]], ["bad one"])
        self.assertEqual(set(load_host_results(task.out / "keyword_host.json")), {"good one"})
        healed = FakeServer()
        report = ws.run_batch(self.job(task, tool="deep_search"), client_factory=healed.client)
        self.assertEqual(report.exit_code, 0)
        self.assertEqual([c["payload"]["params"]["arguments"]["query"] for c in healed.tool_calls()], ["bad one"])

    def test_budget_leaves_pending_with_exit_4(self) -> None:
        task = TaskDir(self.base, ["q1", "q2", "q3"])
        ticks = iter([0.0] + [10_000.0] * 10)
        report = ws.run_batch(self.job(task), client_factory=FakeServer().client, clock=lambda: next(ticks))
        self.assertEqual(report.exit_code, 4)
        summary = json.loads((task.out / "keyword_host.summary.json").read_text(encoding="utf-8"))
        self.assertEqual(len(summary["pending"]), 3)

    def test_auth_failure_exits_3_and_never_leaks_secrets(self) -> None:
        task = TaskDir(self.base, ["q1", "q2"])
        denied = FakeServer(lambda q: ({"code": "40101", "message": "denied"}, True))
        report = ws.run_batch(self.job(task), client_factory=denied.client)
        self.assertEqual(report.exit_code, 3)
        for path in task.out.rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(SECRET_TOKEN, text)
            self.assertNotIn("gateway.invalid", text)

    def test_network_error_message_hides_gateway(self) -> None:
        import requests
        task = TaskDir(self.base, ["q1"])

        def post(p: dict, h: dict):
            raise requests.ConnectionError(f"HTTPSConnectionPool(host='gateway.invalid', port=443): Max retries exceeded url={SECRET_URL}")

        report = ws.run_batch(self.job(task), client_factory=lambda: ws.McpClient(SECRET_URL, SECRET_TOKEN, post=post, sleep=lambda s: None))
        self.assertEqual(report.exit_code, 1)
        self.assertNotIn("gateway.invalid", json.dumps(report.failed))

    def test_untitled_papers_stay_in_raw_but_not_in_host(self) -> None:
        task = TaskDir(self.base, ["q1"])
        server = FakeServer(lambda q: {"papers": [PAPER, dict(PAPER, title="  ")], "stats": {}})
        ws.run_batch(self.job(task), client_factory=server.client)
        raw = next((task.out / "raw" / "keyword").glob("*.json"))
        self.assertEqual(len(json.loads(raw.read_text(encoding="utf-8"))["papers"]), 2)
        host = json.loads((task.out / "keyword_host.json").read_text(encoding="utf-8"))
        self.assertEqual(len(host["queries"][0]["papers"]), 1)


class PrepareAndCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_paths_and_name_are_checked(self) -> None:
        task = TaskDir(self.base, ["q1"])
        outside = self.base / "q.json"
        outside.write_text('{"queries": ["q"]}', encoding="utf-8")
        for args in ((task.root, "keyword", "quick_search", outside), (self.base, "keyword", "quick_search", task.query_file),
                     (task.root, "Bad Name", "quick_search", task.query_file), (task.root, "keyword", "other", task.query_file)):
            with self.assertRaises(ws.ProposalError):
                ws.prepare_job(*args, config=CONFIG)

    def test_top_n_defaults_by_tool_and_is_clamped(self) -> None:
        task = TaskDir(self.base, ["q1"])
        self.assertEqual(ws.prepare_job(task.root, "k", "quick_search", task.query_file, config=CONFIG).top_n, 20)
        self.assertEqual(ws.prepare_job(task.root, "k", "deep_search", task.query_file, config=CONFIG).top_n, 10)
        self.assertEqual(ws.prepare_job(task.root, "k", "deep_search", task.query_file, 500, config=CONFIG).top_n, 100)

    def test_cli_without_credentials_exits_3_without_values(self) -> None:
        task = TaskDir(self.base, ["q1"])
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPYCACHEPREFIX": str(ROOT / ".bensz-api" / "pycache")}
        proc = subprocess.run([sys.executable, str(SCRIPTS / "wispaper_search.py"), "run", "--task-root", str(task.root),
                               "--name", "keyword", "--tool", "quick_search", "--query-file", str(task.query_file)],
                              env=env, cwd=self.base, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("WIS_MCP_URL", proc.stderr)


if __name__ == "__main__":
    unittest.main()
```

`test_cli_without_credentials_exits_3_without_values` 依赖 skill 目录下没有 `.env`。若控制者告知本机 skill 目录有 `.env`，改为用 `mock.patch.object(ws, "SKILL_DIR", 临时目录)` 在进程内调用 `ws.main([...])`。

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_wispaper_search.py`
Expected: FAIL（`ModuleNotFoundError: No module named 'wispaper_search'`）

- [ ] **Step 3: 写脚本**

**传输层** `skills/nsfc-proposal/scripts/wis_mcp_client.py`：照搬团队 academic-literature skill 中 `scripts/wis_mcp_search.py` 的第 38–56 行（协议版本、错误码常量）与第 82–321 行（`McpError`、`McpAuthError`、`McpRateLimited`、`_decode_body`、`_parse_sse_or_json`、`McpClient`），模块文档字符串写明出处与日期。只做四处改动：

- `time.sleep` 改为构造参数 `sleep: Callable[[float], None] = time.sleep`，`call_tool` 中用 `self._sleep`；
- 构造参数 `timeout` 的默认值改为 `(30, 300)`；
- `CLIENT_INFO` 改为 `{"name": "nsfc-proposal-wispaper", "version": "0.1"}`；
- 不搬它的 `_load_dotenv`、`client_from_env`、`search`、`main`（凭据走 `envfile`，不写 `os.environ`）。

控制者会在派发时给出该文件的路径；文件不可读时，按测试自己实现同样的协议（initialize → notifications/initialized → tools/call，`Mcp-Session-Id` 会话头，SSE 按 `\n` 切行并从 `content` 解 UTF-8，401/40101 为鉴权错误，429/42901 退避重试，40001/40002/50001 不重试，`onAgentError` 事件视为失败）。

**批处理** `skills/nsfc-proposal/scripts/wispaper_search.py`：

```python
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


def _error_text(exc: Exception) -> str:
    """MCP 错误照录（含 request-id，不含地址与 token）；网络错误只写类型，因为 requests 的信息会带出主机名与地址。"""
    if isinstance(exc, requests.RequestException):
        return f"网络错误（{type(exc).__name__}）"
    return str(exc)


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
            if getattr(local, "client", None) is None:
                local.client = factory()
            try:
                data = local.client.call_tool(job.tool, {"query": query, "top_n": job.top_n})
            except McpAuthError as exc:
                with lock:
                    report.auth_failed = True
                    report.failed.append({"query": query, "error": _error_text(exc)})
                return
            except (McpError, requests.RequestException) as exc:
                with lock:
                    report.failed.append({"query": query, "error": _error_text(exc)})
                return
            _write_json(job.raw_path(query), data)
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
```

`config.yaml` 的 `literature` 段在 `deep_search_top_n` 后加：

```yaml
  wispaper_workers: 4          # wispaper_search.py 的并发检索数
  wispaper_timeout_s: 300      # 单次检索的读超时（deep_search 一次 40 秒起，top_n 大时更久）
  wispaper_batch_budget_s: 240 # 到时不再发起新检索，未查的留到下一次运行（退出码 4）；加上单次读超时，一次运行不超过 10 分钟
```

- [ ] **Step 4: 改 SKILL.md**

第 3 步第 4 项整段替换为：

```markdown
4. `config.yaml` 中 `literature.use_wispaper` 为 true 时，用 `scripts/wispaper_search.py` 检索。凭据 `WIS_MCP_URL`、`WIS_MCP_TOKEN` 由脚本从环境变量或上级目录的 `.env` 读取，不要打开 `.env`。

   ```bash
   python3 S/scripts/wispaper_search.py run --task-root T --name keyword --tool quick_search \
     --query-file T/nsfc-proposal/input/keyword_queries.json
   python3 S/scripts/wispaper_search.py run --task-root T --name claims_1 --tool deep_search \
     --query-file T/nsfc-proposal/input/claim_queries_1.json
   ```

   - `top_n` 默认取 `literature.quick_search_top_n` 与 `literature.deep_search_top_n`。
   - 每条检索式的原始返回逐字存进 `T/nsfc-proposal/output/wispaper/raw/<名称>/`，再汇成 `T/nsfc-proposal/output/wispaper/<名称>_host.json`（`rls.host_results.v1`），汇总在 `<名称>_host.summary.json`。不要改写这些文件。
   - 退出码 0：完成。4：到了单次时限，原样再跑同一条命令，已存档的不重查。1：有检索式失败，原样再跑一次；仍失败的检索式在 `stages.md` 记下，按「失败与恢复」处理。3：未配置或凭据被拒，按「wispaper 不可用」处理。
   - 不要用 MCP 工具（`mcp__wis-scholar-search__*`）做检索：返回只进对话，不落文件，台账无从追溯。它只可用于一次性探测，例如检查服务是否可用。
```

第 5 项代码块中的 `--host-results` 路径改为 `T/nsfc-proposal/output/wispaper/keyword_host.json` 与 `T/nsfc-proposal/output/wispaper/claims_1_host.json`。

「失败与恢复」表中 wispaper 一行改为两行：

```markdown
| wispaper 不可用（`wispaper_search.py` 退出码 3） | 不传 `--host-results`，改用 research-literature-search 的现有检索源；论断 bundle 同时去掉 `--no-fallback` |
| 部分检索式重跑后仍失败（退出码 1） | 关键词 bundle 照常传 `--host-results`，失败的检索式由其他检索源补。论断 bundle：OpenAlex 不接受带问号的问句，把失败的问句改写成关键词式检索式，写入新的 `claim_queries_<n>.json`，不带 `--no-fallback` 检索；在 `stages.md` 记录 |
```

第 3 步第 6 项中「按本步第 4、5 项检索」保持不变。

README.md 凭据一节加三行（只写变量名与用途，不写值和地址）：`WIS_MCP_URL`（wis-scholar-search 的 MCP 端点）、`WIS_MCP_TOKEN`（Bearer token，不带 `Bearer ` 前缀）、`WIS_MCP_CONSUMER`（可选，网关要求时填）。

- [ ] **Step 5: 运行，确认通过**

Run: 全局约束中的测试命令。Expected: 0 failed。

- [ ] **Step 6: 提交**

```bash
git add skills/nsfc-proposal tests/nsfc-proposal/test_np_wispaper_search.py CHANGELOG.md
git commit -m "feat(nsfc-proposal): wispaper 检索由脚本落盘存档"
```

CHANGELOG 0.1.0 段补一句：「wispaper 检索改由 `scripts/wispaper_search.py` 执行：传输层并入自 academic-literature，原始返回逐字存档，断点续查，汇成 rls.host_results.v1；不再用 MCP 工具做检索轮次（来源：funded-2 验证运行，280 条记录只能手抄）。」

---

### Task 2: 写法文档：出图标签不带括号、动作匹配的对照、编译命令

funded-2 的框架图第一次不合格：模型把提示词骨架里标替换处的〈〉画进了图。研究一比较「动手做」与「只想不做」两组的神经信号，两组动作量不同，没有排除单纯动作的对照；现有规则只管基线与非特异效应。编译命令带相对路径 `--project-dir` 时，项目脚本在项目目录下解析它，报「项目目录不存在」。

**Files:**
- Modify: `skills/nsfc-proposal/references/figure_guide.md`（第 3 节第 2、4 条；第 6 节）
- Modify: `skills/nsfc-proposal/references/section_boundaries.md:42-46`
- Modify: `skills/nsfc-proposal/SKILL.md:249`
- Modify: `tests/nsfc-proposal/test_np_skill_docs.py`
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

**Interfaces:**
- Consumes: 无。
- Produces: 文档文字，供后续运行读取。

- [ ] **Step 1: 写失败的测试**

在 `tests/nsfc-proposal/test_np_skill_docs.py` 中加一个测试类（沿用该文件读取文档的写法）：

```python
class RoundThreeDocsTest(unittest.TestCase):
    def test_figure_labels_carry_no_brackets(self) -> None:
        guide = (SKILL / "references" / "figure_guide.md").read_text(encoding="utf-8")
        self.assertIn("不加括号、引号或书名号", guide)
        self.assertIn("连同〈〉一起换掉", guide)
        self.assertIn("没有清单以外的符号", guide)

    def test_motor_matched_control_rule(self) -> None:
        bounds = (SKILL / "references" / "section_boundaries.md").read_text(encoding="utf-8")
        self.assertIn("动作匹配的对照", bounds)
        self.assertIn("出声朗读", bounds)
        self.assertIn("前三条", bounds)

    def test_build_command_has_no_relative_project_dir(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`python3 P/scripts/nsfc_build.py`", skill)
        self.assertNotIn("nsfc_build.py build --project-dir P", skill)
```

`SKILL` 指 `skills/nsfc-proposal` 目录；若文件中已有同义常量，用已有的。

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_skill_docs.py`
Expected: FAIL（3 个新测试）

- [ ] **Step 3: 改文档**

`figure_guide.md` 第 3 节第 2 条末尾加：

```markdown
   标签原文直接写在「写」字后面，几个标签用顿号隔开，不加括号、引号或书名号。下面骨架里的〈〉只标出替换处，写提示词时连同〈〉一起换掉。实测时模型会把这些符号画进图里。
```

第 3 节第 4 条的规则句改为：「图中所有可见文字只能使用以下内容：……；图中不要出现任何分区名称、面板编号或说明性文字；不得出现清单以外的英文、拼音、汉字或符号」。

第 6 节自检清单第二条改为：「每个可见标签都在可见文字清单中；没有内部编号；没有清单以外的符号（括号、引号、书名号）。」

`section_boundaries.md` 第 42–46 行（「设计」小标题下的对照与基线）改为：

```markdown
「设计」小标题下写对照与基线：

- 采集神经或生理信号（脑电、功能磁共振、心率、皮电等）时，各任务阶段之间设静息或低负荷基线，写明时长。例：每个任务块前设 60 秒静息基线（注视屏幕中央的十字），任务块之间设 30 秒低负荷基线（被动观看灰色图形）。
- 采集神经或生理信号，而各条件的动作不同（一组动手或出声，另一组只看或只想）时，设一个动作匹配的对照：动作相同，只少了要研究的认知加工。否则信号差异可能只来自动作本身。例：语言产出研究中，被试出声命名图片；另设一个条件，出声朗读同一组词语，发音动作相同，只少了从图片提取词汇这一步。
- 操纵可能带来非特异效应（如额外的关注与接触、干预时长、新奇感、安慰剂效应）时，设一个排除这一效应的对照条件。例：干预组每周接受一次用药指导随访；对照组每周接受同等时长的一般健康宣教，随访次数与时长相同，只少了用药指导这一内容。
- 前两条只在采集神经或生理信号时适用，第三条只在操纵可能带来非特异效应时适用；前三条都不强加给数据驱动研究。
```

`SKILL.md` 第 249 行的编译命令改为：「项目有编译脚本且本机字体齐全时运行它（`python3 P/scripts/nsfc_build.py`，不带参数时编译脚本所在的项目；不要传相对路径的 `--project-dir`，脚本在项目目录下解析它）……」，其余文字不变。

- [ ] **Step 4: 运行，确认通过**

Run: 全局约束中的测试命令。Expected: 0 failed。再运行 `git grep -n -E "创造|具身|物化|照样|近红外|综合实践|课时|班级" -- skills/nsfc-proposal/references/section_boundaries.md skills/nsfc-proposal/references/figure_guide.md`，Expected: 无输出。

- [ ] **Step 5: 提交**

```bash
git add skills/nsfc-proposal tests/nsfc-proposal/test_np_skill_docs.py CHANGELOG.md
git commit -m "docs(nsfc-proposal): 出图标签不带括号，神经测量加动作匹配的对照，编译命令不传相对路径"
```

CHANGELOG 0.1.0 段补一句：「作图提示词的标签不加括号、引号、书名号，自检查清单外符号；动作不同的条件间比较神经或生理信号时，设动作匹配的对照；编译命令不带相对路径的 `--project-dir`（来源：funded-2 验证运行）。」

---

### Task 3: 一致性检查：嘱咐语漏检与占位格式误报

funded-2 研究基础中有一句写给申请人的嘱咐：「这些论文将在正式申请书中按……列出」。`process_text_patterns` 没有覆盖「正式申请书」，检查没拦住。AI 使用说明里写了「未提供的内容以【待补充：……】标出」，这是在说明占位格式，检查却把它当成占位，要求列入占位清单。

**Files:**
- Modify: `skills/nsfc-proposal/config.yaml:52`（`process_text_patterns` 末尾加三项）
- Modify: `skills/nsfc-proposal/scripts/consistency_check.py`（占位扫描，第 246–251 行附近）
- Modify: `tests/nsfc-proposal/test_np_consistency.py`
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

**Interfaces:**
- Consumes: 无。
- Produces: `check_project` 的 `placeholders` 与 `placeholder_unlisted` 不再包含内文只有省略号、点或空白的占位。

- [ ] **Step 1: 写失败的测试**

在 `ProcessTextTest`（含 `_hits` 的那个类）中加：

```python
    def test_wording_meant_for_the_applicant_is_flagged(self) -> None:
        for sentence in ("这些论文将在正式申请书中按三类列出。", "正式稿中补全设备型号。", "请申请人补充合作单位名称。"):
            self.assertGreaterEqual(len(self._hits(f"多模态。\n{sentence}\n")), 1, sentence)
```

在 `NonstandardPlaceholderTest` 中加：

```python
    def test_placeholder_format_reference_is_not_a_placeholder(self) -> None:
        for text in ("未提供的内容以【待补充：……】标出。\n", "格式为【待补充：...】。\n", "格式为【待补充：  】。\n"):
            root = self._root(text)
            report = check_project(root)
            self.assertEqual([f for f in report.errors if f.kind == "placeholder_unlisted"], [], text)
            self.assertEqual([f for f in report.placeholders if f.file == "NSFC-ABSTRACTS.md"], [], text)

    def test_real_unlisted_placeholder_still_errors(self) -> None:
        root = self._root("前期结果【待补充：未列入的条目】。\n")
        self.assertEqual([f.detail for f in check_project(root).errors if f.kind == "placeholder_unlisted"],
                         ["【待补充：未列入的条目】"])
```

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_consistency.py`
Expected: FAIL（嘱咐语未命中；格式说明被当作未列入的占位）

- [ ] **Step 3: 改代码与配置**

`config.yaml` 第 52 行 `process_text_patterns` 末尾加 `"正式申请书", "正式稿", "请申请人"`。

`consistency_check.py` 在常量区加：

```python
FORMAT_REFERENCE_RE = re.compile(r"【待补充：[\s.…·]*】")  # 内文只有省略号、点或空白：是在说明占位格式，不是占位
```

占位循环改为跳过这种匹配：

```python
            for match in placeholder_re.finditer(body):
                if FORMAT_REFERENCE_RE.fullmatch(match.group(0)):
                    continue
                report.placeholders.append(Finding("placeholder", rel, number, match.group(0)))
                if match.group(0) not in assumptions:
                    report.errors.append(Finding("placeholder_unlisted", rel, number, match.group(0)))
```

`placeholder_re.sub("", ...)` 的两处（非标准占位扫描、过程说明扫描）保持不变：格式说明在那两处本来就该被去掉。

- [ ] **Step 4: 运行，确认通过**

Run: 全局约束中的测试命令。Expected: 0 failed。

- [ ] **Step 5: 提交**

```bash
git add skills/nsfc-proposal tests/nsfc-proposal/test_np_consistency.py CHANGELOG.md
git commit -m "fix(nsfc-proposal): 一致性检查拦「正式申请书」类嘱咐，不把占位格式说明当占位"
```

CHANGELOG 0.1.0 段补一句：「过程说明词加入「正式申请书」「正式稿」「请申请人」；内文只有省略号的【待补充：……】视为格式说明，不计入占位（来源：funded-2 验证运行）。」

---

### Task 4: 研究基础检查：风险条目计数

`check_project_outputs.py` 第 101、102 行把正则写在原始字符串里又多转义了一次（`r"风险\\s*..."`），匹配的是字面的反斜杠加 s。「风险一」「风险二」这类写法永远数不到，funded-2 只能把每条风险改成一个小标题才过检查。第 99、100 行匹配的是 LaTeX 命令里的反斜杠，写法正确，不要动。

**Files:**
- Modify: `skills/nsfc-research-foundation-writer/scripts/check_project_outputs.py:101-102`
- Modify: `skills/nsfc-research-foundation-writer/CHANGELOG.md`（0.2.0 段）、根 `CHANGELOG.md`
- Create: `tests/nsfc-research-foundation-writer/test_nrfw_risk_count.py`

**Interfaces:**
- Consumes: 无。
- Produces: 无新接口。

- [ ] **Step 1: 写失败的测试**

```python
"""研究基础检查：「风险一」「风险 2」一类写法计入风险条目。"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/nsfc-research-foundation-writer/scripts/check_project_outputs.py"
CONDITIONS = "已具备的条件：实验室。尚缺的条件及解决途径：无。\n"


def run_check(foundation: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        extra = Path(tmp) / "extraTex"
        extra.mkdir()
        (extra / "3.1.研究基础.tex").write_text(foundation, encoding="utf-8")
        (extra / "3.2.工作条件.tex").write_text(CONDITIONS, encoding="utf-8")
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        return subprocess.run([sys.executable, str(SCRIPT), "--project-root", tmp], env=env,
                              capture_output=True, text=True, timeout=60)


class RiskCountTest(unittest.TestCase):
    def test_numbered_risks_in_running_text_count(self) -> None:
        text = "\\subsubsection{风险与应对}\n风险一：数据不足；应对：扩大来源。\n风险二：进度延迟；应对：预留缓冲。\n风险三：设备故障；应对：备用设备。\n"
        proc = run_check(text)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_arabic_numbers_count(self) -> None:
        proc = run_check("风险 1：甲；应对：乙。\n风险 2：丙；预案：丁。\n风险 3：戊；替代：己。\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_single_risk_heading_still_fails(self) -> None:
        proc = run_check("\\subsubsection{风险与应对}\n数据可能不足，应对是扩大来源。\n")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("< 3 risk items", proc.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-research-foundation-writer/test_nrfw_risk_count.py`
Expected: 前两个测试 FAIL（found 1 / found 0）

- [ ] **Step 3: 改正则**

```python
    risk_items += re.findall(r"(?m)^\s*#+\s*.*风险.*$", foundation_text)  # markdown-like headings (rare)
    risk_items += re.findall(r"风险\s*(?:\d+|[一二三四五六七八九十])", foundation_text)
```

- [ ] **Step 4: 运行，确认通过**

Run: 全局约束中的测试命令（已含 `tests/nsfc-research-foundation-writer`）。Expected: 0 failed。

- [ ] **Step 5: 提交**

```bash
git add skills/nsfc-research-foundation-writer tests/nsfc-research-foundation-writer CHANGELOG.md
git commit -m "fix(nsfc-research-foundation-writer): 风险条目计数的正则去掉多余转义"
```

CHANGELOG 0.2.0 段（在 BAC 那行之前）补一句：「修复风险条目计数：正则在原始字符串中多转义一次，「风险一」「风险 2」一类写法从未计入（来源：funded-2 验证运行）。」

---

### Task 5: bib_resolve：书章与图书的条目类型

`crossref_meta` 把 CrossRef 中 `journal-article` 以外、非 `proceedings-article` 的类型一律写成 `@misc`，书名放进 `howpublished`。项目模板用的参考文献样式 `gbt7714-nsfc.bst` 渲染 `@misc` 时不读 `howpublished`，读 `publisher`；渲染 `@incollection` 时读 `booktitle`（必填）和 `publisher`。所以书章在参考文献表里没有出处。

**Files:**
- Modify: `skills/nsfc-proposal/scripts/bib_resolve.py`（`WorkMeta`、`crossref_meta`、`openalex_meta`、`to_bibtex`）
- Modify: `tests/nsfc-proposal/test_np_bib_resolve.py`（`HelperTest`）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

**Interfaces:**
- Consumes: 无。
- Produces: `WorkMeta` 新增字段 `publisher: str | None = None`（放在 `entry_type` 之后，带默认值，现有构造调用不受影响）；`crossref_meta`、`openalex_meta` 按类型给出 `entry_type`。

- [ ] **Step 1: 写失败的测试**

在 `test_np_bib_resolve.py` 的导入行加入 `crossref_meta, openalex_meta`，在 `HelperTest` 中加：

```python
    def test_crossref_book_chapter_becomes_incollection(self) -> None:
        item = {"type": "book-chapter", "title": ["Divergent Thinking as a Process"], "author": [{"family": "Doe", "given": "Jane"}],
                "container-title": ["Handbook of Test Methods"], "publisher": "Test Press", "page": "3-16",
                "issued": {"date-parts": [[2023]]}, "DOI": "10.1000/ch1"}
        meta = crossref_meta(item)
        self.assertEqual((meta.entry_type, meta.publisher), ("incollection", "Test Press"))
        entry = to_bibtex(meta, "k")
        self.assertTrue(entry.startswith("@incollection{k,"))
        self.assertIn("booktitle = {Handbook of Test Methods}", entry)
        self.assertIn("publisher = {Test Press}", entry)
        self.assertNotIn("howpublished", entry)

    def test_crossref_book_and_other_types(self) -> None:
        book = crossref_meta({"type": "monograph", "title": ["A Book"], "publisher": "P", "issued": {"date-parts": [[2020]]}})
        self.assertEqual(book.entry_type, "book")
        self.assertIn("publisher = {P}", to_bibtex(book, "b"))
        other = crossref_meta({"type": "dataset", "title": ["Some Data"], "container-title": ["Data Hub"], "publisher": "Hub Inc"})
        entry = to_bibtex(other, "d")
        self.assertTrue(entry.startswith("@misc{d,"))
        self.assertIn("publisher = {Hub Inc}", entry)
        self.assertIn("howpublished = {Data Hub}", entry)

    def test_chapter_without_container_or_publisher_does_not_fail(self) -> None:
        meta = crossref_meta({"type": "book-chapter", "title": ["Lonely Chapter"], "issued": {"date-parts": [[2021]]}})
        entry = to_bibtex(meta, "c")
        self.assertTrue(entry.startswith("@incollection{c,"))
        self.assertNotIn("booktitle", entry)
        self.assertNotIn("publisher", entry)

    def test_openalex_book_chapter(self) -> None:
        item = {"title": "Chapter T", "type": "book-chapter", "publication_year": 2019,
                "primary_location": {"source": {"display_name": "Book B", "host_organization_name": "Pub P"}}}
        meta = openalex_meta(item)
        self.assertEqual((meta.entry_type, meta.journal, meta.publisher), ("incollection", "Book B", "Pub P"))
```

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_bib_resolve.py`
Expected: FAIL（`crossref_meta` 不可导入，或 `entry_type` 为 `misc`）

- [ ] **Step 3: 改代码**

```python
CROSSREF_TYPES = {"journal-article": "article", "proceedings-article": "inproceedings", "book-chapter": "incollection",
                  "book-part": "incollection", "book-section": "incollection", "book": "book", "monograph": "book",
                  "edited-book": "book", "reference-book": "book"}
OPENALEX_TYPES = {"article": "article", "book-chapter": "incollection", "book": "book"}
```

- `WorkMeta` 加 `publisher: str | None = None`。
- `crossref_meta`：`entry_type = "article" if kind is None else CROSSREF_TYPES.get(kind, "misc")`；`publisher=_str(item.get("publisher"))`。
- `openalex_meta`：`entry_type=OPENALEX_TYPES.get(item.get("type"), "article")`；`publisher=_str(source.get("host_organization_name"))`。
- `to_bibtex`：`venue_field = {"article": "journal", "inproceedings": "booktitle", "incollection": "booktitle", "book": None}.get(meta.entry_type, "howpublished")`；`fields` 中 venue 一项在 `venue_field` 为 None 时跳过；在 `year` 之前加 `("publisher", _escape(meta.publisher) if meta.publisher else None)`。

现有测试中 `WorkMeta(...)` 的位置参数调用不变；`test_np_bib_resolve.py` 中对 `@misc` 的已有断言若与新映射冲突，按新映射改断言并在提交说明里写明。

- [ ] **Step 4: 运行，确认通过**

Run: 全局约束中的测试命令。Expected: 0 failed。

- [ ] **Step 5: 提交**

```bash
git add skills/nsfc-proposal tests/nsfc-proposal/test_np_bib_resolve.py CHANGELOG.md
git commit -m "fix(nsfc-proposal): 书章写成 @incollection、图书写成 @book，带出版者"
```

CHANGELOG 0.1.0 段补一句：「bib_resolve 按 CrossRef/OpenAlex 类型写条目：书章为 @incollection（booktitle、publisher），图书为 @book；其余 @misc 也带 publisher。参考文献样式不渲染 howpublished，书章此前没有出处（来源：funded-2 验证运行）。」

---

### Task 6: 信息表的占位以 section_plan 为准

研究基础信息表把缺失的可行性条目原文包成占位（`【待补充：已有与本项目相关的论文发表，具体论文清单】`），而 `section_plan.yaml` 的 `placeholders` 是第 4 步另写的（`【待补充：已发表的相关论文清单（题目、期刊、年份、DOI）】`）。同一缺失项有两种写法，要靠人统一。改为只用 `section_plan.yaml` 的写法。

**Files:**
- Modify: `skills/nsfc-proposal/scripts/case_render.py`（`_section_notes` 第 168–178 行；`_foundation_form` 第 261 行）
- Modify: `tests/nsfc-proposal/test_np_render.py`（`InfoFormTest`）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

**Interfaces:**
- Consumes: `section_plan.yaml` 中各文件的 `placeholders`（完整的 `【待补充：……】` 字符串列表）。
- Produces: 各写作 skill 的信息表「可选补充」中多一行「<文件> 占位（逐字照抄，不改写）：……」；研究基础信息表中缺失项不再自拟占位文字。

- [ ] **Step 1: 写失败的测试**

```python
    def test_foundation_form_uses_section_plan_placeholders(self) -> None:
        plan = valid_plan()
        for entry in plan["files"]:
            if entry["file"] == "extraTex/3.1.研究基础.tex":
                entry["placeholders"] = ["【待补充：预实验的设计、样本量与主要结果】"]
        form = info_form(valid_case(), plan, "nsfc-research-foundation-writer")
        self.assertIn("【待补充：预实验的设计、样本量与主要结果】", form)
        self.assertIn("逐字照抄", form)
        self.assertNotIn("【待补充：预实验结果】", form)  # 不再用可行性条目原文自拟占位
        self.assertIn("预实验结果", form)               # 缺失项本身仍列出
```

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_render.py`
Expected: FAIL（表中仍是 `【待补充：预实验结果】`，没有 section_plan 的写法）

- [ ] **Step 3: 改代码**

`_section_notes` 在 `must_exclude` 那段之后加：

```python
        placeholders = _strs(entry.get("placeholders"))
        if placeholders:
            notes.append(f"{entry.get('file')} 占位（逐字照抄，不改写）：{'；'.join(placeholders)}")
```

`_foundation_form` 第 261 行改为：

```python
            entries.append(text if item.get("source") == "user_material" else f"缺失：{text}。正文写「可选补充」中列出的对应占位，逐字照抄，不得略去或编造")
```

`_justification_form` 第 191 行不改：立项依据的信息表不负责研究基础的占位。

已有测试 `test_foundation_form_marks_missing_items_as_placeholders` 仍应通过（`valid_plan()` 的占位与可行性原文同为「预实验结果」）。

- [ ] **Step 4: 运行，确认通过**

Run: 全局约束中的测试命令。Expected: 0 failed。

- [ ] **Step 5: 提交**

```bash
git add skills/nsfc-proposal tests/nsfc-proposal/test_np_render.py CHANGELOG.md
git commit -m "fix(nsfc-proposal): 信息表的占位只取 section_plan 的写法"
```

CHANGELOG 0.1.0 段补一句：「信息表列出 section_plan 中的占位并要求逐字照抄；研究基础的缺失项不再自拟占位文字，同一缺失项只有一种写法（来源：funded-2 验证运行）。」

---

### Task 7: 验证运行 fresh-1（控制者安排，不改代码）

前提：Task 1–6 全部提交，终审通过，已推送到 `lauorie`。运行期间仓库不做任何提交。

- 题目与对比基准、skill 示例都不相关：青年科学基金项目，申请人请求写在评测目录的 `input_fresh.md`，颗粒度与 `input_funded.md` 相同（题目、问题、研究设想、团队经验；论文清单写「待补充」；不写任何真实文献）。
- 项目目录用 `projects/NSFC_Young` 模板复制，`packages` 以符号链接只读使用。
- 派发提示词沿用 funded-2，改三处：文献检索按 SKILL 用 `scripts/wispaper_search.py`（凭据由脚本从上级 `.env` 读取，不打开 `.env`）；不再加载 MCP 检索工具；运行报告第一行写 `git -C <仓库> rev-parse HEAD` 的输出。
- 核对清单：
  - wispaper 原始返回由脚本存档，host 文件条数与检索式条数一致，没有手抄；
  - 年度计划为 3 年，`check_project_outputs.py --project-type 青年科学基金项目` 通过；
  - 政策文件经官方网站核对后写明，写进「## 官方文件」；
  - 群组随机的研究计入聚类，组内相关系数注明来源或注明为假设值；最小可检测效应与文献效应量比较；
  - 动作不同的条件间比较神经或生理信号时，有动作匹配的对照；
  - 出图：框架图与各研究设计图，图中没有括号；
  - 研究基础的占位与 section_plan 一致；
  - `citation_ledger.py audit` 为 0，`consistency_check.py` 为 0/0；
  - 参考文献中书章为 `@incollection` 并带出版者（如有书章）。
- 结果写进评测目录 `funded-comparison.md` 新的一节，不做盲评。
