from __future__ import annotations

import hashlib
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import materials  # noqa: E402
import wisdoc_client  # noqa: E402
from material_text import LocalText  # noqa: E402
from wisdoc_client import ASSET_PLACEHOLDER, USER_AGENT, WisDocError, WisDocNotConfigured, WisDocURLRejected  # noqa: E402

BASE = "http://gw.example.test:8123"
SECRET = "http://wisdoc-secret.invalid:8123"
LOCAL_TEXT = "\n".join(f"第{i}项：本研究拟建立肺磨玻璃结节浸润性预测模型，样本来自第{i}家医院的回顾性队列。" for i in range(6))
ENV_KEYS = ("WISDOCRS_BASE_URL", "WISDOC_ALLOWED_HOSTS", "WISDOC_CANARY_HEADER")
PROXY_KEYS = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self._body = body
        self.headers = mock.Mock(get_content_type=lambda: content_type)

    def read(self, amt: int | None = None) -> bytes:
        return self._body if amt is None else self._body[:amt]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class FakeOpener:
    """按（方法，地址）返回固定响应；未登记的地址让测试失败。"""

    def __init__(self, routes: dict[tuple[str, str], Any], log: list, on_open: Callable[[Any], None] | None = None) -> None:
        self.routes, self.log, self.on_open = routes, log, on_open

    def open(self, request: Any, timeout: Any = None) -> FakeResponse:
        self.log.append(request)
        if self.on_open:
            self.on_open(request)
        value = self.routes[(request.get_method(), request.full_url)]
        if isinstance(value, BaseException):
            raise value
        return value


class CountingBody(io.BytesIO):
    """记录被读走的字节数。"""

    consumed = 0

    def read(self, size: int | None = -1) -> bytes:
        data = super().read(size)
        self.consumed += len(data)
        return data


def json_response(payload: Any) -> FakeResponse:
    return FakeResponse(json.dumps(payload).encode())


def flow_routes(markdown: str, *, markdown_url: str = f"{BASE}/files/j1.md", job_id: Any = "j1",
                metadata: Any = None, extra: dict | None = None) -> dict:
    status = {"task_status": {"ready": True, "successful": True},
              "metadata": {"markdown_url": markdown_url} if metadata is None else metadata}
    routes = {
        ("POST", f"{BASE}/api/v2/documents"): json_response({"job_id": job_id}),
        ("GET", f"{BASE}/api/v2/documents/{job_id}"): json_response(status),
        ("GET", markdown_url): FakeResponse(markdown.encode(), "text/markdown"),
    }
    routes.update(extra or {})
    return routes


class IsolatedEnv(unittest.TestCase):
    """清空相关环境变量，cwd 与 skill 目录指向临时目录，避免读到本机的 .env。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.cwd = self.base / "cwd"
        self.cwd.mkdir()
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        self._patch(wisdoc_client, "SKILL_DIR", self.base / "skill")

    def _patch(self, target: Any, name: str, value: Any) -> Any:
        patcher = mock.patch.object(target, name, value)
        started = patcher.start()
        self.addCleanup(patcher.stop)
        return started


class EnvLookupTest(IsolatedEnv):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.base / "group" / "proj"
        self.root.mkdir(parents=True)

    def test_dotenv_in_project_parent_provides_base_url(self) -> None:
        (self.base / "group" / ".env").write_text(f"# 注释\nexport WISDOCRS_BASE_URL='{SECRET}/'\n", encoding="utf-8")
        self.assertEqual(wisdoc_client.resolve_base_url([self.root], cwd=self.cwd), SECRET)
        self.assertNotIn("WISDOCRS_BASE_URL", os.environ)

    def test_lookup_order(self) -> None:
        (self.base / "group" / ".env").write_text("WISDOCRS_BASE_URL=http://project.invalid\n", encoding="utf-8")
        self.assertEqual(wisdoc_client.resolve_base_url([self.root], cwd=self.cwd), "http://project.invalid")
        (self.cwd / ".env").write_text("WISDOCRS_BASE_URL=http://cwd.invalid\n", encoding="utf-8")
        self.assertEqual(wisdoc_client.resolve_base_url([self.root], cwd=self.cwd), "http://cwd.invalid")
        os.environ["WISDOCRS_BASE_URL"] = "http://environ.invalid"
        self.assertEqual(wisdoc_client.resolve_base_url([self.root], cwd=self.cwd), "http://environ.invalid")

    def test_missing_or_bad_url_raises_without_value(self) -> None:
        with self.assertRaises(WisDocNotConfigured):
            wisdoc_client.resolve_base_url([self.root], cwd=self.cwd)
        os.environ["WISDOCRS_BASE_URL"] = "wisdoc-secret.invalid:8123"
        with self.assertRaises(WisDocNotConfigured) as caught:
            wisdoc_client.resolve_base_url([self.root], cwd=self.cwd)
        self.assertNotIn("wisdoc-secret", str(caught.exception))

    def test_inline_comment_is_cut_from_unquoted_value(self) -> None:
        (self.cwd / ".env").write_text("WISDOCRS_BASE_URL=http://gw.example.test:9  # 网关\n", encoding="utf-8")
        self.assertEqual(wisdoc_client.resolve_base_url(cwd=self.cwd), "http://gw.example.test:9")
        self.assertEqual(wisdoc_client._dotenv_value("'a # b'  # c"), "a # b")
        self.assertEqual(wisdoc_client._dotenv_value("pass#word"), "pass#word")

    def test_base_url_with_space_or_hash_is_rejected_without_value(self) -> None:
        for value in ('"http://gw.example.test:9 # 网关"', "'http://gw.example.test/a b'", '"http://gw.example.test/#x"'):
            (self.cwd / ".env").write_text(f"WISDOCRS_BASE_URL={value}\n", encoding="utf-8")
            with self.assertRaises(WisDocNotConfigured) as caught:
                wisdoc_client.resolve_base_url(cwd=self.cwd)
            self.assertNotIn("gw.example", str(caught.exception))

    def test_reads_only_the_requested_key(self) -> None:
        (self.cwd / ".env").write_text("OTHER_SECRET=x\nWISDOC_CANARY_HEADER=blue\n", encoding="utf-8")
        self.assertEqual(wisdoc_client.read_dotenv_value("WISDOC_CANARY_HEADER", cwd=self.cwd), "blue")
        self.assertIsNone(wisdoc_client.read_dotenv_value("MISSING", cwd=self.cwd))
        self.assertFalse(hasattr(wisdoc_client, "read_dotenv"))


class HostRuleTest(unittest.TestCase):
    def test_host_allowed(self) -> None:
        cases = [
            ("gw.example.test", "gw.example.test", True), ("a.gw.example.test", "gw.example.test", True),
            ("cdn.example.test", "gw.example.test", True), ("x.cdn.example.test", "gw.example.test", True),
            ("example.test", "gw.example.test", False), ("notexample.test", "gw.example.test", False),
            ("evil.test", "gw.example.test", False), ("100.100.100.200", "gw.example.test", False),
            ("cdn.example.test", "example.test", True), ("other.test", "example.test", False),
            ("10.0.0.5", "10.0.0.5", True), ("10.0.0.6", "10.0.0.5", False),
        ]
        for host, base, expected in cases:
            self.assertEqual(wisdoc_client.host_allowed(host, base), expected, (host, base))
        self.assertTrue(wisdoc_client.host_allowed("files.other.test", "10.0.0.5", ["files.other.test"]))

    def test_check_url_schemes(self) -> None:
        conn = wisdoc_client._Conn(base_url="https://gw.example.test", canary="grey")
        self.assertEqual(conn.check_url("//cdn.example.test/x.png"), "https://cdn.example.test/x.png")
        for url in ("file:///etc/passwd", "ftp://gw.example.test/x", "data:image/png;base64,AAAA", "//evil.test/x.png",
                    "http://100.100.100.200/latest/meta-data/", "http://[::1"):
            with self.assertRaises(WisDocURLRejected, msg=url):
                conn.check_url(url)

    def test_redirect_handler_checks_each_hop(self) -> None:
        conn = wisdoc_client._Conn(base_url=BASE, canary="grey")
        handler = wisdoc_client._CheckedRedirectHandler(conn)
        request = urllib.request.Request(f"{BASE}/api/v2/documents/j1")
        fp = mock.Mock()
        with self.assertRaises(WisDocURLRejected):
            handler.redirect_request(request, fp, 302, "Found", {}, "http://evil.test/steal")
        fp.close.assert_called_once()
        follow = handler.redirect_request(request, mock.Mock(), 302, "Found", {}, "https://cdn.example.test/j1")
        self.assertEqual(follow.full_url, "https://cdn.example.test/j1")

    def test_opener_has_no_file_ftp_or_data_handlers(self) -> None:
        opener = wisdoc_client._make_opener(wisdoc_client._Conn(base_url=BASE, canary="grey"))
        names = {type(h).__name__ for h in opener.handlers}
        self.assertFalse(names & {"FileHandler", "FTPHandler", "DataHandler", "CacheFTPHandler"})
        self.assertIn("_CheckedRedirectHandler", names)


class ClientTest(IsolatedEnv):
    def setUp(self) -> None:
        super().setUp()
        self.out = self.base / "out"
        self.pdf = self.base / "张三_论文.pdf"
        self.pdf.write_bytes(b"%PDF fake content")
        self.requests: list[Any] = []

    def parse(self, routes: dict, on_open: Callable[[Any], None] | None = None, **kwargs: Any) -> dict:
        options = dict(pdf_path=str(self.pdf), output_dir=self.out, base_url=BASE, cwd=self.cwd, poll_timeout_s=5,
                       poll_interval_s=0, markdown_name="wisdoc.md", assets_dirname="assets")
        options.update(kwargs)
        with mock.patch.object(wisdoc_client, "_make_opener", lambda conn: FakeOpener(routes, self.requests, on_open)):
            return wisdoc_client.parse_pdf_to_markdown(**options)

    def urls(self) -> list[str]:
        return [r.full_url for r in self.requests]

    def test_full_flow_writes_markdown_and_assets_without_identity(self) -> None:
        routes = flow_routes("# 标题\n\n正文\n\n![f](img/a.png)\n", extra={
            ("GET", f"{BASE}/files/img/a.png"): FakeResponse(b"png", "image/png")})
        payload = self.parse(routes)
        markdown = (self.out / "wisdoc.md").read_text(encoding="utf-8")
        self.assertIn("![f](assets/001_a.png)", markdown)
        self.assertTrue((self.out / "assets" / "001_a.png").is_file())
        self.assertNotIn("gw.example", json.dumps(payload))
        for request in self.requests:
            headers = dict(request.header_items())
            self.assertLessEqual({k.lower() for k in headers}, {"x-canary", "content-type", "user-agent"})
            self.assertEqual(headers["User-agent"], USER_AGENT)
            self.assertFalse(any("@" in v for v in headers.values()))
        upload = self.requests[0].data
        self.assertIn(f'filename="{hashlib.sha256(self.pdf.read_bytes()).hexdigest()[:16]}.pdf"'.encode(), upload)
        self.assertNotIn(self.pdf.name.encode("utf-8"), upload)
        self.assertNotIn("张三".encode("utf-8"), upload)

    def test_canary_and_allowed_hosts_come_from_project_dotenv(self) -> None:
        project = self.base / "group" / "proj"
        project.mkdir(parents=True)
        (self.base / "group" / ".env").write_text("WISDOC_CANARY_HEADER=blue\nWISDOC_ALLOWED_HOSTS=x.test, files.other.test\n",
                                                  encoding="utf-8")
        md_url = "http://files.other.test/j1.md"
        with self.assertRaises(WisDocURLRejected):
            self.parse(flow_routes("正文", markdown_url=md_url))
        self.requests.clear()
        self.parse(flow_routes("正文", markdown_url=md_url), env_dirs=[project])
        self.assertIn(md_url, self.urls())
        self.assertTrue(all(dict(r.header_items())["X-canary"] == "blue" for r in self.requests))

    def test_markdown_url_must_be_http_on_allowed_host(self) -> None:
        for md_url in ("file:///etc/passwd", "http://evil.test/x.md", "ftp://gw.example.test/x.md", "//evil.test/x.md",
                       "data:text/plain,hi"):
            self.requests.clear()
            with self.assertRaises(WisDocURLRejected, msg=md_url):
                self.parse(flow_routes("正文", markdown_url=md_url))
            self.assertEqual(len(self.requests), 2, md_url)
        self.assertFalse(self.out.exists())

    def test_markdown_on_sibling_host_is_allowed(self) -> None:
        md_url = "https://cdn.example.test/out/j1.md"
        self.parse(flow_routes("正文", markdown_url=md_url))
        self.assertEqual(self.urls()[-1], md_url)
        self.assertEqual((self.out / "wisdoc.md").read_text(encoding="utf-8"), "正文")

    def test_rejected_or_failed_images_are_replaced(self) -> None:
        markdown = ("![a](img/a.png)\n![b](//other-host.test/x.png)\n![c](http://100.100.100.200/latest/meta-data/)\n"
                    '<img src="file:///etc/passwd">\n![d](data:image/png;base64,AAAA)\n![e](img/missing.png)\n'
                    "![f](https://cdn.example.test/f.png)\n")
        routes = flow_routes(markdown, extra={
            ("GET", f"{BASE}/files/img/a.png"): FakeResponse(b"a", "image/png"),
            ("GET", f"{BASE}/files/img/missing.png"): urllib.error.HTTPError(f"{BASE}/files/img/missing.png", 404, "NF", {}, io.BytesIO(b"")),
            ("GET", "https://cdn.example.test/f.png"): FakeResponse(b"f", "image/png"),
        })
        self.parse(routes)
        text = (self.out / "wisdoc.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(ASSET_PLACEHOLDER), 5)
        self.assertIn("![a](assets/001_a.png)", text)
        self.assertIn("![f](assets/002_f.png)", text)
        for leaked in ("other-host", "100.100.100.200", "file:", "data:", "missing.png"):
            self.assertNotIn(leaked, text)
        self.assertFalse(any(h in u for u in self.urls() for h in ("other-host", "100.100.100.200")))

    def test_invalid_job_id_is_rejected_before_any_file_is_written(self) -> None:
        before = sorted(self.base.rglob("*"))
        for job_id in (str(self.base / "escaped" / "planted"), "../escape", "..", ".", "a/b", "x" * 129, "", None, True):
            self.requests.clear()
            with self.assertRaises(WisDocError, msg=repr(job_id)):
                self.parse(flow_routes("正文", job_id=job_id), markdown_name=None, assets_dirname=None)
            self.assertEqual(len(self.requests), 1)
        self.assertEqual(sorted(self.base.rglob("*")), before)

    def test_valid_job_id_names_cli_outputs(self) -> None:
        payload = self.parse(flow_routes("正文", job_id="a.b-C_1"), markdown_name=None, assets_dirname=None)
        self.assertEqual(Path(payload["markdown_path"]), (self.out / "a.b-C_1.md").resolve())

    def test_oversize_responses(self) -> None:
        self._patch(wisdoc_client, "MAX_RESPONSE_BYTES", 200)
        with self.assertRaises(WisDocError) as caught:
            self.parse(flow_routes("长" * 80))
        self.assertIn("上限", str(caught.exception))
        self.assertEqual(self.urls()[-1], f"{BASE}/files/j1.md")
        self.requests.clear()
        routes = flow_routes("![a](img/a.png)\n![b](img/b.png)\n", extra={
            ("GET", f"{BASE}/files/img/a.png"): FakeResponse(b"x" * 201, "image/png"),
            ("GET", f"{BASE}/files/img/b.png"): FakeResponse(b"b", "image/png")})
        self.parse(routes)
        text = (self.out / "wisdoc.md").read_text(encoding="utf-8")
        self.assertEqual(text, f"{ASSET_PLACEHOLDER}\n![b](assets/001_b.png)\n")

    def test_asset_count_cap(self) -> None:
        self._patch(wisdoc_client, "MAX_ASSETS", 1)
        routes = flow_routes("![a](img/a.png)\n![b](img/b.png)\n", extra={
            ("GET", f"{BASE}/files/img/a.png"): FakeResponse(b"a", "image/png"),
            ("GET", f"{BASE}/files/img/b.png"): FakeResponse(b"b", "image/png")})
        self.parse(routes)
        self.assertEqual((self.out / "wisdoc.md").read_text(encoding="utf-8"), f"![a](assets/001_a.png)\n{ASSET_PLACEHOLDER}\n")
        self.assertNotIn(f"{BASE}/files/img/b.png", self.urls())

    def test_total_deadline_stops_image_downloads(self) -> None:
        clock = [0.0]
        self._patch(wisdoc_client, "_now", lambda: clock[0])

        def advance(request: Any) -> None:
            if request.full_url.endswith("a.png"):
                clock[0] += 100

        routes = flow_routes("![a](img/a.png)\n![b](img/b.png)\n", extra={
            ("GET", f"{BASE}/files/img/a.png"): FakeResponse(b"a", "image/png"),
            ("GET", f"{BASE}/files/img/b.png"): FakeResponse(b"b", "image/png")})
        self.parse(routes, on_open=advance, total_timeout_s=50)
        self.assertEqual((self.out / "wisdoc.md").read_text(encoding="utf-8"), f"![a](assets/001_a.png)\n{ASSET_PLACEHOLDER}\n")

    def test_metadata_of_wrong_type_raises_wisdoc_error(self) -> None:
        for metadata in ("oops", ["x"], {"markdown_url": ["x"]}, {"markdown_url": ""}):
            with self.assertRaises(WisDocError, msg=repr(metadata)):
                self.parse(flow_routes("正文", metadata=metadata))

    def test_http_error_text_is_redacted_and_capped(self) -> None:
        body = CountingBody(f'{{"error": {{"message": "upstream {SECRET}/x failed"}}}}'.encode() + b" " * 100_000)
        error = urllib.error.HTTPError(f"{SECRET}/api/v2/documents", 502, "Bad Gateway", {}, body)
        routes = {("POST", f"{SECRET}/api/v2/documents"): error}
        with self.assertRaises(wisdoc_client.WisDocHTTPError) as caught:
            self.parse(routes, base_url=SECRET)
        self.assertEqual(caught.exception.status, 502)
        self.assertNotIn("wisdoc-secret", str(caught.exception))
        self.assertLessEqual(body.consumed, wisdoc_client.MAX_ERROR_BYTES)
        self.assertTrue(body.closed)

    def test_cli_has_no_serve_mode(self) -> None:
        self.assertFalse(hasattr(wisdoc_client, "_run_mcp_server"))
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            wisdoc_client._parse_cli(["serve"])


class _LocalWisDoc(http.server.BaseHTTPRequestHandler):
    """127.0.0.1 上的假 WisDoc：轮询地址先重定向到 server.redirect_target。"""

    def _send(self, status: int, body: bytes, content_type: str = "application/json", location: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if location:
            self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._send(200, b'{"job_id": "j1"}')

    def do_GET(self) -> None:  # noqa: N802
        status = {"task_status": {"ready": True, "successful": True}, "metadata": {"markdown_url": "/files/j1.md"}}
        pages = {
            "/status/j1": (200, json.dumps(status).encode(), "application/json"),
            "/files/j1.md": (200, "正文\n![a](/img/a.png)\n![m](http://100.100.100.200/latest/meta-data/)\n".encode(), "text/markdown"),
            "/img/a.png": (200, b"png", "image/png"),
        }
        if self.path == "/api/v2/documents/j1":
            self._send(302, b"", location=self.server.redirect_target)  # type: ignore[attr-defined]
        elif self.path in pages:
            self._send(*pages[self.path])
        else:
            self._send(404, b"{}")

    def log_message(self, *args: Any) -> None:
        return None


class LocalServerTest(IsolatedEnv):
    def setUp(self) -> None:
        super().setUp()
        for key in PROXY_KEYS:
            os.environ.pop(key, None)
        os.environ["no_proxy"] = os.environ["NO_PROXY"] = "*"
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _LocalWisDoc)
        self.addCleanup(self.server.server_close)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.shutdown)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.pdf = self.base / "a.pdf"
        self.pdf.write_bytes(b"%PDF fake")

    def parse(self) -> dict:
        return wisdoc_client.parse_pdf_to_markdown(pdf_path=str(self.pdf), output_dir=self.base / "out", base_url=self.base_url,
                                                   cwd=self.cwd, poll_timeout_s=5, poll_interval_s=0,
                                                   markdown_name="wisdoc.md", assets_dirname="assets")

    def test_redirect_to_external_host_is_rejected(self) -> None:
        self.server.redirect_target = "http://evil.test/steal"  # type: ignore[attr-defined]
        with self.assertRaises(WisDocURLRejected):
            self.parse()

    def test_same_host_redirect_and_real_opener(self) -> None:
        self.server.redirect_target = "/status/j1"  # type: ignore[attr-defined]
        self.parse()
        text = (self.base / "out" / "wisdoc.md").read_text(encoding="utf-8")
        self.assertEqual(text, f"正文\n![a](assets/001_a.png)\n{ASSET_PLACEHOLDER}\n")


class MaterialsWithClientTest(IsolatedEnv):
    """materials.py 调用真实客户端（opener 被替换）：返回值不合规时只记警告，不中断运行。"""

    def setUp(self) -> None:
        super().setUp()
        self.root = self.base / "proj"
        self.root.mkdir()
        self.task = self.base / ".bensz-api" / "task-20261010-1200-client"
        self.pdf = self.base / "a.pdf"
        self.pdf.write_bytes(b"%PDF fake")
        os.environ["WISDOCRS_BASE_URL"] = BASE
        self._patch(materials, "local_pdf_text", lambda path: LocalText(LOCAL_TEXT, "PyMuPDF", ()))

    def run_with(self, routes: dict) -> dict:
        with mock.patch.object(wisdoc_client, "_make_opener", lambda conn: FakeOpener(routes, [])):
            [(entry, _)] = materials.run(self.root, self.task, [self.pdf], cwd=self.cwd, no_cache=True,
                                         settings=materials.Settings(poll_timeout_s=5, poll_interval_s=0, total_timeout_s=30))
        return entry

    def test_bad_metadata_and_rejected_url_become_warnings(self) -> None:
        entry = self.run_with(flow_routes("正文", metadata="oops"))
        self.assertEqual((entry["parser"], entry["primary"]), ("local", "01-a/local.txt"))
        self.assertIn("WisDoc 解析失败（返回内容异常），正文以 local.txt 为准", entry["warnings"])
        entry = self.run_with(flow_routes("正文", markdown_url="file:///etc/passwd"))
        self.assertIn("WisDoc 解析失败（服务器返回的地址不在允许范围内），正文以 local.txt 为准", entry["warnings"])
        self.assertFalse((self.task / "shared" / "materials" / "01-a" / "wisdoc.md").exists())


if __name__ == "__main__":
    unittest.main()
