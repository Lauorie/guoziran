# tests/nsfc-proposal/test_np_figures.py
"""figures.py：WisImage 出图。全部用桩替换 requests.post，不联网。

隔离：清掉三个环境变量；cwd、project_root、skill 目录都放在临时目录；requests.post 与 Session.request
换成一调用就让测试失败的桩，只有用例显式传入的 post 才会被调用。
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import figures  # noqa: E402

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
ENV_KEYS = ("WISMODEL_IMAGE_URL", "WISMODEL_API_KEY", "DEPLOY_REGION")
URL = "https://gw.example.test/img"
TOKEN = "sk-test-0001"
REGION = "cn-test"
SENTINEL_TOKEN = "sk-SENTINEL-123"
SENTINEL_URL = "https://gw.sentinel.test/img"
SENTINEL_HOST = "gw.sentinel.test"


class FakeResponse:
    def __init__(self, status: int, payload: Any = None, text: str = "") -> None:
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else text

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakePost:
    """依次返回给定的响应；元素是异常时抛出。"""

    def __init__(self, *responses: Any, tick: Any = None) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []
        self.tick = tick

    def __call__(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        if self.tick:
            self.tick()
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 8


def image_result(data: bytes = PNG_1X1, mime: str = "image/png") -> dict:
    url = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    return {"choices": [{"message": {"role": "assistant", "content": "",
                                     "images": [{"type": "image_url", "image_url": {"url": url}}]}}]}


def refusal_result(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text, "images": []}}]}


class FiguresBase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.cwd = self.base / "cwd"
        self.skill = self.base / "skill"
        self.project = self.base / "group" / "proj"
        self.task = self.base / "work" / ".bensz-api" / "task-20261010-1200-figs"
        self.out = self.task / "nsfc-proposal" / "output" / "figures"
        for path in (self.cwd, self.skill, self.project, self.out):
            path.mkdir(parents=True)
        self.prompt = self.out / "fig1-framework.prompt.txt"
        self.prompt.write_text("国家自然科学基金申请书正文中的科研示意图，白底、扁平矢量风格。\nZONE 1：……\n", encoding="utf-8")
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        old_cwd = os.getcwd()
        os.chdir(self.cwd)
        self.addCleanup(os.chdir, old_cwd)
        self.unexpected: list[Any] = []
        self.addCleanup(lambda: self.assertEqual(self.unexpected, [], "测试发出了未替换的请求"))

        def forbidden(*args: Any, **kwargs: Any) -> Any:
            self.unexpected.append(args[:1])
            raise AssertionError("测试不得发出真实请求")

        for target, name in ((requests, "post"), (requests.Session, "request")):
            patcher = mock.patch.object(target, name, forbidden)
            patcher.start()
            self.addCleanup(patcher.stop)
        skill_patch = mock.patch.object(figures, "SKILL_DIR", self.skill)
        skill_patch.start()
        self.addCleanup(skill_patch.stop)
        self.sleeps: list[float] = []

    def configure(self, url: str = URL, token: str = TOKEN, region: str = REGION) -> None:
        os.environ.update({"WISMODEL_IMAGE_URL": url, "WISMODEL_API_KEY": token, "DEPLOY_REGION": region})

    def render(self, name: str = "fig1-framework", *, prompt: Path | None = None, **kwargs: Any) -> int:
        kwargs.setdefault("sleep", self.sleeps.append)
        return figures.render(self.project, self.task, prompt or self.prompt, name, cwd=self.cwd, skill_dir=self.skill,
                              **kwargs)

    def index(self) -> list[dict]:
        data = json.loads((self.out / "index.json").read_text(encoding="utf-8"))
        return data["figures"]

    def png(self, name: str = "fig1-framework") -> Path:
        return self.project / "figures" / "nsfc-proposal" / f"{name}.png"


class RenderSuccessTest(FiguresBase):
    def test_success_writes_png_prompt_copy_and_index(self) -> None:
        self.configure()
        post = FakePost(FakeResponse(200, image_result()))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = self.render(post=post)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue().strip(), "已生成 figures/nsfc-proposal/fig1-framework.png")
        self.assertTrue(self.png().read_bytes().startswith(b"\x89PNG"))
        copy = self.out / "fig1-framework.prompt.md"
        self.assertEqual(copy.read_text(encoding="utf-8"), self.prompt.read_text(encoding="utf-8"))
        [entry] = self.index()
        self.assertEqual(entry["name"], "fig1-framework")
        self.assertEqual(entry["png"], "figures/nsfc-proposal/fig1-framework.png")
        self.assertEqual(entry["prompt"], "nsfc-proposal/output/figures/fig1-framework.prompt.md")
        self.assertEqual((entry["aspect_ratio"], entry["image_size"]), ("1:1", "2K"))
        self.assertEqual(entry["sha256"], hashlib.sha256(PNG_1X1).hexdigest())
        self.assertEqual((entry["status"], entry["bytes"]), ("ok", len(PNG_1X1)))
        self.assertTrue(entry["created"])
        [(url, kwargs)] = post.calls
        self.assertEqual(url, URL)
        body = kwargs["json"]
        self.assertEqual(body["image_config"], {"aspect_ratio": "1:1", "image_size": "2K"})
        self.assertEqual(body["model"], "google/gemini-3.1-flash-image")
        self.assertEqual(body["messages"], [{"role": "user", "content": self.prompt.read_text(encoding="utf-8")}])
        self.assertEqual((body["modalities"], body["max_tokens"]), (["image", "text"], 16000))
        headers = kwargs["headers"]
        self.assertEqual(headers["X-Channel"], "qiewenclaw")
        self.assertEqual(headers["User-Agent"], "nsfc-proposal-figures/0.1")
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(headers["x-req-location"], REGION)
        self.assertEqual((headers["Content-Type"], headers["Accept-Encoding"]), ("application/json", "identity"))
        self.assertFalse(any("@" in v for v in headers.values()))
        self.assertEqual(kwargs["proxies"], {"http": None, "https": None})
        self.assertEqual(kwargs["timeout"], 300)

    def test_design_figure_defaults_to_design_aspect_ratio(self) -> None:
        self.configure()
        post = FakePost(FakeResponse(200, image_result()))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.render("fig2-study1", post=post), 0)
        self.assertEqual(post.calls[0][1]["json"]["image_config"], {"aspect_ratio": "16:9", "image_size": "2K"})
        post = FakePost(FakeResponse(200, image_result()))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.render("fig3-study2", aspect="21:9", size="4K", post=post), 0)
        self.assertEqual(post.calls[0][1]["json"]["image_config"], {"aspect_ratio": "21:9", "image_size": "4K"})

    def test_existing_target_needs_force(self) -> None:
        self.configure()
        self.png().parent.mkdir(parents=True)
        self.png().write_bytes(b"old")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.render(), 2)
        self.assertEqual(self.png().read_bytes(), b"old")
        post = FakePost(FakeResponse(200, image_result()))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.render(force=True, post=post), 0)
        self.assertEqual(self.png().read_bytes(), PNG_1X1)

    def test_existing_jpg_also_needs_force_and_is_replaced(self) -> None:
        self.configure()
        jpg = self.png().with_suffix(".jpg")
        jpg.parent.mkdir(parents=True)
        jpg.write_bytes(JPEG)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.render(), 2)
        post = FakePost(FakeResponse(200, image_result()))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.render(force=True, post=post), 0)
        self.assertEqual((self.png().read_bytes(), jpg.exists()), (PNG_1X1, False))

    def test_jpeg_is_saved_as_jpg(self) -> None:
        self.configure()
        post = FakePost(FakeResponse(200, image_result(JPEG, "image/jpeg")))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(self.render(post=post), 0)
        self.assertEqual(stdout.getvalue().strip(), "已生成 figures/nsfc-proposal/fig1-framework.jpg")
        self.assertEqual(self.png().with_suffix(".jpg").read_bytes(), JPEG)
        self.assertFalse(self.png().exists())
        entry = self.index()[-1]
        self.assertEqual((entry["png"], entry["format"]), ("figures/nsfc-proposal/fig1-framework.jpg", "jpeg"))


class NotConfiguredTest(FiguresBase):
    def assert_not_configured(self) -> None:
        post = FakePost()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = self.render(post=post)
        self.assertEqual(code, 3)
        self.assertEqual(post.calls, [])
        self.assertEqual(self.index()[-1]["status"], "not_configured")
        self.assertFalse(self.png().exists())

    def test_missing_settings_send_nothing(self) -> None:
        self.assert_not_configured()
        os.environ.update({"WISMODEL_IMAGE_URL": URL, "WISMODEL_API_KEY": TOKEN})
        self.assert_not_configured()
        self.assertEqual(len(self.index()), 2)

    def test_bad_url_is_not_configured(self) -> None:
        for url in ("gw.example.test/img", "ftp://gw.example.test/img", f"{URL}#x", f"{URL} x"):
            self.configure(url=url)
            self.assert_not_configured()

    def test_non_ascii_token_or_region_is_not_configured(self) -> None:
        for token, region in (("sk-密钥-1", REGION), (TOKEN, "华东")):
            self.configure(token=token, region=region)
            stderr = io.StringIO()
            post = FakePost()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(self.render(post=post), 3)
            self.assertEqual(post.calls, [])
            self.assertNotIn("密钥", stderr.getvalue() + json.dumps(self.index(), ensure_ascii=False))
            self.assertNotIn("华东", stderr.getvalue() + json.dumps(self.index(), ensure_ascii=False))

    def test_disabled_in_config(self) -> None:
        self.configure()
        config = {"figures": {"enabled": False, "model": "m"}}
        post = FakePost()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.render(post=post, config=config), 3)
        self.assertEqual(post.calls, [])
        self.assertEqual(self.index()[-1]["status"], "not_configured")


class DotenvTest(FiguresBase):
    def write_env(self, folder: Path, url: str) -> None:
        (folder / ".env").write_text(
            f"OTHER=x\nWISMODEL_IMAGE_URL={url}\nWISMODEL_API_KEY={TOKEN}  # 测试 key\nDEPLOY_REGION={REGION}\n",
            encoding="utf-8")

    def test_inline_comment_is_cut(self) -> None:
        self.write_env(self.cwd, f"{URL}  # 注释")
        post = FakePost(FakeResponse(200, image_result()))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.render(post=post), 0)
        url, kwargs = post.calls[0]
        self.assertEqual(url, URL)
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {TOKEN}")

    def test_hash_without_space_is_not_configured(self) -> None:
        self.write_env(self.cwd, f"{URL}#x")
        post = FakePost()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.render(post=post), 3)
        self.assertEqual(post.calls, [])

    def test_lookup_order(self) -> None:
        self.write_env(self.base / "group", "https://project.example.test/img")
        settings = figures.load_settings(self.project, cwd=self.cwd, skill_dir=self.skill)
        self.assertEqual(settings.url, "https://project.example.test/img")
        self.write_env(self.cwd, "https://cwd.example.test/img")
        self.assertEqual(figures.load_settings(self.project, cwd=self.cwd, skill_dir=self.skill).url,
                         "https://cwd.example.test/img")
        os.environ["WISMODEL_IMAGE_URL"] = "https://environ.example.test/img"
        self.assertEqual(figures.load_settings(self.project, cwd=self.cwd, skill_dir=self.skill).url,
                         "https://environ.example.test/img")
        self.assertNotIn(TOKEN, repr(settings))


class GatewayFailureTest(FiguresBase):
    def failed(self, *responses: Any, tick: Any = None, **kwargs: Any) -> tuple[int, FakePost, dict, str]:
        self.configure()
        post = FakePost(*responses, tick=tick)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = self.render(post=post, **kwargs)
        return code, post, self.index()[-1], stderr.getvalue()

    def test_4xx_fails_fast(self) -> None:
        code, post, entry, _ = self.failed(FakeResponse(400, text="bad request"))
        self.assertEqual((code, len(post.calls), entry["status"], entry["category"]), (1, 1, "failed", "http_4xx"))
        self.assertEqual(self.sleeps, [])
        self.assertFalse(self.png().exists())
        code, post, entry, stderr = self.failed(FakeResponse(402, text="insufficient credits"))
        self.assertEqual((code, len(post.calls), entry["category"]), (1, 1, "credit"))
        self.assertIn("额度不足", stderr)

    def test_5xx_then_success(self) -> None:
        self.configure()
        post = FakePost(FakeResponse(502, text="bad gateway"), FakeResponse(200, image_result()))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.render(post=post), 0)
        self.assertEqual((len(post.calls), self.sleeps), (2, [3]))
        self.assertTrue(self.png().is_file())

    def test_5xx_twice_and_network_twice(self) -> None:
        code, post, entry, _ = self.failed(FakeResponse(503), FakeResponse(500))
        self.assertEqual((code, len(post.calls), entry["category"]), (1, 2, "http_5xx"))
        code, post, entry, _ = self.failed(requests.ConnectionError("refused"), requests.ConnectionError("refused"))
        self.assertEqual((code, len(post.calls), entry["category"]), (1, 2, "network"))
        code, post, entry, _ = self.failed(requests.Timeout("slow"), requests.Timeout("slow"))
        self.assertEqual((code, len(post.calls), entry["category"]), (1, 2, "timeout"))
        self.assertFalse(self.png().exists())

    def test_total_timeout_caps_each_request_and_skips_late_retry(self) -> None:
        config = {"figures": {"model": "m", "timeout_s": 300, "total_timeout_s": 560}}
        clock = FakeClock()

        def advance(seconds: float) -> Any:
            return lambda: setattr(clock, "now", clock.now + seconds)

        code, post, _, _ = self.failed(FakeResponse(502), FakeResponse(200, image_result()), config=config,
                                       clock=clock, tick=advance(400))
        self.assertEqual(code, 0)
        self.assertEqual([kw["timeout"] for _, kw in post.calls], [300, 160])
        clock.now = 0.0
        code, post, entry, _ = self.failed(FakeResponse(502), config=config, clock=clock, tick=advance(540), force=True)
        self.assertEqual((code, len(post.calls), entry["category"]), (1, 1, "timeout"))

    def test_200_without_image(self) -> None:
        code, post, entry, stderr = self.failed(
            FakeResponse(200, refusal_result("抱歉，我无法生成这张图片。参见 https://policy.example.test/rules 了解详情。")))
        self.assertEqual((code, len(post.calls), entry["category"]), (1, 1, "no_image"))
        self.assertFalse(self.png().exists())
        self.assertIn("抱歉，我无法生成这张图片", stderr)
        self.assertNotIn("policy.example.test", stderr)
        code, _, entry, _ = self.failed(FakeResponse(200, text="<html>not json</html>"))
        self.assertEqual((code, entry["category"]), (1, "no_image"))

    def test_bad_image_and_too_large(self) -> None:
        code, _, entry, _ = self.failed(FakeResponse(200, image_result(b"not an image at all", "image/png")))
        self.assertEqual((code, entry["category"]), (1, "bad_image"))
        for data in (WEBP, b"GIF89a" + b"\x00" * 20):
            code, _, entry, _ = self.failed(FakeResponse(200, image_result(data, "image/webp")))
            self.assertEqual((code, entry["category"], entry["png"]), (1, "unsupported_format", None))
        self.assertEqual(list((self.project / "figures" / "nsfc-proposal").glob("*")), [])
        code, _, entry, _ = self.failed(FakeResponse(200, image_result(b"\x89PNG" + b"\x00" * 100)),
                                        config={"figures": {"model": "m", "max_image_bytes": 50}})
        self.assertEqual((code, entry["category"]), (1, "too_large"))
        self.assertFalse(self.png().exists())
        with self.assertRaises(figures.FigureError) as caught:
            figures.extract_image(image_result(PNG_1X1), len(PNG_1X1) - 1)
        self.assertEqual(caught.exception.category, "too_large")
        broken = {"choices": [{"message": {"images": [{"image_url": {"url": "data:image/png;base64,@@@@"}}]}}]}
        with self.assertRaises(figures.FigureError) as caught:
            figures.extract_image(broken, 1024)
        self.assertEqual(caught.exception.category, "bad_image")


class ArgumentTest(FiguresBase):
    def test_bad_name_target_and_prompt_location(self) -> None:
        self.configure()
        with contextlib.redirect_stderr(io.StringIO()):
            for name in ("../x", "Fig1", "-fig", "a" * 49, "", "fig1\n"):
                self.assertEqual(self.render(name), 2, name)
            outside = self.base / "prompt.txt"
            outside.write_text("提示词", encoding="utf-8")
            self.assertEqual(self.render(prompt=outside), 2)
            self.assertEqual(self.render(prompt=self.out / "missing.txt"), 2)
            empty = self.out / "empty.txt"
            empty.write_text("  \n", encoding="utf-8")
            self.assertEqual(self.render(prompt=empty), 2)
            self.assertEqual(figures.render(self.project, self.base / "work", self.prompt, "fig1-framework",
                                            cwd=self.cwd, skill_dir=self.skill), 2)
        self.assertFalse((self.out / "index.json").exists())

    def test_cli_rejects_bad_choices(self) -> None:
        argv = ["render", "--project-root", str(self.project), "--task-root", str(self.task),
                "--prompt-file", str(self.prompt), "--name", "fig1-framework"]
        with contextlib.redirect_stderr(io.StringIO()):
            for extra in (["--aspect-ratio", "4:3"], ["--image-size", "8K"]):
                with self.assertRaises(SystemExit) as caught:
                    figures.main(argv + extra)
                self.assertEqual(caught.exception.code, 2)

    def test_main_quiets_urllib3(self) -> None:
        urllib3_logger = logging.getLogger("urllib3")
        self.addCleanup(urllib3_logger.setLevel, urllib3_logger.level)
        urllib3_logger.setLevel(logging.NOTSET)
        argv = ["render", "--project-root", str(self.project), "--task-root", str(self.task),
                "--prompt-file", str(self.prompt), "--name", "Bad"]
        with mock.patch.object(logging, "basicConfig"), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(figures.main(argv), 2)
        self.assertEqual(urllib3_logger.level, logging.ERROR)

    def test_cli_script_runs_standalone(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
        env["PYTHONPYCACHEPREFIX"] = str(ROOT / ".bensz-api" / "pycache")
        env["WISMODEL_IMAGE_URL"] = "not-a-url"
        proc = subprocess.run([sys.executable, str(SCRIPTS / "figures.py"), "render", "--project-root", str(self.project),
                               "--task-root", str(self.task), "--prompt-file", str(self.prompt), "--name", "Bad/Name"],
                              cwd=self.cwd, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2, proc.stderr)


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


class SecretTest(FiguresBase):
    def captured(self, post: FakePost) -> str:
        handler = _Collect()
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.render(post=post, force=True)
        finally:
            root.removeHandler(handler)
            root.setLevel(old_level)
        index = (self.out / "index.json").read_text(encoding="utf-8")
        return "\n".join([stdout.getvalue(), stderr.getvalue(), *handler.lines, index])

    def assert_clean(self, text: str) -> None:
        self.assertNotIn(SENTINEL_TOKEN, text)
        self.assertNotIn(SENTINEL_HOST, text.lower())

    def test_host_is_masked_regardless_of_case(self) -> None:
        self.configure(url="https://GW.Sentinel.test/img", token=SENTINEL_TOKEN)
        for host in ("GW.Sentinel.test", "gw.sentinel.test", "Gw.SENTINEL.Test"):
            text = self.captured(FakePost(FakeResponse(200, refusal_result(f"无法生成 {host} 拒绝"))))
            self.assert_clean(text)
            self.assertIn("无法生成", text)

    def test_sentinels_never_leak(self) -> None:
        self.configure(url=SENTINEL_URL, token=SENTINEL_TOKEN)
        echo = f"error at {SENTINEL_URL} with key {SENTINEL_TOKEN}"
        cases = [
            FakePost(FakeResponse(200, image_result())),
            FakePost(FakeResponse(500, text=echo), FakeResponse(503, text=echo)),
            FakePost(FakeResponse(401, text=echo)),
            FakePost(requests.ConnectionError(echo), requests.ConnectionError(echo)),
            FakePost(FakeResponse(200, refusal_result(f"无法生成。{echo} 主机 {SENTINEL_HOST} key {SENTINEL_TOKEN}"))),
        ]
        for post in cases:
            self.assert_clean(self.captured(post))
            self.assertTrue(post.calls)
        for prefix in ("x" * 190, "x" * 195, "x" * 199):
            for secret in (SENTINEL_TOKEN, SENTINEL_HOST, SENTINEL_HOST.upper()):
                text = self.captured(FakePost(FakeResponse(200, refusal_result(prefix + secret + " 之后的文字"))))
                self.assert_clean(text)
                self.assertNotIn("sk-SENT", text)
                self.assertNotIn("gw.sent", text.lower())
        os.environ["WISMODEL_IMAGE_URL"] = f"{SENTINEL_HOST}/img"
        post = FakePost()
        text = self.captured(post)
        self.assertEqual(post.calls, [])
        self.assert_clean(text)
        self.assertEqual(self.index()[-1]["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
