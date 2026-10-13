# nsfc-proposal 第四轮改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修掉 fresh-1 验证运行暴露的四个缺陷，并下调篇幅下限：参考文献的 HTML 实体与已写入条目的刷新路径、数字核对不认 percent、立项依据写作脚本的 `--out` 不建目录、第二次补摘要不能沿用前次结果；立项依据与研究内容的字数下限按实测稿件下调。

**Architecture:** 改动分在五个 skill。nsfc-proposal：`bib_resolve.py` 先解 HTML 实体再转义；新增 `bib_refresh.py`，按台账中的 DOI 重新取 CrossRef 元数据、用原 key 重写条目，并在引用台账追加 add 事件；`consistency_check.py` 读摘要时把 percent 写法换成 %。nsfc-justification-writer：`--out` 先建目录。research-literature-search：`enrich-abstracts` 新增 `--reuse`。nsfc-length-aligner 的 `config.yaml` 是篇幅预算的唯一来源，在那里改下限，并同步说明文档。

**Tech Stack:** Python 3 标准库、PyYAML、requests；pytest（unittest 风格）。

**Spec:** `docs/superpowers/specs/2026-10-09-nsfc-proposal-design.md`。本轮要求来自申请人 2026-10-10 在对话中的决定：「第四轮做前四条，篇幅下调」。前四条见评测目录 `funded-comparison.md`「fresh-1 暴露的问题」第 1–4 条：

1. bib_resolve 不解码 HTML 实体，已写入的条目要有刷新路径（手改会破坏台账核对）。
2. 数字核对不认「percent」。
3. nsfc-justification-writer 的 `coach --out` 不建输出目录。
4. 第二次补摘要少于第一次时，没有规定能否沿用前次结果。

篇幅：研究内容的下限 12000 字，三次运行和获资助申请书都在 7400–8500 字；立项依据的下限 8000 字，四份稿件在 4900–8000 字。两章下限都下调。研究基础没有可比数据（获资助申请书的 PDF 不含这一部分），fresh-1 的不足来自申请人材料缺失，不改。

## Global Constraints

- 分支 `nsfc-proposal`，远程 `lauorie`（git@github.com:Lauorie/guoziran.git）。各任务不推送，由控制者在终审后统一推送。
- 不新增必需的第三方依赖：只用标准库、PyYAML、requests。
- 脚本用 `Path(__file__).resolve()` 定位 skill 资产；文件读写显式 `encoding="utf-8"`。
- 输出路径限制在 project_root（P）或任务目录（T，目录名以 `task-` 开头且父目录名为 `.bensz-api`）内；越界报错，退出码 2。
- 仓库中不得出现本机用户目录的绝对路径和团队服务的域名；检查用的 `git grep` 模式由控制者在派发任务时给出，不写进仓库。
- HTTP 请求不附带个人邮箱或身份信息（不加 mailto）。
- `.bib` 条目文本只由脚本按检索结果写入；不手写、不手改。
- 正文占位格式固定为 `【待补充：……】`；内部编号不进正文。
- 示例不得回显对比基准（中标书）的题材：创造力、具身、物化、照样制作、近红外、综合实践活动课程、课时、班级等词不进 skill 文档与测试。tracked 文件不提中标书本身。
- 版本号不改动（本分支的版本已提升、尚未发布）：nsfc-proposal 0.1.0、nsfc-justification-writer 1.4.0、research-literature-search 1.1.0、nsfc-research-content-writer 1.1.0、nsfc-length-aligner 0.3.1。改动记入各自 CHANGELOG：前四个记入现有版本段落（BAC 行仍在段落最后）；nsfc-length-aligner 记入 `[Unreleased]` 的 `### Changed`。根 `CHANGELOG.md` `[Unreleased]` 每项同步一句。
- 测试放 `tests/<skill名>/`，unittest 风格，文件名全仓唯一（带 skill 缩写前缀）。测试不联网，产物写系统临时目录。测试命令（仓库根目录）：`PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider -W ignore::pytest.PytestConfigWarning tests/nsfc-proposal tests/nsfc-justification-writer tests/nsfc-research-content-writer tests/nsfc-research-foundation-writer tests/research-literature-search`。基线 399 passed、13 subtests passed。
- 提交信息 `<type>(<skill>): <中文摘要>`，末尾附 `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`（写实际完成提交的模型）。每次提交前测试 0 failed；`find skills tests -name __pycache__ -o -name .pytest_cache` 无输出。不要用 `python3 -I`（它忽略 PYTHONPYCACHEPREFIX）。
- 文档风格：短句，少副词，不写宣传用语。
- 不改系统级 skill，不碰网页版（`nsfc-skill-web`）。

## Review Focus

1. 刷新时 CrossRef 不可达、DOI 已不存在或返回的标题对不上：该条目和台账都不动，其余条目照常刷新，退出码 1。测试在 Task 2。
2. 一份 `.bib` 里有多条文献，只刷新其中一条：其他条目逐字不变，`audit` 两节都为 0。测试在 Task 2。
3. `enrich-abstracts --reuse` 指向的文件就是 `--output`：先读旧文件再覆盖，摘要不丢。测试在 Task 5。
4. 摘要写「10–20 percent」「7 percentage points」「3.5 per cent」：正文写对应的百分数不报；写错的数字仍报。测试在 Task 3。
5. CrossRef 返回两层编码（`&amp;amp;`）或编码过的标签（`&lt;i&gt;`）：解成一个 `&`、去掉标签后再做 LaTeX 转义。测试在 Task 1。

---

### Task 1: bib_resolve 先解 HTML 实体再转义

fresh-1 中 8 条期刊名写成了 `Waste Management \&amp; Research`，排版后显示「&amp;」。原因：CrossRef 返回的 `container-title` 带 `&amp;`，`_escape`（`bib_resolve.py:211`）把 `&` 转成 `\&`，留下 `amp;`。标题比对 `_norm_title` 也没有解实体。

**Files:**
- Modify: `skills/nsfc-proposal/scripts/bib_resolve.py`（`import html`；新增 `_unescape_html`；改 `_norm_title`、`_escape`）
- Modify: `tests/nsfc-proposal/test_np_bib_resolve.py`（`HelperTest` 加 3 个测试）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`（0.1.0 段 `### Changed` 末尾、BAC 行之前加一行）、根 `CHANGELOG.md`

**Interfaces:**
- Produces: `bib_resolve._unescape_html(text: str) -> str`；`_escape`、`_norm_title` 行为改变（接口不变）。Task 2 依赖 `to_bibtex` 输出不含 HTML 实体。

- [ ] **Step 1: 写失败的测试**

在 `tests/nsfc-proposal/test_np_bib_resolve.py` 的 `HelperTest` 类末尾（`test_escape_tilde_caret_backslash` 之后）加：

```python
    def test_html_entities_are_decoded_before_latex_escape(self) -> None:
        self.assertEqual(bib_resolve._escape("Waste Management &amp; Research"), r"Waste Management \& Research")
        self.assertEqual(bib_resolve._escape("Memory &amp;amp; Cognition"), r"Memory \& Cognition")
        self.assertEqual(bib_resolve._escape("&lt;i&gt;In vivo&lt;/i&gt; tests of &#39;x&#39;"), "In vivo tests of 'x'")
        self.assertEqual(bib_resolve._escape("Rate &lt; 5 &amp; 10%"), r"Rate < 5 \& 10\%")

    def test_crossref_journal_with_entity_renders_plain_ampersand(self) -> None:
        item = {"type": "journal-article", "title": ["T"], "container-title": ["Accident Analysis &amp; Prevention"]}
        entry = to_bibtex(crossref_meta(item), "a")
        self.assertIn(r"journal = {Accident Analysis \& Prevention}", entry)
        self.assertNotIn("amp;", entry)

    def test_title_matching_ignores_entities(self) -> None:
        self.assertTrue(title_matches("Habits &amp; goals in daily recycling behaviour", "Habits & Goals in Daily Recycling Behaviour", 0.92))
```

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_bib_resolve.py -k "entities or entity"`
Expected: 3 failed（`\&amp;` 仍在输出中；标题相似度不足）。

- [ ] **Step 3: 实现**

`bib_resolve.py` 顶部 import 区加 `import html`（按字母序放在 `import argparse` 之后）。在 `_norm_title` 之前加：

```python
def _unescape_html(text: str) -> str:
    """检索源的文本常带 HTML 实体（&amp;），偶有两层编码（&amp;amp;）；最多解两层。"""
    for _ in range(2):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text
```

`_norm_title` 第一行改为先解实体：

```python
def _norm_title(text: str) -> str:
    text = unicodedata.normalize("NFKC", _unescape_html(text)).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()
```

`_escape` 先解实体，再去标签，再转义（编码过的标签解开后也会被去掉）：

```python
def _escape(text: str) -> str:
    text = _unescape_html(text)
    text = re.sub(r"</?(?:i|b|em|strong|sub|sup|scp|span|mml:[A-Za-z]+)(?:\s[^>]*)?>", "", text, flags=re.IGNORECASE)
    return "".join(LATEX_SPECIALS.get(ch, ch) for ch in text)
```

- [ ] **Step 4: 运行，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_bib_resolve.py`
Expected: 全部通过（含原有的 `test_escape_markup_and_special_chars`：`p<0.05 and n>3` 不受影响）。

- [ ] **Step 5: CHANGELOG**

`skills/nsfc-proposal/CHANGELOG.md` 的 `## [0.1.0]` 段 `### Changed（变更）` 末尾、BAC 行之前加：

```markdown
- `bib_resolve` 先解 HTML 实体（最多两层）再做 LaTeX 转义，标题比对同样先解实体；此前 CrossRef 期刊名中的 `&amp;` 会写成 `\&amp;`，排版显示「&amp;」（来源：fresh-1 验证运行）。
```

根 `CHANGELOG.md` 的 `[Unreleased]` 末尾加：

```markdown
- `nsfc-proposal` 0.1.0：`bib_resolve` 先解 HTML 实体再转义，期刊名不再显示「&amp;」。
```

- [ ] **Step 6: 全量测试并提交**

Run: 全局测试命令。Expected: 402 passed。

```bash
git add skills/nsfc-proposal/scripts/bib_resolve.py tests/nsfc-proposal/test_np_bib_resolve.py skills/nsfc-proposal/CHANGELOG.md CHANGELOG.md
git commit -m "fix(nsfc-proposal): bib_resolve 先解 HTML 实体再转义" -m "Co-Authored-By: <实际模型> <noreply@anthropic.com>"
```

---

### Task 2: bib_refresh：按台账 DOI 刷新已写入的条目

fresh-1 的 8 条 `\&amp;` 条目修不了：规则 8 不许手改；手改后 `citation_ledger.py audit` 报哈希不一致；重跑 `bib_resolve` 时它们按 DOI 判为 `exists`，不会重写。现有的 drop → 删条目 → 重新解析一路要手工找记录、key 可能变，正文的 `\cite` 随之失效。

新增 `bib_refresh.py`：只处理台账中由 `bib_resolve` 写入（最后有效事件为 `add`）且带 DOI 的条目；按 DOI 回 CrossRef 取元数据并核对标题；用原 key 生成条目，替换 `.bib` 中的原文（写前备份）；在台账追加一条 `reason` 为 `refresh` 的 add 事件，沿用原有摘要与来源。新文本与原文规范化后相同则不写。

为避免重复代码，先在 `bib_resolve.py` 抽出三个公共函数：`crossref_by_doi`（`lookup` 与 `_authoritative_by_doi` 改用它，失败原因的文字不变）、`check_task_root`、`backup_file`（`append_entries` 改用它）。

**Files:**
- Modify: `skills/nsfc-proposal/scripts/bib_resolve.py`（抽出 `crossref_by_doi`、`check_task_root`、`backup_file`）
- Modify: `skills/nsfc-proposal/scripts/citation_ledger.py`（`add_event` 加 `reason` 参数；模块说明）
- Create: `skills/nsfc-proposal/scripts/bib_refresh.py`
- Modify: `skills/nsfc-proposal/SKILL.md`（规则 8；「失败与恢复」表加一行）
- Modify: `skills/nsfc-proposal/README.md`（若有脚本清单，加 `bib_refresh.py` 一行；没有则不改）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`
- Create: `tests/nsfc-proposal/test_np_bib_refresh.py`

**Interfaces:**
- Consumes: Task 1 的 `to_bibtex`（输出不含 HTML 实体）；`citation_ledger.load_ledger`、`append_event`、`entry_sha256`、`register_user_entries`、`audit`；`latex_files.bib_entry_texts`、`scan_latex_tree`、`normalize_doi`；`proposal_common.ProposalError`、`load_config`、`proposal_paths`、`resolve_project_root`。
- Produces:
  - `bib_resolve.crossref_by_doi(doi: str, title: str, *, session: HttpSession, settings: Settings) -> tuple[WorkMeta | None, str | None]`
  - `bib_resolve.check_task_root(task_root: Path) -> Path`
  - `bib_resolve.backup_file(path: Path, backup_dir: Path) -> Path`
  - `citation_ledger.add_event(..., reason: str | None = None)`
  - `bib_refresh.refresh(project_root: Path, task_root: Path, keys: Sequence[str], *, session: HttpSession | None = None, sleep: Callable[[float], None] | None = None) -> dict[str, Any]`
  - CLI：`python3 S/scripts/bib_refresh.py --project-root P --task-root T --key K [--key K2 ...]`。写 `T/nsfc-proposal/output/bib_refresh.json`，备份写 `T/nsfc-proposal/output/bib_backup/`。退出码：0 全部刷新或无需改动；1 有条目刷新失败（该条目保持原样）；2 输入或路径错误（不写任何文件）。

- [ ] **Step 1: 写失败的测试**

`tests/nsfc-proposal/test_np_bib_refresh.py`：

```python
"""bib_refresh：按台账 DOI 重新取 CrossRef 元数据，原 key 重写条目，台账追加 add 事件。不联网。"""
from __future__ import annotations

import json
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

import bib_refresh  # noqa: E402
from bib_resolve import CROSSREF_WORKS, USER_AGENT, crossref_meta, to_bibtex  # noqa: E402
from citation_ledger import add_event, append_event, audit, load_ledger, register_user_entries  # noqa: E402
from latex_files import bib_entry_texts  # noqa: E402
from proposal_common import proposal_paths  # noqa: E402

KEY = "tester2024peritumoral"
DOI = "10.5555/nsfc.test.001"
DOI_URL = f"{CROSSREF_WORKS}/{DOI}"
TITLE = "Peritumoral texture and invasiveness of test nodules in a multicenter cohort study"
ITEM = {"DOI": "10.5555/NSFC.TEST.001", "title": [TITLE], "author": [{"family": "Tester", "given": "Alice"}],
        "container-title": ["Waste Management &amp; Research"], "issued": {"date-parts": [[2024]]},
        "volume": "7", "issue": "2", "page": "100-110", "type": "journal-article"}
CLEAN = to_bibtex(crossref_meta({**ITEM, "container-title": ["Waste Management & Research"]}), KEY)
OLD = CLEAN.replace("\\&", "\\&amp;")
OTHER = "@article{other2020x,\n  title = {{Other}},\n  year = {2020},\n}\n"
USER = "@article{user2019y,\n  title = {{User paper}},\n  year = {2019},\n  doi = {10.5555/user.1},\n}\n"
ABSTRACT = "This abstract is long enough to be stored in the citation ledger for the refreshed test entry here."
PROVENANCE = {"record_id": "doi:10.5555/nsfc.test.001", "record_title": TITLE, "query_matches": ["q01"],
              "host_tool": "wispaper", "provider": "mcp"}


class FakeResponse:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status_code, self.headers, self._payload = status, {}, payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """按 URL 返回固定响应；未登记的 URL 返回 404；登记为异常时抛出。"""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict, dict]] = []

    def get(self, url: str, params: Any = None, headers: Any = None, timeout: Any = None) -> FakeResponse:
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        value = self.routes.get(url)
        if isinstance(value, Exception):
            raise value
        return value if value is not None else FakeResponse(404)


class RefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "proj"
        (self.root / "references").mkdir(parents=True)
        (self.root / "proposal").mkdir()
        (self.root / "main.tex").write_text("\\input{references/reference.tex}\n", encoding="utf-8")
        (self.root / "references" / "reference.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
        self.bib = self.root / "references" / "refs.bib"
        self.task = base / ".bensz-api" / "task-20261010-1200-test"
        self.ledger = proposal_paths(self.root).ledger
        self.waits: list[float] = []
        self._write_bib(OLD)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_bib(self, entry: str) -> None:
        self.bib.write_text(OTHER + "\n" + entry + "\n" + USER, encoding="utf-8")
        if self.ledger.exists():
            self.ledger.unlink()
        texts = bib_entry_texts([self.bib])
        append_event(self.ledger, add_event("other2020x", source="crossref", entry_text=texts["other2020x"], doi=None,
                                            abstract=None, provenance={"record_id": "r0"}))
        append_event(self.ledger, add_event(KEY, source="crossref", entry_text=texts[KEY], doi=DOI, abstract=ABSTRACT,
                                            provenance=PROVENANCE))
        register_user_entries(self.root, ["user2019y"])

    def _snapshot(self) -> tuple[str, str]:
        return self.bib.read_text(encoding="utf-8"), self.ledger.read_text(encoding="utf-8")

    def _refresh(self, session: FakeSession, *keys: str) -> dict:
        return bib_refresh.refresh(self.root, self.task, list(keys) or [KEY], session=session, sleep=self.waits.append)

    def _main(self, *keys: str) -> int:
        args = ["--project-root", str(self.root), "--task-root", str(self.task)]
        for key in keys:
            args += ["--key", key]
        return bib_refresh.main(args)

    def test_refresh_rewrites_entry_keeps_key_and_passes_audit(self) -> None:
        other_before = bib_entry_texts([self.bib])["other2020x"]
        session = FakeSession({DOI_URL: FakeResponse(200, {"message": ITEM})})
        summary = self._refresh(session)
        self.assertEqual(summary["counts"], {"refreshed": 1, "unchanged": 0, "failed": 0})
        text = self.bib.read_text(encoding="utf-8")
        self.assertIn(f"@article{{{KEY},", text)
        self.assertIn("journal = {Waste Management \\& Research}", text)
        self.assertNotIn("amp;", text)
        self.assertEqual(bib_entry_texts([self.bib])["other2020x"], other_before)
        self.assertEqual(audit(self.root), ([], []))
        record = load_ledger(self.ledger)[KEY]
        self.assertEqual((record["event"], record["reason"], record["abstract"], record["provenance"]),
                         ("add", "refresh", ABSTRACT, PROVENANCE))
        self.assertTrue(summary["backups"])
        self.assertTrue(all(Path(p).is_file() for p in summary["backups"]))
        self.assertTrue((self.task / "nsfc-proposal" / "output" / "bib_refresh.json").is_file())
        url, params, headers = session.calls[0]
        self.assertEqual(headers.get("User-Agent"), USER_AGENT)
        self.assertNotIn("mailto", json.dumps([url, params, headers]))

    def test_unchanged_entry_writes_nothing(self) -> None:
        self._write_bib(CLEAN)
        before = self._snapshot()
        summary = self._refresh(FakeSession({DOI_URL: FakeResponse(200, {"message": ITEM})}))
        self.assertEqual(summary["counts"], {"refreshed": 0, "unchanged": 1, "failed": 0})
        self.assertEqual(summary["backups"], [])
        self.assertEqual(self._snapshot(), before)

    def test_network_failure_leaves_entry_and_ledger(self) -> None:
        before = self._snapshot()
        summary = self._refresh(FakeSession({DOI_URL: requests.ConnectionError("down")}))
        self.assertEqual(summary["counts"], {"refreshed": 0, "unchanged": 0, "failed": 1})
        self.assertIn("CrossRef DOI 查询失败", summary["outcomes"][0]["reason"])
        self.assertEqual(self._snapshot(), before)

    def test_title_mismatch_fails_and_leaves_entry(self) -> None:
        before = self._snapshot()
        other = {**ITEM, "title": ["Cardiac strain imaging in an unrelated cohort of adults"]}
        summary = self._refresh(FakeSession({DOI_URL: FakeResponse(200, {"message": other})}))
        self.assertEqual(summary["outcomes"][0]["status"], "failed")
        self.assertIn("标题", summary["outcomes"][0]["reason"])
        self.assertEqual(self._snapshot(), before)

    def test_cli_exit_codes(self) -> None:
        with mock.patch.object(bib_refresh.requests, "Session", return_value=FakeSession({})):
            self.assertEqual(self._main(KEY), 1)  # CrossRef 404：刷新失败，条目不动
        with mock.patch.object(bib_refresh.requests, "Session", return_value=FakeSession({DOI_URL: FakeResponse(200, {"message": ITEM})})):
            self.assertEqual(self._main(KEY), 0)
        self.assertNotIn("amp;", self.bib.read_text(encoding="utf-8"))

    def test_keys_that_cannot_be_refreshed_exit_2_without_writing(self) -> None:
        before = self._snapshot()
        for bad in ("user2019y", "missing2000z", "other2020x"):  # 申请人登记、不在 .bib、台账无 DOI
            with self.subTest(key=bad):
                self.assertEqual(self._main(KEY, bad), 2)
                self.assertEqual(self._snapshot(), before)
        self.assertFalse((self.task / "nsfc-proposal" / "output" / "bib_refresh.json").exists())

    def test_task_root_must_be_task_dir(self) -> None:
        args = ["--project-root", str(self.root), "--task-root", str(self.root), "--key", KEY]
        self.assertEqual(bib_refresh.main(args), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_bib_refresh.py`
Expected: 收集失败（`ModuleNotFoundError: No module named 'bib_refresh'`）。

- [ ] **Step 3: bib_resolve 抽出公共函数**

在 `_authoritative_by_doi` 之前加 `crossref_by_doi`，并改写 `_authoritative_by_doi`：

```python
def crossref_by_doi(doi: str, title: str, *, session: HttpSession, settings: Settings) -> tuple[WorkMeta | None, str | None]:
    """用 DOI 回 CrossRef 取元数据，返回 (元数据, 失败原因)；给了标题时要求标题相符。"""
    try:
        data = _get_json(session, f"{CROSSREF_WORKS}/{quote(doi, safe='/')}", None, settings)
    except (requests.RequestException, ValueError) as exc:
        return None, f"CrossRef DOI 查询失败（{failure_label(exc)}）"
    meta = crossref_meta((data or {}).get("message") or {}) if data else None
    if meta is None:
        return None, "CrossRef 没有这个 DOI"
    if title and not title_matches(title, meta.title, settings.doi_title_similarity):
        return None, f"DOI {doi} 对应的标题与记录不符"
    return meta, None


def _authoritative_by_doi(doi: str, title: str, *, session: HttpSession, settings: Settings) -> WorkMeta | None:
    """用 DOI 回 CrossRef 取元数据；查询失败、无此 DOI 或标题不符时返回 None。"""
    return crossref_by_doi(doi, title, session=session, settings=settings)[0]
```

`lookup` 中 `if doi:` 一段改为：

```python
    if doi:
        meta, failure = crossref_by_doi(doi, title, session=session, settings=settings)
        if meta is not None:
            return meta, "crossref", None
        failures.append(failure)
```

在 `append_entries` 之前加 `backup_file`，`append_entries` 改用它：

```python
def backup_file(path: Path, backup_dir: Path) -> Path:
    """把 path 复制到 backup_dir，文件名加时间戳；返回备份路径。"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.name}.{datetime.now().strftime('%Y%m%d%H%M%S%f')}.bak"
    shutil.copy2(path, backup)
    return backup


def append_entries(bib_path: Path, entries: list[str], backup_dir: Path) -> Path | None:
    """追加条目；写前备份。没有条目时不碰文件。"""
    if not entries:
        return None
    backup = None
    text = ""
    if bib_path.exists():
        backup = backup_file(bib_path, backup_dir)
        text = bib_path.read_text(encoding="utf-8")
    else:
        bib_path.parent.mkdir(parents=True, exist_ok=True)
    if not text:
        separator = ""
    elif text.endswith("\n\n"):
        separator = ""
    elif text.endswith("\n"):
        separator = "\n"
    else:
        separator = "\n\n"
    bib_path.write_text(text + separator + "\n".join(entries), encoding="utf-8")
    return backup
```

在 `run` 之前加 `check_task_root`，`run` 开头两行改用它：

```python
def check_task_root(task_root: Path) -> Path:
    """返回解析后的任务目录；不是 .bensz-api/task-*/ 时报错。"""
    task = Path(task_root).expanduser().resolve()
    if not task.name.startswith("task-") or task.parent.name != ".bensz-api":
        raise ProposalError(f"--task-root 必须指向 .bensz-api/task-*/ 目录：{task}")
    return task
```

```python
    root = resolve_project_root(project_root)
    task = check_task_root(task_root)
```

模块说明第 7 行之后加一句：「已写入的条目要按来源更新时，用 bib_refresh.py。」

- [ ] **Step 4: citation_ledger 的 add_event 加 reason**

```python
def add_event(bibkey: str, *, source: str | None, entry_text: str, doi: str | None, abstract: str | None,
              provenance: Mapping[str, Any], reason: str | None = None) -> dict[str, Any]:
    return {"event": "add", "bibkey": bibkey, "time": now_iso(), "source": source, "doi": doi,
            "entry_sha256": entry_sha256(entry_text), "abstract": abstract, "provenance": dict(provenance), "reason": reason}
```

模块说明第 6–7 行改为：

```text
事件：add（bib_resolve 写入；bib_refresh 按台账中的 DOI 重新取元数据、原 key 重写条目后再记一条，reason 为 refresh）、
register_user（申请人确认由其提供、用 register-user --key 登记的条目）、drop（作废）。case.py init 只建空台账，不登记任何条目。
条目文本只由脚本写，不接受手改。同一篇文献的条目有误时用 bib_refresh；要换成另一篇，先 drop，再用 bib_resolve 重新解析。
```

- [ ] **Step 5: 写 bib_refresh.py**

`skills/nsfc-proposal/scripts/bib_refresh.py`：

```python
#!/usr/bin/env python3
"""按引用台账中的 DOI 重新取 CrossRef 元数据，用原 key 重写 .bib 条目，并在台账追加 add 事件（reason 为 refresh）。

用途：旧版 bib_resolve 写入的条目有缺陷（如期刊名中的 &amp;），或条目需要按来源更新。条目文本只来自检索，
不接受手改；key 不变，正文的 \\cite 不用改。只处理台账中由 bib_resolve 写入（add）且带 DOI 的条目；
申请人登记的条目（register_user）与没有 DOI 的条目不刷新：先 citation_ledger.py drop，从 .bib 删去，再用 bib_resolve 重新解析。
退出码：0 全部刷新或无需改动；1 有条目刷新失败（该条目保持原样）；2 输入或路径错误（不写任何文件）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import requests

from bib_resolve import HttpSession, Settings, backup_file, check_task_root, crossref_by_doi, to_bibtex
from citation_ledger import add_event, append_event, entry_sha256, load_ledger
from latex_files import bib_entry_texts, normalize_doi, scan_latex_tree
from proposal_common import ProposalError, load_config, proposal_paths, resolve_project_root

TITLE_FIELD_RE = re.compile(r"^\s*title\s*=\s*\{\{?(.*?)\}?\},?\s*$", re.MULTILINE)


@dataclass
class RefreshOutcome:
    bibkey: str
    status: str  # refreshed | unchanged | failed
    doi: str | None = None
    reason: str | None = None


def _wanted_title(record: Mapping[str, Any], entry_text: str) -> str:
    """核对标题用台账记下的检索记录标题；没有时用条目里的 title 字段。"""
    provenance = record.get("provenance") if isinstance(record.get("provenance"), Mapping) else {}
    title = str(provenance.get("record_title") or "").strip()
    if title:
        return title
    match = TITLE_FIELD_RE.search(entry_text)
    return match.group(1) if match else ""


def _check_keys(keys: Sequence[str], texts: Mapping[str, str], ledger: Mapping[str, Mapping[str, Any]]) -> None:
    """有任何一个 key 不能刷新时报错，一条也不处理。"""
    absent = [k for k in keys if k not in texts]
    if absent:
        raise ProposalError(f".bib 中没有这些条目：{'、'.join(absent)}")
    not_added = [k for k in keys if (ledger.get(k) or {}).get("event") != "add"]
    if not_added:
        raise ProposalError(f"这些条目不是 bib_resolve 写入的（台账中没有有效的 add 记录），不能刷新：{'、'.join(not_added)}；"
                            "申请人登记的条目由申请人核对")
    no_doi = [k for k in keys if not normalize_doi(ledger[k].get("doi"))]
    if no_doi:
        raise ProposalError(f"这些条目在台账中没有 DOI，不能刷新：{'、'.join(no_doi)}；"
                            "请先 citation_ledger.py drop，从 .bib 删去，再用 bib_resolve 重新解析")


def _rewrite(bib_files: Sequence[Path], old_texts: Mapping[str, str], new_texts: Mapping[str, str], backup_dir: Path) -> list[str]:
    """把各 key 的条目原文换成新文本；只改含该条目的文件，写前备份。返回备份路径。"""
    backups: list[str] = []
    for path in bib_files:
        path = Path(path)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated = text
        for key, new in new_texts.items():
            old = old_texts[key].rstrip()
            if updated.count(old) == 1:
                updated = updated.replace(old, new.rstrip(), 1)
        if updated != text:
            backups.append(str(backup_file(path, backup_dir)))
            path.write_text(updated, encoding="utf-8")
    return backups


def refresh(project_root: Path, task_root: Path, keys: Sequence[str], *, session: HttpSession | None = None,
            sleep: Callable[[float], None] | None = None) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    task = check_task_root(task_root)
    wanted = list(dict.fromkeys(keys))
    if not wanted:
        raise ProposalError("至少给一个 --key")
    tree = scan_latex_tree(root)
    if not tree.bib_files:
        raise ProposalError("main.tex 及其 \\input 文件中没有 \\bibliography，无法确定 .bib")
    texts = bib_entry_texts(tree.bib_files)
    ledger_path = proposal_paths(root).ledger
    ledger = load_ledger(ledger_path)
    _check_keys(wanted, texts, ledger)
    settings = Settings.from_config(load_config())
    if sleep is not None:
        settings = replace(settings, sleep=sleep)
    http = session or requests.Session()
    outcomes: list[RefreshOutcome] = []
    new_texts: dict[str, str] = {}
    for key in wanted:
        doi = normalize_doi(ledger[key].get("doi"))
        meta, reason = crossref_by_doi(doi, _wanted_title(ledger[key], texts[key]), session=http, settings=settings)
        if meta is None:
            outcomes.append(RefreshOutcome(key, "failed", doi=doi, reason=reason))
            continue
        text = to_bibtex(meta, key)
        if entry_sha256(text) == entry_sha256(texts[key]):
            outcomes.append(RefreshOutcome(key, "unchanged", doi=doi))
            continue
        new_texts[key] = text
        outcomes.append(RefreshOutcome(key, "refreshed", doi=meta.doi or doi))
    out_dir = task / "nsfc-proposal" / "output"
    backups = _rewrite(tree.bib_files, texts, new_texts, out_dir / "bib_backup")
    written = bib_entry_texts(tree.bib_files)
    for outcome in outcomes:
        if outcome.status != "refreshed":
            continue
        if entry_sha256(written.get(outcome.bibkey, "")) != entry_sha256(new_texts[outcome.bibkey]):
            outcome.status, outcome.reason = "failed", "未能在 .bib 中定位原条目文本，条目未改"
            continue
        prior = ledger[outcome.bibkey]
        append_event(ledger_path, add_event(
            outcome.bibkey, source="crossref", entry_text=written[outcome.bibkey], doi=outcome.doi,
            abstract=prior.get("abstract"), provenance=prior.get("provenance") or {}, reason="refresh"))
    summary = {
        "bib_files": [str(p) for p in tree.bib_files],
        "backups": backups,
        "counts": {status: sum(1 for o in outcomes if o.status == status) for status in ("refreshed", "unchanged", "failed")},
        "outcomes": [asdict(o) for o in outcomes],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bib_refresh.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bib_refresh.py", description="按台账中的 DOI 重新取元数据，用原 key 重写 .bib 条目")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task-root", required=True, help="本任务的 .bensz-api/task-*/ 目录")
    parser.add_argument("--key", action="append", required=True, help="要刷新的 bibkey；可重复")
    args = parser.parse_args(argv)
    try:
        summary = refresh(Path(args.project_root), Path(args.task_root), args.key)
    except ProposalError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["counts"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 运行，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_bib_refresh.py tests/nsfc-proposal/test_np_bib_resolve.py tests/nsfc-proposal/test_np_citation_ledger.py`
Expected: 全部通过。

- [ ] **Step 7: SKILL.md**

规则 8 中，把「要修正某条文献，先 `python3 S/scripts/citation_ledger.py drop --project-root P --key K --reason "…"`，从 `.bib` 删去该条，再用 `bib_resolve` 重新解析（仍留在 `.bib` 的作废条目会被报为 `exists`）。」改为：

```markdown
要修正某条文献：仍是同一篇、只是条目文本有误（如期刊名显示 `&amp;`、类型或字段缺失）时，运行 `python3 S/scripts/bib_refresh.py --project-root P --task-root T --key K`（可重复 `--key`），按台账中的 DOI 重新取 CrossRef 元数据，原 key 不变，台账追加一条记录；退出码 1 表示有条目没有刷新，原样保留，原因见 `T/nsfc-proposal/output/bib_refresh.json`。要换成另一篇，或条目是申请人登记的、台账中没有 DOI，先 `python3 S/scripts/citation_ledger.py drop --project-root P --key K --reason "…"`，从 `.bib` 删去该条，再用 `bib_resolve` 重新解析（仍留在 `.bib` 的作废条目会被报为 `exists`）。
```

「失败与恢复」表中「台账与 `.bib` 不一致」一行之后加一行：

```markdown
| `.bib` 条目显示 `&amp;` 等 HTML 实体（旧版 `bib_resolve` 写入） | 不手改。在 `.bib` 中搜 `&amp;`、`&lt;`、`&gt;`、`&#` 找出这些条目，按规则 8 用 `bib_refresh.py` 刷新 |
```

「输出管理」中列 `bib_resolve.json` 的地方，同句补上 `bib_refresh.json`（写在 `T/nsfc-proposal/output/`）。

- [ ] **Step 8: CHANGELOG**

`skills/nsfc-proposal/CHANGELOG.md` 0.1.0 段 `### Added（新增）` 末尾加：

```markdown
- `scripts/bib_refresh.py`：按引用台账中的 DOI 重新取 CrossRef 元数据，用原 key 重写 `.bib` 条目，台账追加 `reason` 为 `refresh` 的 add 事件；申请人登记的条目与没有 DOI 的条目不刷新（来源：fresh-1 验证运行）。
```

根 `CHANGELOG.md` `[Unreleased]` 末尾加：

```markdown
- `nsfc-proposal` 0.1.0：新增 `bib_refresh.py`，按台账 DOI 刷新已写入的 `.bib` 条目，key 与正文引用不变。
```

- [ ] **Step 9: 全量测试并提交**

Run: 全局测试命令。Expected: 409 passed（Task 1 之后 402，加 7）。

```bash
git add skills/nsfc-proposal/scripts/bib_resolve.py skills/nsfc-proposal/scripts/citation_ledger.py skills/nsfc-proposal/scripts/bib_refresh.py skills/nsfc-proposal/SKILL.md skills/nsfc-proposal/CHANGELOG.md CHANGELOG.md tests/nsfc-proposal/test_np_bib_refresh.py
git commit -m "feat(nsfc-proposal): bib_refresh 按台账 DOI 刷新已写入的条目" -m "Co-Authored-By: <实际模型> <noreply@anthropic.com>"
```

（README 有改动时一并 add。）

---

### Task 3: 数字核对认 percent

fresh-1 中，正文「10%至20%」所引文献的摘要写「10–20 percent」，`consistency_check` 报 `number_not_in_evidence`。写稿时为了过检查，改成了「一成至两成」，数字变模糊。`_evidence_readings` 已处理 `\%`、全角 ％、英文数词与千分位，没有处理 percent。

**Files:**
- Modify: `skills/nsfc-proposal/scripts/consistency_check.py`（新增两条正则；`_evidence_readings`）
- Modify: `tests/nsfc-proposal/test_np_consistency.py`（`LedgerConsistencyTest` 加 2 个测试）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`

**Interfaces:**
- Produces: `_evidence_readings` 把 `10–20 percent`、`10 to 20 per cent` 读作 `10%–20%`、`10% to 20%`，把 `7 percentage points` 读作 `7%`。`number_in_text` 接口不变。

- [ ] **Step 1: 写失败的测试**

在 `LedgerConsistencyTest` 的 `test_english_number_words_in_abstract` 之后加：

```python
    def test_percent_words_in_abstract(self) -> None:
        a = ("Energy use fell by 10–20 percent in treated households, sorting accuracy rose 7 percentage points, "
             "and contamination dropped 3.5 per cent, from 12 to 15 percent of bins over the study.")
        self.assertEqual(self._number_details("用电量下降10\\%至20\\%\\cite{wu2021value}。\n", a), [])
        self.assertEqual(self._number_details("正确率提高7个百分点\\cite{wu2021value}。\n", a), [])
        self.assertEqual(self._number_details("混投下降3.5\\%\\cite{wu2021value}。\n", a), [])
        self.assertEqual(self._number_details("占比由12\\%升至15\\%\\cite{wu2021value}。\n", a), [])
        self.assertEqual(len(self._number_details("用电量下降30\\%\\cite{wu2021value}。\n", a)), 1)

    def test_number_in_text_reads_percent_words(self) -> None:
        from consistency_check import number_in_text
        text = "Rates rose by 10-20 Percent and by 4.5 per cent; another arm gained 6 percentage-points."
        for value in ("10%", "20%", "4.5%", "6%"):
            self.assertTrue(number_in_text(value, text), value)
        self.assertFalse(number_in_text("45%", text))
```

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_consistency.py -k percent`
Expected: 2 failed。

- [ ] **Step 3: 实现**

`consistency_check.py` 中，紧接 `_LATEX_LENGTH_RE` 定义之后加：

```python
_PERCENT_WORDS = r"(?:per\s*cent|percentage[\s-]points?)\b"
_PERCENT_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)(\s*(?:[–—\-~～]|to)\s*)(\d+(?:\.\d+)?)\s*" + _PERCENT_WORDS, re.IGNORECASE)
_PERCENT_WORD_RE = re.compile(r"(\d+(?:\.\d+)?)\s*" + _PERCENT_WORDS, re.IGNORECASE)
```

`_evidence_readings` 改为：

```python
def _evidence_readings(text: str) -> list[str]:
    """摘要的两种读法：原样，以及把空格类千分位并回；数字声称见于任一读法即算有据。percent 写法读作 %。"""
    text = re.sub(r"\\%", "%", text).replace("％", "%")
    text = _PERCENT_RANGE_RE.sub(r"\1%\2\3%", text)
    text = _PERCENT_WORD_RE.sub(r"\1%", text)
    text = re.sub(r"\s+%", "%", text)
    text = _NUMBER_WORD_RE.sub(lambda m: _NUMBER_WORDS[m.group(1).lower()], _THOUSANDS_RE.sub("", text))
    return [text, _SPACE_THOUSANDS_RE.sub(r"\1", text)]
```

- [ ] **Step 4: 运行，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_consistency.py`
Expected: 全部通过。

- [ ] **Step 5: CHANGELOG**

nsfc-proposal 0.1.0 段 `### Changed（变更）` 末尾、BAC 行之前加：

```markdown
- 引用句数字核对把摘要中的 percent、per cent、percentage points 读作 %（含「10–20 percent」「12 to 15 percent」这类区间）；此前这类写法会被报为数字不见于摘要（来源：fresh-1 验证运行）。
```

根 `CHANGELOG.md` `[Unreleased]` 末尾加：

```markdown
- `nsfc-proposal` 0.1.0：引用句数字核对认摘要中的 percent 写法。
```

- [ ] **Step 6: 全量测试并提交**

Run: 全局测试命令。Expected: 411 passed。

```bash
git add skills/nsfc-proposal/scripts/consistency_check.py tests/nsfc-proposal/test_np_consistency.py skills/nsfc-proposal/CHANGELOG.md CHANGELOG.md
git commit -m "fix(nsfc-proposal): 数字核对认摘要中的 percent 写法" -m "Co-Authored-By: <实际模型> <noreply@anthropic.com>"
```

---

### Task 4: nsfc-justification-writer 的 --out 先建目录

`refs`、`review`、`coach` 三个子命令的 `--out` 直接写文件，目录不存在时报 `FileNotFoundError`、退出码 2。fresh-1 第一次运行 `coach --out T/nsfc-justification-writer/output/...` 时就是这样。`diagnose` 的 HTML 报告已经先建目录。

**Files:**
- Modify: `skills/nsfc-justification-writer/scripts/run.py`（新增 `_write_out`；三处调用）
- Create: `tests/nsfc-justification-writer/test_njw_out_dir.py`
- Modify: `skills/nsfc-justification-writer/CHANGELOG.md`（`## [1.4.0]` 段 `### Fixed（修复）` 末尾）、根 `CHANGELOG.md`

**Interfaces:**
- Produces: `run._write_out(path: str, text: str) -> None`。

- [ ] **Step 1: 写失败的测试**

`tests/nsfc-justification-writer/test_njw_out_dir.py`：

```python
"""refs、review、coach 的 --out 指向不存在的目录时，先建目录再写。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/nsfc-justification-writer/scripts/run.py"


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
    env.pop("NSFC_JUSTIFICATION_WRITER_RUNS_DIR", None)
    return subprocess.run([sys.executable, str(SCRIPT), "--no-user-override", *args],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=120)


class OutDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.proj = self.base / "proj"
        (self.proj / "extraTex").mkdir(parents=True)
        (self.proj / "extraTex" / "1.1.立项依据.tex").write_text("\\subsubsection{研究背景}\n正文。\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_out_creates_missing_directories(self) -> None:
        for command in ("coach", "review", "refs"):
            with self.subTest(command=command):
                out = self.base / "out" / command / "nested" / f"{command}.md"
                proc = run_cli(self.base, command, "--project-root", str(self.proj), "--out", str(out))
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertTrue(out.is_file())
                self.assertIn("已输出", proc.stdout)

    def test_out_into_existing_directory_still_works(self) -> None:
        out = self.base / "coach.md"
        proc = run_cli(self.base, "coach", "--project-root", str(self.proj), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-justification-writer/test_njw_out_dir.py`
Expected: `test_out_creates_missing_directories` 的三个子测试失败（returncode 2，`FileNotFoundError`）；另一个通过。

- [ ] **Step 3: 实现**

`run.py` 中，在 `_read_body_file` 之前加：

```python
def _write_out(path: str, text: str) -> None:
    """把 markdown 写到 --out 指定的文件；目录不存在时先建。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"已输出：{path}")
```

`cmd_refs`、`cmd_review`、`cmd_coach` 中的

```python
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"已输出：{args.out}")
        return 0
```

都改为：

```python
    if args.out:
        _write_out(args.out, md)
        return 0
```

改完后 `grep -n 'Path(args.out).write_text' skills/nsfc-justification-writer/scripts/run.py` 应无输出。

- [ ] **Step 4: 运行，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-justification-writer`
Expected: 全部通过。

- [ ] **Step 5: CHANGELOG**

`skills/nsfc-justification-writer/CHANGELOG.md` 的 `## [1.4.0]` 段 `### Fixed（修复）` 末尾加：

```markdown
- `refs`、`review`、`coach` 的 `--out` 指向不存在的目录时先建目录；此前报 FileNotFoundError（来源：nsfc-proposal fresh-1 验证运行）。
```

根 `CHANGELOG.md` `[Unreleased]` 末尾加：

```markdown
- `nsfc-justification-writer` 1.4.0：`refs`、`review`、`coach` 的 `--out` 先建目录。
```

- [ ] **Step 6: 全量测试并提交**

Run: 全局测试命令。Expected: 413 passed（另有 3 个 subtests）。

```bash
git add skills/nsfc-justification-writer/scripts/run.py tests/nsfc-justification-writer/test_njw_out_dir.py skills/nsfc-justification-writer/CHANGELOG.md CHANGELOG.md
git commit -m "fix(nsfc-justification-writer): --out 指向的目录不存在时先建目录" -m "Co-Authored-By: <实际模型> <noreply@anthropic.com>"
```

---

### Task 5: enrich-abstracts 沿用前次补到的摘要

fresh-1 中，第一次 `enrich-abstracts` 补到 18 条摘要；补检后重新挑选，第二次运行时 OpenAlex 当日额度用完，只补到 2 条。子代理按 `record_id` 手工并入第一次的 14 条，SKILL.md 没有这一步。改为脚本支持：`--reuse <前次输出>`，同一 `record_id` 已有足够长摘要的记录直接沿用，不再请求。

**Files:**
- Modify: `skills/research-literature-search/scripts/search_runner.py`（新增 `_reusable_abstracts`；`enrich_abstracts` 加 `reuse_path`；CLI 加 `--reuse`）
- Modify: `skills/research-literature-search/SKILL.md`（`enrich-abstracts` 用法后加一句）
- Modify: `skills/research-literature-search/CHANGELOG.md`（`## [1.1.0]` 段 `### Added（新增）` 末尾）
- Modify: `skills/nsfc-proposal/SKILL.md`（第 3 步第 6 项）
- Modify: `skills/nsfc-proposal/CHANGELOG.md`、根 `CHANGELOG.md`
- Modify: `tests/research-literature-search/test_rls_enrich_abstracts.py`（新增测试类）

**Interfaces:**
- Produces:
  - `enrich_abstracts(input_path, output_path, *, ..., reuse_path: Path | None = None) -> dict`；汇总新增 `reused`（沿用条数，不计入 `attempted`）与 `reuse_file`（文件名，未用时为 null）。
  - 沿用的记录：`abstract` 取前次的摘要，`abstract_status` 为 `present`，`abstract_provenance` 为前次的来源加 `reused_from`（前次文件名）。
  - CLI：`enrich-abstracts --input I --output O [--reuse R]`；`R` 可以与 `O` 相同（先读后写）；`R` 不存在时退出码 2，不写输出。

- [ ] **Step 1: 写失败的测试**

在 `tests/research-literature-search/test_rls_enrich_abstracts.py` 顶部 import 区加 `import os`、`import subprocess`（按字母序，放在 `import json` 前后），文件末尾（`if __name__` 之前；没有则放文件末尾）加：

```python
SCRIPT = ROOT / "skills/research-literature-search/scripts/search_runner.py"


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class EnrichReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src, self.prior, self.dst = self.base / "in.jsonl", self.base / "prior.jsonl", self.base / "out.jsonl"
        _write_rows(self.src, [{"record_id": "doi:10.5555/a", "title": TITLE},
                               {"record_id": "title:other", "title": "Another paper about household sorting habits"}])
        self.calls: list[str] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _fetchers(self) -> dict:
        def fetch(q, **k):
            self.calls.append(q)
            return []
        return {name: fetch for name in ("crossref", "semantic_scholar", "openalex")}

    def test_prior_abstract_reused_by_record_id_without_request(self) -> None:
        _write_rows(self.prior, [{"record_id": "doi:10.5555/a", "title": TITLE, "abstract": LONG, "abstract_status": "present",
                                  "abstract_provenance": {"source": "openalex", "method": "post_selection"}}])
        summary = enrich_abstracts(self.src, self.dst, fetchers=self._fetchers(), reuse_path=self.prior)
        rows = _read_rows(self.dst)
        self.assertEqual((rows[0]["abstract"], rows[0]["abstract_status"]), (LONG, "present"))
        self.assertEqual(rows[0]["abstract_provenance"], {"source": "openalex", "method": "post_selection", "reused_from": "prior.jsonl"})
        self.assertNotIn(TITLE, self.calls)
        self.assertEqual((summary["reused"], summary["attempted"], summary["reuse_file"]), (1, 1, "prior.jsonl"))

    def test_prior_without_usable_abstract_is_not_reused(self) -> None:
        _write_rows(self.prior, [{"record_id": "doi:10.5555/a", "title": TITLE, "abstract": None, "abstract_status": "missing"},
                                 {"record_id": "title:other", "abstract": "too short", "abstract_status": "present"}])
        summary = enrich_abstracts(self.src, self.dst, fetchers=self._fetchers(), reuse_path=self.prior)
        self.assertEqual((summary["reused"], summary["attempted"]), (0, 2))
        self.assertIn(TITLE, self.calls)

    def test_reuse_file_may_be_the_output_file(self) -> None:
        _write_rows(self.dst, [{"record_id": "doi:10.5555/a", "title": TITLE, "abstract": LONG, "abstract_status": "present"}])
        summary = enrich_abstracts(self.src, self.dst, fetchers=self._fetchers(), reuse_path=self.dst)
        rows = _read_rows(self.dst)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["abstract"], LONG)
        self.assertEqual(summary["reused"], 1)

    def test_without_reuse_summary_reports_zero(self) -> None:
        summary = enrich_abstracts(self.src, self.dst, fetchers=self._fetchers())
        self.assertEqual((summary["reused"], summary["reuse_file"]), (0, None))

    def test_cli_missing_reuse_file_exits_2(self) -> None:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        proc = subprocess.run([sys.executable, str(SCRIPT), "enrich-abstracts", "--input", str(self.src), "--output", str(self.dst),
                               "--reuse", str(self.base / "missing.jsonl")], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertFalse(self.dst.exists())
```

- [ ] **Step 2: 运行，确认失败**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/research-literature-search/test_rls_enrich_abstracts.py -k Reuse`
Expected: 5 failed（`unexpected keyword argument 'reuse_path'`、汇总没有 `reused`、CLI 不认 `--reuse`）。

- [ ] **Step 3: 实现**

`search_runner.py` 中，`enrich_abstracts` 之前加：

```python
def _reusable_abstracts(path: Path, min_chars: int) -> dict[str, dict[str, Any]]:
    """前一次 enrich-abstracts 输出中已有足够长摘要的记录，按 record_id 索引；同一 id 取先出现的。"""
    found: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        record_id, abstract = row.get("record_id"), row.get("abstract")
        if (isinstance(record_id, str) and record_id and row.get("abstract_status") == "present"
                and isinstance(abstract, str) and len(abstract.strip()) >= min_chars):
            found.setdefault(record_id, row)
    return found
```

`enrich_abstracts` 的签名加 `reuse_path: Path | None = None`（放在 `sleep` 之后）。函数开头 `rows = _read_jsonl(input_path)` 之后加：

```python
    reusable = _reusable_abstracts(reuse_path, min_chars) if reuse_path is not None else {}  # read before output is overwritten
    reused = 0
```

循环中，紧接「已有摘要则 `continue`」那一段之后、`attempted += 1` 之前加：

```python
        prior = reusable.get(str(row.get("record_id") or ""))
        if prior is not None:
            previous = prior.get("abstract_provenance")
            row["abstract"] = prior["abstract"].strip()
            row["abstract_status"] = "present"
            row["abstract_provenance"] = {**(previous if isinstance(previous, dict) else {"method": "post_selection"}),
                                          "reused_from": Path(reuse_path).name}
            reused += 1
            continue
```

汇总字典加两项：

```python
    summary = {"mode": "selected", "attempted": attempted, "filled": filled, "reused": reused,
               "missing": sum(1 for row in output if row.get("abstract_status") == "missing"), "min_abstract_chars": min_chars,
               "max_papers_total": max_papers, "exhausted_providers": exhausted,
               "reuse_file": Path(reuse_path).name if reuse_path is not None else None}
```

`main()` 中 `enrich` 子命令加参数：

```python
    enrich.add_argument("--reuse", type=Path, help="前一次 enrich-abstracts 的输出：同一 record_id 已补到的摘要直接沿用，不再请求；可与 --output 相同")
```

分发处改为：

```python
    if args.command == "enrich-abstracts":
        if args.reuse is not None and not args.reuse.is_file():
            print(f"✗ --reuse 文件不存在：{args.reuse}", file=sys.stderr)
            return 2
        print(json.dumps(enrich_abstracts(args.input, args.output, max_papers=args.max_papers, min_chars=args.min_abstract_chars, timeout=3,
                                          retries=args.retries, backoff_s=args.backoff_s, reuse_path=args.reuse), ensure_ascii=False, indent=2))
        return 0
```

- [ ] **Step 4: 运行，确认通过**

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/research-literature-search`
Expected: 全部通过。

- [ ] **Step 5: 文档**

`skills/research-literature-search/SKILL.md` 第 28 行的 `enrich-abstracts` 命令之后（代码块之外）加一句：

```markdown
再次补全同一批或扩充后的记录时加 `--reuse <上一次的输出>`（可与 `--output` 相同）：同一 `record_id` 已补到的摘要直接沿用，不再请求；汇总的 `reused` 记沿用条数，不计入 `attempted`。
```

`skills/nsfc-proposal/SKILL.md` 第 3 步第 6 项，「在 `stages.md` 记录这一偏离及原因。」之后另起一段（三个空格缩进，与本项其他段落一致）：

```markdown
   补检后重新挑选、再次补全摘要时，命令加 `--reuse T/nsfc-proposal/output/selected_enriched.jsonl`（与 `--output` 相同即可，脚本先读旧文件再覆盖）：同一 `record_id` 上一次已补到的摘要直接沿用，不再请求。汇总的 `reused` 是沿用条数，不计入 `attempted`；判断「低于一半」时也不计入。不手工合并两次运行的结果。在 `stages.md` 记下 `reused` 条数。
```

- [ ] **Step 6: CHANGELOG**

`skills/research-literature-search/CHANGELOG.md` `## [1.1.0]` 段 `### Added（新增）` 末尾加：

```markdown
- `enrich-abstracts` 新增 `--reuse`：沿用前次输出中同一 `record_id` 已补到的摘要，不再请求；汇总新增 `reused` 与 `reuse_file`。
```

`skills/nsfc-proposal/CHANGELOG.md` 0.1.0 段 `### Changed（变更）` 末尾、BAC 行之前加：

```markdown
- 第 3 步第 6 项：再次补全摘要时用 `enrich-abstracts --reuse` 沿用前次结果，不手工合并（来源：fresh-1 验证运行）。
```

根 `CHANGELOG.md` `[Unreleased]` 末尾加：

```markdown
- `research-literature-search` 1.1.0：`enrich-abstracts` 新增 `--reuse`，沿用前次补到的摘要；nsfc-proposal 第 3 步第 6 项改用它。
```

- [ ] **Step 7: 全量测试并提交**

Run: 全局测试命令。Expected: 418 passed。

```bash
git add skills/research-literature-search/scripts/search_runner.py skills/research-literature-search/SKILL.md skills/research-literature-search/CHANGELOG.md skills/nsfc-proposal/SKILL.md skills/nsfc-proposal/CHANGELOG.md CHANGELOG.md tests/research-literature-search/test_rls_enrich_abstracts.py
git commit -m "feat(research-literature-search): enrich-abstracts 沿用前次补到的摘要" -m "Co-Authored-By: <实际模型> <noreply@anthropic.com>"
```

---

### Task 6: 篇幅下限下调

`nsfc-proposal/config.yaml` 的 `length_budget_source` 指向 `../nsfc-length-aligner/config.yaml`，那里是各章篇幅的唯一来源；`section_plan.yaml` 与各信息表的「篇幅：min–max 字」都取自那里，`check_length.py` 也按它报告。只在这一处改数，再同步写了这些数字的说明文档。

新区间（cjk_chars）：

| 章节 | 原区间 | 新区间 |
|---|---|---|
| 立项依据 | 8000–10000 | 4500–10000 |
| 研究内容 | 12000–15000 | 7000–15000 |
| 研究基础 | 5000–6000 | 不变 |
| 合计 | 25000–31000 | 18000–31000 |

上限与页数上限（28/30 页）不变。

**Files:**
- Modify: `skills/nsfc-length-aligner/config.yaml`（`length_standard.overall` 与两个 `files` 条目）
- Modify: `skills/nsfc-length-aligner/SKILL.md`（第 46 行）
- Modify: `skills/nsfc-length-aligner/CHANGELOG.md`（`## [Unreleased]` 的 `### Changed`）
- Modify: `skills/nsfc-research-content-writer/SKILL.md`（第 58 行）、`references/page_budget.md`（第 7 行）、`README.md`（第 26、34 行）
- Modify: `skills/nsfc-research-content-writer/CHANGELOG.md`（`## [1.1.0]` 段，BAC 行之前）
- Modify: `tests/nsfc-proposal/test_np_init.py`（第 56 行）、`tests/nsfc-proposal/test_np_render.py`（第 56 行）
- Modify: 根 `CHANGELOG.md`

**Interfaces:**
- Produces: `case.load_length_budgets()` 读到的 `立项依据` 为 `{"min": 4500, "max": 10000}`，`研究内容` 为 `{"min": 7000, "max": 15000}`。

- [ ] **Step 1: 改测试（先失败）**

`tests/nsfc-proposal/test_np_init.py` 第 56 行改为：

```python
        self.assertEqual(files["extraTex/1.1.立项依据.tex"]["length"], {"min": 4500, "max": 10000, "unit": "cjk_chars"})
        self.assertEqual(files["extraTex/2.1.研究内容.tex"]["length"], {"min": 7000, "max": 15000, "unit": "cjk_chars"})
```

（第二行加在第一行之后。）

`tests/nsfc-proposal/test_np_render.py` 第 56 行的 `"8000–10000"` 改为 `"4500–10000"`。

Run: `PYTHONPYCACHEPREFIX=.bensz-api/pycache python3 -m pytest -q -p no:cacheprovider tests/nsfc-proposal/test_np_init.py tests/nsfc-proposal/test_np_render.py`
Expected: 2 failed。

- [ ] **Step 2: 改 nsfc-length-aligner/config.yaml**

`overall` 段改为（注释的第二行同改）：

```yaml
  overall:
    # 合计口径（面上/青基 C 类）：
    # - 合计约 18000–31000 字（2026-10 随各章下限下调；建议与页数联动校对：总页数≤28）
    # 注意：这里的“字”是写作口径；脚本的 cjk_chars 只统计中日韩统一表意文字，英文/数字/标点会被低估。
    min: 18000
    max: 31000
    notes: "合计约 18000–31000 字；建议总页数≤28 留缓冲。请按当年指南/模板校对。"
```

`立项依据` 条目：

```yaml
    - name: "立项依据"
      match: "*立项依据*.tex"
      min: 4500
      max: 10000
      notes: "约 4500–10000 字：穿透式，不铺陈；聚焦 Gap/Key Idea/价值论证。下限于 2026-10 按试写与评测下调，只作提示；证据不足时不凑字。"
```

`研究内容` 条目：

```yaml
    - name: "研究内容"
      match: "*研究内容*.tex"
      min: 7000
      max: 15000
      notes: "约 7000–15000 字（图表多时取低值）：绝对核心；逻辑框架 + 关键设计 + 图表表达；应提炼创新点与年度计划（如把创新/计划拆到独立文件，请从本预算中等额扣除，保持总量不变）。下限于 2026-10 按试写与评测下调，只作提示。"
```

- [ ] **Step 3: 同步说明文档**

`skills/nsfc-length-aligner/SKILL.md` 第 46 行整行替换为：

```markdown
- 本仓库默认的分章区间（面上/青基 C 类，供校对用）：立项依据约 4500–10000 字 / 研究内容约 7000–15000 字（图表多时取低值）/ 研究基础约 5000–6000 字；合计建议 ≤28 页留缓冲（原则上不超过 30 页）。下限于 2026-10 按试写与评测下调，只作提示：证据或材料不足时不凑字
```

`skills/nsfc-research-content-writer/SKILL.md` 第 58 行改为：

```markdown
     - 推荐字数：7000–15000 字（纯文字部分；图表多时取低值）
```

`skills/nsfc-research-content-writer/references/page_budget.md` 第 7 行改为：

```markdown
- **研究内容推荐字数**：7000–15000 字（纯文字部分；图表多时取低值）
```

`skills/nsfc-research-content-writer/README.md` 第 26 行中的「纯文字约 12000–15000 字」改为「纯文字约 7000–15000 字」；第 34 行改为：

```markdown
- 研究内容推荐字数：7000–15000 字（纯文字部分；图表多时取低值）
```

改完后在仓库根目录运行 `git grep -n "12000–15000\|8000–10000\|25000–31000" -- skills`，应无输出。

- [ ] **Step 4: CHANGELOG**

`skills/nsfc-length-aligner/CHANGELOG.md` `## [Unreleased]` 的 `### Changed` 末尾加：

```markdown
- 下调字数下限：立项依据 8000→4500、研究内容 12000→7000、合计 25000→18000（cjk_chars）；上限与页数上限不变。依据 2026-10 的试写与评测：获资助稿件与试写稿的这两章都低于原下限。
```

`skills/nsfc-research-content-writer/CHANGELOG.md` `## [1.1.0]` 段末尾、BAC 行之前加：

```markdown
- 研究内容推荐字数改为 7000–15000 字，与 nsfc-length-aligner 的预算一致。
```

根 `CHANGELOG.md` `[Unreleased]` 末尾加：

```markdown
- `nsfc-length-aligner`：立项依据与研究内容的字数下限下调为 4500、7000，合计下限 18000；`nsfc-research-content-writer` 推荐字数同步。
```

- [ ] **Step 5: 全量测试并提交**

Run: 全局测试命令。Expected: 418 passed（本任务只改断言，不增加测试数）。

```bash
git add skills/nsfc-length-aligner/config.yaml skills/nsfc-length-aligner/SKILL.md skills/nsfc-length-aligner/CHANGELOG.md skills/nsfc-research-content-writer/SKILL.md skills/nsfc-research-content-writer/references/page_budget.md skills/nsfc-research-content-writer/README.md skills/nsfc-research-content-writer/CHANGELOG.md tests/nsfc-proposal/test_np_init.py tests/nsfc-proposal/test_np_render.py CHANGELOG.md
git commit -m "chore(nsfc-length-aligner): 下调立项依据与研究内容的字数下限" -m "Co-Authored-By: <实际模型> <noreply@anthropic.com>"
```

---

### Task 7: 在 fresh-1 副本上验证（控制者执行，不改代码）

不重跑整份申请书。在评测目录复制 fresh-1 的项目为 `fresh-1-r4`，在副本上检查：

1. `bib_refresh.py` 刷新 8 条含 `\&amp;` 的条目：`refreshed` 8；`.bib` 中搜不到 `amp;`；`citation_ledger.py audit` 两节为 0；`consistency_check.py --json` 为 0/0。CrossRef 请求不带身份信息。
2. 把 1.1 中改写成「一成至两成」的那一句恢复为「10\%至20\%」：`consistency_check.py` 的 needs_review 仍为 0。
3. 用 fresh-1 保存的两次补摘要结果，离线（fetchers 全部返回空）运行 `enrich_abstracts(..., reuse_path=第一次的输出)`：`reused` 不少于子代理手工并入的 14 条，且并入的 14 个 `record_id` 都在其中。
4. `check_length.py` 按新预算：立项依据 7944、研究内容 7984 都在区间内。
5. `coach --out` 指向不存在的目录：退出码 0。

结果写进评测目录 `funded-comparison.md` 新的一节，并更新 `DELIVERY-2026-10-10.md` 与 `REPORT.md`。
