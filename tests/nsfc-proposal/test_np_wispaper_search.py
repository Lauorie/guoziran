"""wispaper 检索脚本：MCP 会话、原始返回落盘、断点续查、汇成 rls.host_results.v1。不联网。"""
from __future__ import annotations

import contextlib
import io
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


    def test_gateway_echo_in_http_body_is_redacted(self) -> None:
        task = TaskDir(self.base, ["q1"])
        echo = f"Bad gateway at {SECRET_URL.upper()} host gateway.invalid auth Bearer {SECRET_TOKEN}"

        def post(p: dict, h: dict) -> FakeResponse:
            if p["method"] == "initialize":
                return FakeResponse(200, rpc(p["id"], {}), {"Mcp-Session-Id": "s"})
            if p["method"] == "notifications/initialized":
                return FakeResponse(202, "")
            return FakeResponse(502, echo)

        report = ws.run_batch(self.job(task), client_factory=lambda: ws.McpClient(SECRET_URL, SECRET_TOKEN, post=post, sleep=lambda s: None))
        self.assertEqual(report.exit_code, 1)
        self.assertIn("502", report.failed[0]["error"])
        self.assert_clean(task, report)

    def test_gateway_echo_in_auth_message_is_redacted(self) -> None:
        task = TaskDir(self.base, ["q1"])
        denied = FakeServer(lambda q: ({"code": "40101", "message": f"denied {SECRET_TOKEN} at gateway.invalid {SECRET_URL}"}, True))
        report = ws.run_batch(self.job(task), client_factory=denied.client)
        self.assertEqual(report.exit_code, 3)
        self.assert_clean(task, report)

    def assert_clean(self, task: TaskDir, report: ws.BatchReport) -> None:
        blob = json.dumps(report.failed) + (task.out / "keyword_host.summary.json").read_text(encoding="utf-8")
        for secret in (SECRET_TOKEN, "gateway.invalid", "GATEWAY.INVALID"):
            self.assertNotIn(secret, blob)

    def test_unexpected_exceptions_count_as_failures_and_summary_is_written(self) -> None:
        task = TaskDir(self.base, ["good", "bad list", "bad boom", "bad json"])

        def answer(q: str):
            if q == "bad list":
                return []
            return {"papers": [PAPER], "stats": {}}

        server = FakeServer(answer)
        real_post = server.post

        def post(p: dict, h: dict) -> FakeResponse:
            if p.get("method") == "tools/call":
                q = p["params"]["arguments"]["query"]
                if q == "bad boom":
                    raise RuntimeError(f"boom {SECRET_TOKEN}")
                if q == "bad json":
                    return FakeResponse(200, '{"jsonrpc": "2.0", "id": 3, "result": ')
            return real_post(p, h)

        report = ws.run_batch(self.job(task), client_factory=lambda: ws.McpClient(SECRET_URL, SECRET_TOKEN, post=post, sleep=lambda s: None))
        self.assertEqual(report.exit_code, 1)
        self.assertEqual({f["query"] for f in report.failed}, {"bad list", "bad boom", "bad json"})
        self.assertIn("RuntimeError", json.dumps(report.failed))
        self.assertNotIn(SECRET_TOKEN, json.dumps(report.failed))
        self.assertEqual(set(load_host_results(task.out / "keyword_host.json")), {"good"})
        self.assertEqual(len(json.loads((task.out / "keyword_host.summary.json").read_text(encoding="utf-8"))["failed"]), 3)


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
        sandbox = self.base / "sandbox"
        sandbox.mkdir()
        err = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(ws, "SKILL_DIR", sandbox), \
                mock.patch.object(ws.envfile, "dotenv_candidates", return_value=[sandbox / ".env"]), \
                contextlib.redirect_stderr(err):
            code = ws.main(["run", "--task-root", str(task.root), "--name", "keyword", "--tool", "quick_search",
                            "--query-file", str(task.query_file)])
        self.assertEqual(code, 3)
        self.assertIn("缺 WIS_MCP_URL、WIS_MCP_TOKEN", err.getvalue())

    def test_non_ascii_or_spaced_token_is_not_configured(self) -> None:
        task = TaskDir(self.base, ["q1"])
        for token in ("tok-密钥", "tok 1"):
            env = {"WIS_MCP_URL": SECRET_URL, "WIS_MCP_TOKEN": token}
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(ws.envfile, "dotenv_candidates", return_value=[]):
                with self.assertRaises(ws.WispaperNotConfigured) as ctx:
                    ws.load_credentials(task.root, skill_dir=self.base)
            self.assertNotIn(token, str(ctx.exception))
            self.assertIn("WIS_MCP_TOKEN", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
