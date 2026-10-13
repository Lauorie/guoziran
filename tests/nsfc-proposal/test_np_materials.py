from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))

import material_text  # noqa: E402
import materials  # noqa: E402
import wisdoc_client  # noqa: E402
from material_text import LocalText, coverage, sentence_key  # noqa: E402

try:
    import fitz  # type: ignore[import-not-found]
except ImportError:
    fitz = None

FAKE_URL = "http://wisdoc-secret.invalid:8123"
SENTENCES = [f"第{i}项：本研究拟建立肺磨玻璃结节浸润性预测模型，样本来自第{i}家医院的回顾性队列。" for i in range(10)]
LOCAL_TEXT = "\n".join(SENTENCES)
SETTINGS = materials.Settings(min_coverage=0.9, poll_timeout_s=1, poll_interval_s=0, total_timeout_s=30)
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class FakeWisDoc:
    """替换 materials.wisdoc_parse：记录调用，写出 wisdoc.md 与一张图，或抛出给定异常。"""

    def __init__(self, markdown: str = "", exc: BaseException | None = None) -> None:
        self.markdown, self.exc, self.calls = markdown, exc, []

    def __call__(self, pdf: Path, out_dir: Path, *, env_dirs: Any, cwd: Any, no_cache: bool, settings: Any) -> Path:
        self.calls.append({"pdf": pdf, "no_cache": no_cache, "env_dirs": list(env_dirs)})
        if self.exc is not None:
            raise self.exc
        (out_dir / "assets").mkdir(parents=True, exist_ok=True)
        (out_dir / "assets" / "001_fig.png").write_bytes(b"png")
        path = out_dir / "wisdoc.md"
        path.write_text(self.markdown, encoding="utf-8")
        return path


def make_docx(path: Path, paragraph: str, rows: list[tuple[str, str]]) -> None:
    def cell(text: str) -> str:
        return f"<w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>"
    table = "".join(f"<w:tr>{cell(a)}{cell(b)}</w:tr>" for a, b in rows)
    grid = '<w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid>'
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}"><w:body>'
                f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p><w:tbl>{grid}{table}</w:tbl></w:body></w:document>")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'))
        archive.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>'))
        archive.writestr("word/document.xml", document)


class MaterialsBase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / "proj"
        self.root.mkdir()
        self.inputs = self.base / "inputs"
        self.inputs.mkdir()
        self.task = self.base / ".bensz-api" / "task-20261010-1200-test"
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("WISDOCRS_BASE_URL", None)
        self.local = LocalText(LOCAL_TEXT, "PyMuPDF", ())
        self._patch(materials, "local_pdf_text", lambda path: self.local)

    def _patch(self, target: Any, name: str, value: Any) -> None:
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_wisdoc(self, markdown: str = "", exc: BaseException | None = None) -> FakeWisDoc:
        fake = FakeWisDoc(markdown, exc)
        self._patch(materials, "wisdoc_parse", fake)
        return fake

    def pdf(self, name: str = "paper.pdf", content: bytes = b"%PDF-1.4 fake") -> Path:
        path = self.inputs / name
        path.write_bytes(content)
        return path

    def run_files(self, *files: Path, **kwargs: Any) -> list[tuple[dict, bool]]:
        return materials.run(self.root, self.task, list(files), cwd=self.base, settings=SETTINGS, **kwargs)

    @property
    def mat(self) -> Path:
        return self.task / "shared" / "materials"

    def index(self) -> dict:
        return json.loads((self.mat / "index.json").read_text(encoding="utf-8"))


class PdfTest(MaterialsBase):
    def test_high_coverage_uses_wisdoc(self) -> None:
        markdown = "# 标题\n\n" + "\n\n".join(SENTENCES) + "\n\n![图 1](assets/001_fig.png)\n\n<table><tr><td>AUC</td><td>0.81</td></tr></table>\n"
        fake = self.fake_wisdoc(markdown)
        [(entry, cached)] = self.run_files(self.pdf())
        self.assertFalse(cached)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["env_dirs"], [self.root.resolve()])
        self.assertEqual((entry["parser"], entry["primary"], entry["wisdoc_md"], entry["local_txt"]),
                         ("wisdoc", "01-paper/wisdoc.md", "01-paper/wisdoc.md", "01-paper/local.txt"))
        self.assertEqual(entry["coverage"], 1.0)
        self.assertEqual(entry["warnings"], [])
        self.assertEqual(entry["chars"], len(markdown))
        self.assertEqual(entry["assets"], 1)
        self.assertTrue((self.mat / "01-paper" / "assets" / "001_fig.png").is_file())
        self.assertEqual(self.index()["schema"], "nsfc-proposal.materials.v1")
        self.assertEqual(self.index()["files"], [entry])

    def test_low_coverage_falls_back_to_local_text(self) -> None:
        kept = SENTENCES[:5] + [s[:6] + "机密" + s[6:] for s in SENTENCES[5:7]]
        self.fake_wisdoc("\n\n".join(kept))
        [(entry, _)] = self.run_files(self.pdf())
        self.assertEqual(entry["parser"], "wisdoc")
        self.assertEqual(entry["primary"], "01-paper/local.txt")
        self.assertEqual(entry["wisdoc_md"], "01-paper/wisdoc.md")
        self.assertEqual(entry["coverage"], 0.5)
        self.assertIn("WisDoc 漏字（覆盖率 50%），正文以 local.txt 为准，表格与图看 wisdoc.md", entry["warnings"])

    def test_wisdoc_error_falls_back_without_leaking_url(self) -> None:
        os.environ["WISDOCRS_BASE_URL"] = FAKE_URL
        self.fake_wisdoc(exc=wisdoc_client.WisDocHTTPError(502, f"HTTP 502: bad gateway at {FAKE_URL}/api/v2/documents"))
        with self.assertLogs("materials", level="WARNING") as logs:
            [(entry, _)] = self.run_files(self.pdf())
        self.assertEqual((entry["parser"], entry["primary"], entry["wisdoc_md"]), ("local", "01-paper/local.txt", None))
        self.assertIn("WisDoc 解析失败（HTTP 错误 502），正文以 local.txt 为准", entry["warnings"])
        self.assertFalse((self.mat / "01-paper" / "wisdoc.md").exists())
        dumped = json.dumps(self.index(), ensure_ascii=False) + materials.summary_line(entry, False) + "\n".join(logs.output)
        self.assertNotIn("wisdoc-secret", dumped)

    def test_timeout_and_connection_errors_are_categorized(self) -> None:
        cases = [(TimeoutError("timed out"), "超时"), (urllib.error.URLError(ConnectionRefusedError(111, "refused")), "连接失败"),
                 (wisdoc_client.WisDocJobFailed("failed"), "解析任务失败")]
        for exc, label in cases:
            self.assertEqual(materials.failure_category(exc), label)

    def test_missing_base_url_falls_back_without_network(self) -> None:
        self._patch(wisdoc_client, "SKILL_DIR", self.base / "skill")
        opener = mock.Mock(side_effect=AssertionError("不应联网"))
        self._patch(wisdoc_client, "_make_opener", opener)
        [(entry, _)] = self.run_files(self.pdf())
        opener.assert_not_called()
        self.assertEqual((entry["parser"], entry["primary"]), ("local", "01-paper/local.txt"))
        self.assertIn("WisDoc 解析失败（WISDOCRS_BASE_URL 未配置或写法不对），正文以 local.txt 为准", entry["warnings"])

    def test_project_root_and_limits_are_passed_to_client(self) -> None:
        seen: dict[str, Any] = {}

        def fake_parse(**kwargs: Any) -> dict:
            seen.update(kwargs)
            out = Path(kwargs["output_dir"]) / kwargs["markdown_name"]
            out.write_text(LOCAL_TEXT, encoding="utf-8")
            return {"markdown_path": str(out)}

        self._patch(wisdoc_client, "parse_pdf_to_markdown", fake_parse)
        [(entry, _)] = self.run_files(self.pdf())
        self.assertEqual((list(seen["env_dirs"]), seen["cwd"]), ([self.root.resolve()], self.base))
        self.assertEqual((seen["poll_timeout_s"], seen["poll_interval_s"], seen["total_timeout_s"]), (1, 0, 30))
        self.assertEqual((seen["markdown_name"], seen["assets_dirname"]), ("wisdoc.md", "assets"))
        self.assertNotIn("base_url", seen)
        self.assertEqual(entry["parser"], "wisdoc")

    def test_empty_wisdoc_with_local_text_uses_local(self) -> None:
        self.fake_wisdoc("<p></p>\n![图](assets/001_fig.png)\n")
        [(entry, _)] = self.run_files(self.pdf())
        self.assertEqual((entry["parser"], entry["primary"], entry["wisdoc_md"]), ("local", "01-paper/local.txt", None))
        self.assertEqual(entry["warnings"], ["WisDoc 解析失败（返回空），正文以 local.txt 为准"])
        self.assertFalse((self.mat / "01-paper" / "wisdoc.md").exists())

    def test_empty_local_text_uses_wisdoc_with_scan_warning(self) -> None:
        self.local = LocalText("", "PyMuPDF", ())
        self.fake_wisdoc("扫描件里识别出的少量文字。")
        [(entry, _)] = self.run_files(self.pdf())
        self.assertEqual((entry["parser"], entry["primary"], entry["local_txt"]), ("wisdoc", "01-paper/wisdoc.md", None))
        self.assertIn("本机抽不到文字，可能是扫描件，以 WisDoc 结果为准", entry["warnings"])
        self.assertIn("解析结果过短", entry["warnings"])
        self.assertFalse((self.mat / "01-paper" / "local.txt").exists())

    def test_both_empty_gives_no_primary(self) -> None:
        self.local = LocalText("", "PyMuPDF", ())
        self.fake_wisdoc("![图](assets/001_fig.png)\n")
        [(entry, _)] = self.run_files(self.pdf())
        self.assertIsNone(entry["primary"])
        self.assertIn("WisDoc 解析失败（返回空）", entry["warnings"])
        self.assertIn("未取得文字", entry["warnings"])
        self.assertFalse((self.mat / "01-paper" / "assets").exists())

    def test_local_only_never_calls_wisdoc(self) -> None:
        fake = self.fake_wisdoc("\n".join(SENTENCES))
        [(entry, _)] = self.run_files(self.pdf(), local_only=True)
        self.assertEqual(fake.calls, [])
        self.assertEqual((entry["parser"], entry["primary"], entry["wisdoc_md"]), ("local", "01-paper/local.txt", None))
        self.assertEqual(entry["warnings"], [])


class CacheTest(MaterialsBase):
    def test_second_run_hits_cache_and_no_cache_reparses(self) -> None:
        fake = self.fake_wisdoc("\n\n".join(SENTENCES))
        pdf = self.pdf()
        self.run_files(pdf)
        [(entry, cached)] = self.run_files(pdf)
        self.assertTrue(cached)
        self.assertEqual(len(fake.calls), 1)
        [(again, cached)] = self.run_files(pdf, no_cache=True)
        self.assertFalse(cached)
        self.assertEqual(len(fake.calls), 2)
        self.assertTrue(fake.calls[-1]["no_cache"])
        self.assertEqual(again["dir"], entry["dir"])
        self.assertEqual(len(self.index()["files"]), 1)

    def test_local_only_does_not_reuse_wisdoc_result(self) -> None:
        fake = self.fake_wisdoc("\n\n".join(SENTENCES))
        pdf = self.pdf()
        self.run_files(pdf)
        [(entry, cached)] = self.run_files(pdf, local_only=True)
        self.assertFalse(cached)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual((entry["parser"], entry["wisdoc_md"]), ("local", None))
        self.assertFalse((self.mat / "01-paper" / "wisdoc.md").exists())

    def test_missing_output_file_invalidates_cache(self) -> None:
        fake = self.fake_wisdoc("\n\n".join(SENTENCES))
        pdf = self.pdf()
        self.run_files(pdf)
        (self.mat / "01-paper" / "local.txt").unlink()
        [(_, cached)] = self.run_files(pdf)
        self.assertFalse(cached)
        self.assertEqual(len(fake.calls), 2)

    def test_missing_assets_dir_invalidates_cache(self) -> None:
        fake = self.fake_wisdoc("\n\n".join(SENTENCES))
        pdf = self.pdf()
        self.run_files(pdf)
        shutil.rmtree(self.mat / "01-paper" / "assets")
        [(entry, cached)] = self.run_files(pdf)
        self.assertFalse(cached)
        self.assertEqual(len(fake.calls), 2)
        self.assertTrue((self.mat / "01-paper" / "assets" / "001_fig.png").is_file())

    def test_unreadable_input_exits_2(self) -> None:
        fake = self.fake_wisdoc("unused")
        self._patch(materials, "_sha256", mock.Mock(side_effect=PermissionError(13, "denied")))
        with mock.patch("sys.stderr", io.StringIO()):
            code = materials.main(["parse", "--project-root", str(self.root), "--task-root", str(self.task), str(self.pdf())])
        self.assertEqual(code, 2)
        self.assertEqual(fake.calls, [])
        self.assertFalse(self.task.exists())

    def test_new_file_gets_next_number(self) -> None:
        self.fake_wisdoc("\n\n".join(SENTENCES))
        self.run_files(self.pdf("a.pdf", b"%PDF a"))
        [(entry, _)] = self.run_files(self.pdf("b 论文(终稿).pdf", b"%PDF b"))
        self.assertEqual(entry["dir"], "02-b_论文_终稿")


class OtherFormatsTest(MaterialsBase):
    def test_docx_without_pandoc_extracts_paragraph_and_table_rows(self) -> None:
        fake = self.fake_wisdoc("unused")
        self._patch(materials, "pandoc_available", lambda: False)
        path = self.inputs / "预实验.docx"
        make_docx(path, "申请人的预实验记录", [("指标", "数值"), ("AUC", "0.81")])
        [(entry, _)] = self.run_files(path)
        self.assertEqual(fake.calls, [])
        self.assertEqual((entry["kind"], entry["parser"], entry["primary"]), ("docx", "docx-xml", "01-预实验/converted.md"))
        text = (self.mat / entry["primary"]).read_text(encoding="utf-8")
        self.assertIn("申请人的预实验记录", text)
        self.assertIn("| 指标 | 数值 |", text)
        self.assertIn("| AUC | 0.81 |", text)
        self.assertIn("本机没有 pandoc，用内置解析抽取段落与表格行", entry["warnings"])

    @unittest.skipUnless(shutil.which("pandoc"), "本机没有 pandoc")
    def test_docx_with_pandoc_keeps_table(self) -> None:
        path = self.inputs / "notes.docx"
        make_docx(path, "申请人的预实验记录", [("指标", "数值"), ("AUC", "0.81")])
        [(entry, _)] = self.run_files(path)
        self.assertEqual(entry["parser"], "pandoc")
        text = (self.mat / entry["primary"]).read_text(encoding="utf-8")
        self.assertIn("申请人的预实验记录", text)
        self.assertRegex(text, r"\|\s*AUC\s*\|\s*0\.81\s*\|")

    def test_md_and_gb18030_txt_are_copied_verbatim(self) -> None:
        md_text = "# 研究基础\n\n已发表论文 3 篇，**样本量** 120 例。\n"
        txt_text = "预实验结果：AUC 0.81，样本量 30 例。\n第二行。\n"
        md = self.inputs / "基础.md"
        md.write_text(md_text, encoding="utf-8")
        txt = self.inputs / "预实验.txt"
        txt.write_bytes(txt_text.encode("gb18030"))
        bom = self.inputs / "bom.txt"
        bom.write_bytes("﻿带 BOM 的文本\n".encode("utf-8"))
        results = self.run_files(md, txt, bom)
        texts = [(self.mat / e["primary"]).read_text(encoding="utf-8") for e, _ in results]
        self.assertEqual(texts, [md_text, txt_text, "带 BOM 的文本\n"])
        self.assertEqual([e["kind"] for e, _ in results], ["md", "txt", "txt"])
        self.assertEqual([e["parser"] for e, _ in results], ["text", "text", "text"])

    def test_unsupported_suffix_is_skipped_others_processed(self) -> None:
        sheet = self.inputs / "数据.xlsx"
        sheet.write_bytes(b"PK fake")
        md = self.inputs / "notes.md"
        md.write_text("正文\n", encoding="utf-8")
        results = self.run_files(sheet, md)
        skipped, kept = results[0][0], results[1][0]
        self.assertEqual((skipped["dir"], skipped["primary"]), (None, None))
        self.assertEqual(skipped["warnings"], ["不支持的文件类型 .xlsx，已跳过"])
        self.assertEqual(kept["primary"], "01-notes/converted.md")
        self.assertEqual([e["source"] for e in self.index()["files"]], ["数据.xlsx", "notes.md"])


class CoverageTest(unittest.TestCase):
    def test_sentence_keys(self) -> None:
        self.assertIsNone(sentence_key("短句子不计入。"))
        self.assertEqual(sentence_key("本研究拟建立肺磨玻璃结节浸润性预测模型并外部验证"), "本研究拟建立肺磨玻璃结节")
        self.assertEqual(sentence_key("In 2020, we built a CT radiomics model for nodules and validated it"),
                         "in2020webuiltactradiomicsmodelfor")

    def test_coverage_ignores_markup_and_counts_distinct_keys(self) -> None:
        local = "\n".join(SENTENCES[:2] + SENTENCES[:2])
        wisdoc = f"<p>{SENTENCES[0]}</p>\n\n![图](a.png)\n\n" + SENTENCES[1].replace("，", "<br>")
        self.assertEqual(coverage(local, wisdoc), 1.0)
        self.assertIsNone(coverage("短。也短。", wisdoc))


@unittest.skipUnless(fitz is not None, "本机没有 PyMuPDF")
class FitzTest(MaterialsBase):
    def make_pdf(self, path: Path) -> None:
        doc = fitz.open()
        page = doc.new_page()
        for i, sentence in enumerate(SENTENCES[:6]):
            page.insert_text((40, 80 + 22 * i), sentence, fontname="china-s", fontsize=10)
        page.insert_text((150, 520), "机密水印禁止外传", fontname="china-s", fontsize=48, morph=(fitz.Point(150, 520), fitz.Matrix(-45)))
        page.insert_text((300, 700), "内部资料请勿复制", fontname="china-s", fontsize=10, morph=(fitz.Point(300, 700), fitz.Matrix(-30)))
        doc.save(str(path))
        doc.close()

    def test_diagonal_watermark_is_dropped_from_local_text(self) -> None:
        path = self.inputs / "watermarked.pdf"
        self.make_pdf(path)
        local = material_text.local_pdf_text(path)
        self.assertEqual(local.backend, "PyMuPDF")
        self.assertIn(SENTENCES[0], local.text)
        self.assertNotIn("水印", local.text)
        self.assertNotIn("内部资料", local.text)

    def test_watermarked_wisdoc_output_loses_to_local_text(self) -> None:
        self._patch(materials, "local_pdf_text", material_text.local_pdf_text)
        path = self.inputs / "watermarked.pdf"
        self.make_pdf(path)
        self.fake_wisdoc("\n\n".join([SENTENCES[0][:5] + "机密" + SENTENCES[0][5:], SENTENCES[1], SENTENCES[2][:4] + "水印" + SENTENCES[2][4:]]))
        [(entry, _)] = self.run_files(path)
        self.assertEqual(entry["primary"], "01-watermarked/local.txt")
        self.assertNotIn("水印", (self.mat / entry["primary"]).read_text(encoding="utf-8"))


class CliTest(unittest.TestCase):
    def _cli(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))
        env.pop("WISDOCRS_BASE_URL", None)
        return subprocess.run([sys.executable, str(SCRIPTS / "materials.py"), "parse", *args], env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=60, cwd=self.tmp)

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.md = Path(tmp.name) / "a.md"
        self.md.write_text("正文\n", encoding="utf-8")

    def test_task_root_outside_bensz_api_task_exits_2(self) -> None:
        for bad in (Path(self.tmp) / "notatask", Path(self.tmp) / "other" / "task-20261010-0000-x"):
            proc = self._cli("--project-root", self.tmp, "--task-root", str(bad), str(self.md))
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertFalse(bad.exists())

    def test_missing_file_exits_2(self) -> None:
        task = Path(self.tmp) / ".bensz-api" / "task-20261010-0000-x"
        proc = self._cli("--project-root", self.tmp, "--task-root", str(task), str(Path(self.tmp) / "missing.pdf"))
        self.assertEqual(proc.returncode, 2)

    def test_parse_prints_one_line_per_file(self) -> None:
        task = Path(self.tmp) / ".bensz-api" / "task-20261010-0000-x"
        proc = self._cli("--project-root", self.tmp, "--task-root", str(task), "--local-only", str(self.md))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("a.md  parser=text  primary=01-a/converted.md  覆盖率=-  警告=0", proc.stdout)
        self.assertTrue((task / "shared" / "materials" / "index.json").is_file())


if __name__ == "__main__":
    unittest.main()
