#!/usr/bin/env python3
"""用 WisImage 生成研究框架图与各研究的设计图。

render：读 T 下的提示词文件，POST 到 WISMODEL_IMAGE_URL，把返回的图片写成 P/figures/nsfc-proposal/<名称>.png；
提示词副本写 T/nsfc-proposal/output/figures/<名称>.prompt.md；每次运行在同目录的 index.json 追加一条记录。
凭据与地址（WISMODEL_IMAGE_URL、WISMODEL_API_KEY、DEPLOY_REGION）的查找顺序：已有环境变量 → 当前目录及各级父目录的
.env → project_root 及各级父目录的 .env → skill 目录。输出、日志与索引不含地址、token 和模型名。
退出码：0 已生成；1 生成失败（不写 PNG）；2 参数或路径错误；3 未配置或 figures.enabled 为 false（不发请求）。
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

import envfile
from proposal_common import ProposalError, load_config, project_path, resolve_project_root

SKILL_DIR = Path(__file__).resolve().parents[1]
SCHEMA = "nsfc-proposal.figures.v1"
USER_AGENT = "nsfc-proposal-figures/0.1"
CHANNEL = "qiewenclaw"
URL_KEY, TOKEN_KEY, REGION_KEY = "WISMODEL_IMAGE_URL", "WISMODEL_API_KEY", "DEPLOY_REGION"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
ASPECT_RATIOS = ("1:1", "16:9", "9:16", "21:9")
IMAGE_SIZES = ("1K", "2K", "4K")
FIGURES_DIR = "figures/nsfc-proposal"
OUTPUT_DIR = "nsfc-proposal/output/figures"
MAX_TOKENS = 16000
RETRY_DELAY_S = 3
DEFAULT_TIMEOUT_S = 300
DEFAULT_MAX_IMAGE_BYTES = 31457280
REFUSAL_CHARS = 200
DATA_URL_RE = re.compile(r"^data:image/[A-Za-z0-9.+-]+;base64,(.*)$", re.S)
URL_IN_TEXT_RE = re.compile(r"(?i)\b(?:[a-z][a-z0-9+.-]*://|www\.)\S+")
CATEGORIES = {
    "http_4xx": "请求被拒绝（HTTP 4xx）",
    "credit": "额度不足",
    "http_5xx": "服务端错误（HTTP 5xx），已重试 1 次",
    "network": "网络错误，已重试 1 次",
    "no_image": "没有返回图片",
    "bad_image": "返回的不是 PNG、JPEG 或 WebP 图片",
    "too_large": "图片超过 figures.max_image_bytes",
}

logger = logging.getLogger(__name__)


class FigureError(RuntimeError):
    """出图失败；category 取 CATEGORIES 的键，text 是去掉网址、截断后的拒绝文字。"""

    def __init__(self, category: str, *, status: int | None = None, text: str = "") -> None:
        super().__init__(category)
        self.category = category
        self.status = status
        self.text = text


class FiguresNotConfigured(RuntimeError):
    """缺凭据或地址写法不对；信息只含键名，不含值。"""


@dataclass(frozen=True, repr=False)
class ImageSettings:
    url: str
    api_key: str
    region: str

    def __repr__(self) -> str:
        return "ImageSettings(<已隐藏>)"

    def redact(self, text: str) -> str:
        """去掉文字中的地址、主机名与 token。"""
        host = urllib.parse.urlparse(self.url).hostname or ""
        for secret in (self.url, host, self.api_key):
            if secret:
                text = text.replace(secret, "<已隐藏>")
        return text


@dataclass(frozen=True)
class Job:
    root: Path
    task: Path
    name: str
    prompt: str
    png: Path
    prompt_copy: Path
    index: Path
    aspect: str
    size: str
    enabled: bool
    model: str
    timeout: float
    max_bytes: int


def load_settings(project_root: Path | str, *, cwd: Path | str | None = None,
                  skill_dir: Path | str | None = None) -> ImageSettings:
    """查找并校验三个键；缺失或写法不对时抛出 FiguresNotConfigured（信息不含值）。cwd 与 skill_dir 可注入。"""
    skill = skill_dir if skill_dir is not None else SKILL_DIR
    values = {key: envfile.resolve_setting(key, [project_root], cwd, skill_dir=skill)
              for key in (URL_KEY, TOKEN_KEY, REGION_KEY)}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise FiguresNotConfigured(f"缺 {'、'.join(missing)}")
    url = values[URL_KEY]
    if re.search(r"[\s#]", url):
        raise FiguresNotConfigured(f"{URL_KEY} 含空白或 #：检查 .env 中该行是否带了行尾注释")
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
    except ValueError:
        parsed, host = None, None
    if parsed is None or parsed.scheme not in ("http", "https") or not host:
        raise FiguresNotConfigured(f"{URL_KEY} 不是 http(s) 地址")
    for key in (TOKEN_KEY, REGION_KEY):
        if re.search(r"\s", values[key]):
            raise FiguresNotConfigured(f"{key} 含空白")
    return ImageSettings(url=url, api_key=values[TOKEN_KEY], region=values[REGION_KEY])


def build_payload(prompt: str, model: str, aspect: str, size: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "max_tokens": MAX_TOKENS,
        "image_config": {"aspect_ratio": aspect, "image_size": size},
    }


def call_gateway(settings: ImageSettings, payload: dict, *, post: Callable[..., Any] | None = None,
                 sleep: Callable[[float], Any] | None = None, timeout: float = DEFAULT_TIMEOUT_S) -> dict:
    """POST 一次；5xx 与网络错误等 3 秒重试 1 次，4xx 立即失败（402 记 credit）。post、sleep 在调用时解析，可注入。"""
    send = post or requests.post
    wait = sleep or time.sleep
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
        "X-Channel": CHANNEL,
        "x-req-location": settings.region,
        "Accept-Encoding": "identity",
        "User-Agent": USER_AGENT,
    }
    for attempt in (1, 2):
        try:
            response = send(settings.url, headers=headers, json=payload, timeout=timeout,
                            proxies={"http": None, "https": None})
        except requests.RequestException as exc:
            logger.warning("WisImage 网络错误（%s，第 %d 次）", type(exc).__name__, attempt)
            if attempt == 1:
                wait(RETRY_DELAY_S)
                continue
            raise FigureError("network") from None
        status = int(response.status_code)
        if 200 <= status < 300:
            try:
                data = response.json()
            except ValueError:
                raise FigureError("no_image", status=status) from None
            if not isinstance(data, dict):
                raise FigureError("no_image", status=status)
            return data
        logger.warning("WisImage 返回 HTTP %d（第 %d 次）", status, attempt)
        if status >= 500:
            if attempt == 1:
                wait(RETRY_DELAY_S)
                continue
            raise FigureError("http_5xx", status=status)
        raise FigureError("credit" if status == 402 else "http_4xx", status=status)
    raise FigureError("network")


def image_format(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _refusal_text(message: Any) -> str:
    """模型的文字回复：去掉网址，压缩空白，取前 REFUSAL_CHARS 字。"""
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = " ".join(str(p.get("text") or "") for p in content if isinstance(p, dict))
    text = " ".join(URL_IN_TEXT_RE.sub("", str(content or "")).split())
    return text[:REFUSAL_CHARS]


def extract_image(result: Mapping[str, Any], max_bytes: int) -> bytes:
    """取 choices[0].message.images[0].image_url.url 中的 data URL 并解码；校验大小与魔数。"""
    choices = result.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    images = message.get("images") if isinstance(message, dict) else None
    image = images[0] if isinstance(images, list) and images else None
    image_url = image.get("image_url") if isinstance(image, dict) else None
    url = image_url.get("url") if isinstance(image_url, dict) else None
    if not isinstance(url, str) or not url.strip():
        raise FigureError("no_image", text=_refusal_text(message))
    match = DATA_URL_RE.match(url.strip())
    if not match:
        raise FigureError("bad_image")
    encoded = re.sub(r"\s+", "", match.group(1))
    if len(encoded) > (max_bytes + 2) // 3 * 4 + 4:
        raise FigureError("too_large")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise FigureError("bad_image") from None
    if len(data) > max_bytes:
        raise FigureError("too_large")
    if image_format(data) is None:
        raise FigureError("bad_image")
    return data


def _inside(base: Path, path: Path) -> bool:
    return base == path or base in path.parents


def _prepare(project_root: Path | str, task_root: Path | str, prompt_file: Path | str, name: str, aspect: str | None,
             size: str | None, force: bool, config: Mapping[str, Any] | None) -> Job:
    """校验参数与路径；任何一项不合格都抛出 ProposalError（退出码 2），此时还没有读凭据。"""
    task = Path(task_root).expanduser().resolve()
    if not task.name.startswith("task-") or task.parent.name != ".bensz-api":
        raise ProposalError(f"--task-root 必须指向 .bensz-api/task-*/ 目录：{task}")
    if not NAME_RE.match(name or ""):
        raise ProposalError(f"--name 须匹配 {NAME_RE.pattern}：{name!r}")
    root = resolve_project_root(project_root)
    source = Path(prompt_file).expanduser().resolve()
    if not _inside(task, source) or not source.is_file():
        raise ProposalError(f"--prompt-file 必须是任务目录下的文件：{prompt_file}")
    try:
        prompt = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProposalError(f"--prompt-file 读不了（{type(exc).__name__}）：{prompt_file}") from exc
    if not prompt.strip():
        raise ProposalError(f"--prompt-file 是空文件：{prompt_file}")
    section = (config if config is not None else load_config()).get("figures") or {}
    model = str(section.get("model") or "").strip()
    if not model:
        raise ProposalError("config.yaml 缺 figures.model")
    ratio_key = "framework_aspect_ratio" if "framework" in name else "design_aspect_ratio"
    aspect = aspect or str(section.get(ratio_key) or ("1:1" if ratio_key == "framework_aspect_ratio" else "16:9"))
    size = size or str(section.get("image_size") or "2K")
    if aspect not in ASPECT_RATIOS or size not in IMAGE_SIZES:
        raise ProposalError(f"画幅须为 {'|'.join(ASPECT_RATIOS)}，尺寸须为 {'|'.join(IMAGE_SIZES)}")
    png = project_path(root, f"{FIGURES_DIR}/{name}.png")
    if png.exists() and not force:
        raise ProposalError(f"{FIGURES_DIR}/{name}.png 已存在：重画用新名称（如 {name}-v2），或加 --force 覆盖")
    out_dir = (task / OUTPUT_DIR).resolve()
    if not _inside(task, out_dir):
        raise ProposalError(f"{OUTPUT_DIR} 越出任务目录")
    return Job(root=root, task=task, name=name, prompt=prompt, png=png, prompt_copy=out_dir / f"{name}.prompt.md",
               index=out_dir / "index.json", aspect=aspect, size=size, enabled=bool(section.get("enabled", True)),
               model=model, timeout=float(section.get("timeout_s") or DEFAULT_TIMEOUT_S),
               max_bytes=int(section.get("max_image_bytes") or DEFAULT_MAX_IMAGE_BYTES))


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _append_index(job: Job, status: str, **fields: Any) -> None:
    """index.json 追加一条记录；文件缺失或格式不符时重建。路径相对 P（png）或 T（prompt）。"""
    entries: list = []
    if job.index.exists():
        try:
            data = json.loads(job.index.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("schema") == SCHEMA and isinstance(data.get("figures"), list):
                entries = data["figures"]
            else:
                logger.warning("index.json 格式不符，重建索引")
        except (OSError, ValueError):
            logger.warning("index.json 无法读取，重建索引")
    entry = {"name": job.name, "png": f"{FIGURES_DIR}/{job.name}.png" if status == "ok" else None,
             "prompt": f"{OUTPUT_DIR}/{job.name}.prompt.md", "aspect_ratio": job.aspect, "image_size": job.size,
             "status": status, **fields, "created": datetime.now().astimezone().isoformat(timespec="seconds")}
    text = json.dumps({"schema": SCHEMA, "figures": entries + [entry]}, ensure_ascii=False, indent=2) + "\n"
    _write_atomic(job.index, text.encode("utf-8"))


def render(project_root: Path | str, task_root: Path | str, prompt_file: Path | str, name: str,
           aspect: str | None = None, size: str | None = None, force: bool = False, *,
           post: Callable[..., Any] | None = None, sleep: Callable[[float], Any] | None = None,
           cwd: Path | str | None = None, skill_dir: Path | str | None = None,
           config: Mapping[str, Any] | None = None) -> int:
    """生成一张图，返回退出码。aspect 不给时：名称含 framework 取 framework_aspect_ratio，否则取 design_aspect_ratio。"""
    try:
        job = _prepare(project_root, task_root, prompt_file, name, aspect, size, force, config)
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    _write_atomic(job.prompt_copy, job.prompt.encode("utf-8"))
    if not job.enabled:
        _append_index(job, "not_configured", reason="figures.enabled 为 false")
        print("figures.enabled 为 false：不出图，正文保留占位。", file=sys.stderr)
        return 3
    try:
        settings = load_settings(job.root, cwd=cwd, skill_dir=skill_dir)
    except FiguresNotConfigured as exc:
        _append_index(job, "not_configured", reason=str(exc))
        print(f"WisImage 未配置（{exc}；环境变量或 .env）：不出图，正文保留占位。", file=sys.stderr)
        return 3
    try:
        result = call_gateway(settings, build_payload(job.prompt, job.model, job.aspect, job.size), post=post,
                              sleep=sleep, timeout=job.timeout)
        data = extract_image(result, job.max_bytes)
    except FigureError as exc:
        extra = {"http_status": exc.status} if exc.status else {}
        _append_index(job, "failed", category=exc.category, **extra)
        print(f"WisImage 出图失败：{exc.category}（{CATEGORIES.get(exc.category, '')}）；未写 PNG。", file=sys.stderr)
        if exc.text:
            print(f"返回的文字：{settings.redact(exc.text)}", file=sys.stderr)
        return 1
    _write_atomic(job.png, data)
    fmt = image_format(data)
    logger.info("WisImage 返回 %d 字节（%s）", len(data), fmt)
    _append_index(job, "ok", sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), format=fmt)
    if fmt != "png":
        print(f"⚠️ 返回的是 {fmt} 数据，已按 .png 文件名保存；编译报错时改用 PNG 重画。", file=sys.stderr)
    print(f"已生成 {FIGURES_DIR}/{job.name}.png")
    return 0


def main(argv: list[str] | None = None, *, post: Callable[..., Any] | None = None,
         sleep: Callable[[float], Any] | None = None, cwd: Path | str | None = None,
         skill_dir: Path | str | None = None) -> int:
    parser = argparse.ArgumentParser(prog="figures.py", description="用 WisImage 生成研究框架图与设计图")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("render", help="生成一张图，写入 P/figures/nsfc-proposal/<名称>.png")
    cmd.add_argument("--project-root", required=True)
    cmd.add_argument("--task-root", required=True, help="本任务的 .bensz-api/task-*/ 目录")
    cmd.add_argument("--prompt-file", required=True, help="任务目录下的提示词文件")
    cmd.add_argument("--name", required=True, help="小写字母、数字、- 或 _，最长 48 字符，如 fig1-framework")
    cmd.add_argument("--aspect-ratio", choices=ASPECT_RATIOS,
                     help="不给时：名称含 framework 取 figures.framework_aspect_ratio，否则取 figures.design_aspect_ratio")
    cmd.add_argument("--image-size", choices=IMAGE_SIZES, help="不给时取 figures.image_size")
    cmd.add_argument("--force", action="store_true", help="覆盖已存在的同名 PNG")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    return render(args.project_root, args.task_root, args.prompt_file, args.name, args.aspect_ratio, args.image_size,
                  args.force, post=post, sleep=sleep, cwd=cwd, skill_dir=skill_dir)


if __name__ == "__main__":
    raise SystemExit(main())
