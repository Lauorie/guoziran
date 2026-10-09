from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/nsfc-proposal/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from citation_ledger import append_event, entry_sha256, load_ledger, register_user_entries  # noqa: E402
from latex_files import bib_entry_texts  # noqa: E402
from proposal_common import ProposalError, proposal_paths  # noqa: E402
from bib_resolve import run  # noqa: E402
from case import init_proposal  # noqa: E402
from test_np_bib_resolve import CROSSREF_ITEM_1, TITLE_1, FakeResponse, FakeSession, doi_url  # noqa: E402
from test_np_init import make_project  # noqa: E402

ENTRY_A = "@article{a2020,\n  title = {Alpha},\n  year = {2020},\n  doi = {10.5555/a},\n}\n"
ENTRY_B = "@book{b2021,\n  title = {Beta},\n}\n"
ABSTRACT = "In a multicenter cohort of test nodules, the model reached an AUC of 0.86 with sensitivity of 95% across centers."


def add(key: str, **extra: object) -> dict:
    return {"event": "add", "bibkey": key, "time": "2026-10-09T10:00:00+08:00", "source": "crossref", "doi": None,
            "entry_sha256": "x", "abstract": None, "provenance": {}, "reason": None, **extra}


def make_ledger_project(base: Path, bib_text: str = ENTRY_A + "\n" + ENTRY_B) -> Path:
    root = base / "proj"
    (root / "references").mkdir(parents=True)
    (root / "main.tex").write_text("\\input{references/reference.tex}\n", encoding="utf-8")
    (root / "references" / "reference.tex").write_text("\\bibliography{references/refs}\n", encoding="utf-8")
    (root / "references" / "refs.bib").write_text(bib_text, encoding="utf-8")
    return root


class LedgerFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "proposal" / "citation_ledger.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_is_empty(self) -> None:
        self.assertEqual(load_ledger(self.path), {})

    def test_drop_invalidates_and_add_restores(self) -> None:
        append_event(self.path, add("k1"))
        append_event(self.path, add("k2"))
        self.assertEqual(set(load_ledger(self.path)), {"k1", "k2"})
        append_event(self.path, {"event": "drop", "bibkey": "k1", "time": "t", "reason": "撤回"})
        self.assertEqual(set(load_ledger(self.path)), {"k2"})
        append_event(self.path, add("k1", doi="10.5555/z"))
        self.assertEqual(load_ledger(self.path)["k1"]["doi"], "10.5555/z")
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 4)

    def test_chinese_is_not_escaped(self) -> None:
        append_event(self.path, {"event": "drop", "bibkey": "k", "time": "t", "reason": "撤回"})
        self.assertIn("撤回", self.path.read_text(encoding="utf-8"))

    def test_bad_line_reports_line_number(self) -> None:
        append_event(self.path, add("k1"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write("{not json\n")
        with self.assertRaises(ProposalError) as ctx:
            load_ledger(self.path)
        self.assertIn("第 2 行", str(ctx.exception))

    def test_unknown_event_reports_line_number(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(add("k1")) + "\n" + json.dumps({"event": "revise", "bibkey": "k1"}) + "\n", encoding="utf-8")
        with self.assertRaises(ProposalError) as ctx:
            load_ledger(self.path)
        self.assertIn("第 2 行", str(ctx.exception))

    def test_append_after_file_without_trailing_newline(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(add("k1")), encoding="utf-8")
        append_event(self.path, add("k2"))
        self.assertEqual(set(load_ledger(self.path)), {"k1", "k2"})


class HashTest(unittest.TestCase):
    def test_insensitive_to_trailing_whitespace_and_crlf(self) -> None:
        crlf = ENTRY_A.replace("\n", "\r\n").replace("2020},", "2020},  ") + "\r\n\r\n"
        self.assertEqual(entry_sha256(ENTRY_A), entry_sha256(crlf))

    def test_sensitive_to_field_content(self) -> None:
        self.assertNotEqual(entry_sha256(ENTRY_A), entry_sha256(ENTRY_A.replace("2020", "2021")))

    def test_bib_entry_texts_skips_non_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bib = Path(tmp) / "x.bib"
            bib.write_text("@comment{note}\n@string{j = {J}}\n" + ENTRY_A + "\n" + ENTRY_B, encoding="utf-8")
            texts = bib_entry_texts([bib])
        self.assertEqual(set(texts), {"a2020", "b2021"})
        self.assertEqual(entry_sha256(texts["a2020"]), entry_sha256(ENTRY_A))
        self.assertNotIn("@book", texts["a2020"])


class RegisterUserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_ledger_project(Path(self.tmp.name))
        self.ledger = proposal_paths(self.root).ledger

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_register_is_idempotent(self) -> None:
        self.assertEqual(register_user_entries(self.root), ["a2020", "b2021"])
        self.assertEqual(register_user_entries(self.root), [])
        rec = load_ledger(self.ledger)["a2020"]
        self.assertEqual((rec["event"], rec["source"], rec["doi"], rec["abstract"]), ("register_user", "user", "10.5555/a", None))
        self.assertEqual(rec["entry_sha256"], entry_sha256(ENTRY_A))
        self.assertEqual(len(self.ledger.read_text(encoding="utf-8").splitlines()), 2)

    def test_dropped_entry_is_not_reregistered(self) -> None:
        register_user_entries(self.root)
        append_event(self.ledger, {"event": "drop", "bibkey": "b2021", "time": "t", "reason": "r"})
        self.assertEqual(register_user_entries(self.root), [])
        self.assertNotIn("b2021", load_ledger(self.ledger))


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_ledger_project(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    ENV = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / ".bensz-api" / "pycache"))

    def _cli(self, *args: str, root: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / "citation_ledger.py"), *args, "--project-root", str(root or self.root)],
                              env=self.ENV, capture_output=True, text=True, timeout=60)

    def test_register_user_show_and_drop(self) -> None:
        self.assertEqual(self._cli("register-user").returncode, 0)
        shown = self._cli("show")
        self.assertIn("a2020\tuser\t10.5555/a\t无摘要", shown.stdout)
        dropped = self._cli("drop", "--key", "a2020", "--reason", "元数据有误")
        self.assertEqual(dropped.returncode, 0, dropped.stderr)
        self.assertIn("从 .bib 中删除", dropped.stdout)
        self.assertIn("bib_resolve", dropped.stdout)
        self.assertNotIn("a2020", self._cli("show").stdout)

    def test_audit_lists_handwritten_and_modified(self) -> None:
        self.assertEqual(self._cli("register-user").returncode, 0)
        self.assertEqual(self._cli("audit").returncode, 0)
        bib = self.root / "references" / "refs.bib"
        bib.write_text(bib.read_text(encoding="utf-8").replace("Alpha", "Alpha, revised") + "\n@article{hand2024,\n  title = {H},\n}\n", encoding="utf-8")
        proc = self._cli("audit")
        self.assertEqual(proc.returncode, 1)
        missing, modified = proc.stdout.split("## 条目文本与台账哈希不一致")
        self.assertIn("hand2024", missing)
        self.assertIn("a2020", modified)
        self.assertNotIn("b2021", proc.stdout)

    def test_errors_exit_2(self) -> None:
        self.assertEqual(self._cli("drop", "--key", "nope", "--reason", "r").returncode, 2)
        self.assertEqual(self._cli("audit", root=Path(self.tmp.name) / "absent").returncode, 2)
        proposal_paths(self.root).ledger.parent.mkdir()
        proposal_paths(self.root).ledger.write_text("oops\n", encoding="utf-8")
        self.assertEqual(self._cli("audit").returncode, 2)


class ResolveLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = make_ledger_project(base, ENTRY_B)
        (self.root / "proposal").mkdir()
        self.task = base / ".bensz-api" / "task-20261009-1200-test"
        self.records = base / "selected.jsonl"
        self.session = FakeSession({doi_url("10.5555/nsfc.test.001"): FakeResponse(200, {"message": CROSSREF_ITEM_1})})
        self.row = {"record_id": "r1", "title": TITLE_1, "year": 2024, "identifiers": {"doi": "10.5555/nsfc.test.001"},
                    "abstract": ABSTRACT, "abstract_status": "present", "query_matches": ["Q-a"],
                    "provenance": {"host_tool": "wispaper"}, "sources": [{"provider": "wispaper-test"}]}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, row: dict, dry_run: bool = False) -> dict:
        self.records.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        return run(self.root, self.records, self.task, session=self.session, dry_run=dry_run)

    def test_added_entry_gets_add_event_with_hash_and_abstract(self) -> None:
        summary = self._run(self.row)
        key = summary["outcomes"][0]["bibkey"]
        ledger = load_ledger(proposal_paths(self.root).ledger)
        rec = ledger[key]
        written = bib_entry_texts([self.root / "references" / "refs.bib"])[key]
        self.assertEqual((rec["event"], rec["source"], rec["doi"]), ("add", "crossref", "10.5555/nsfc.test.001"))
        self.assertEqual(rec["entry_sha256"], entry_sha256(written))
        self.assertEqual(rec["abstract"], ABSTRACT)
        self.assertEqual(rec["provenance"], {"record_id": "r1", "record_title": TITLE_1, "query_matches": ["Q-a"],
                                             "host_tool": "wispaper", "provider": "wispaper-test"})
        self.assertEqual({r["event"] for r in ledger.values()}, {"add"})
        self.assertNotIn("b2021", ledger)

    def test_missing_source_is_recorded_as_null(self) -> None:
        from bib_resolve import Outcome
        from citation_ledger import record_added
        path = proposal_paths(self.root).ledger
        outcome = Outcome("r1", "B", "added", bibkey="b2021", doi=None, source=None)
        record_added(path, [self.root / "references" / "refs.bib"], [{"title": "B"}], [outcome])
        self.assertIsNone(load_ledger(path)["b2021"]["source"])

    def test_short_or_missing_abstract_is_null(self) -> None:
        self._run({**self.row, "abstract": "too short", "provenance": None, "sources": None, "query_matches": None})
        rec = load_ledger(proposal_paths(self.root).ledger)["tester2024peritumoral"]
        self.assertIsNone(rec["abstract"])
        self.assertEqual((rec["provenance"]["host_tool"], rec["provenance"]["provider"], rec["provenance"]["query_matches"]), (None, None, []))

    def test_absent_abstract_status_is_null(self) -> None:
        self._run({**self.row, "abstract_status": "missing"})
        self.assertIsNone(load_ledger(proposal_paths(self.root).ledger)["tester2024peritumoral"]["abstract"])

    def test_dry_run_and_exists_write_nothing(self) -> None:
        self._run(self.row, dry_run=True)
        self.assertFalse(proposal_paths(self.root).ledger.exists())
        self._run(self.row)
        before = proposal_paths(self.root).ledger.read_text(encoding="utf-8")
        self.assertEqual(self._run(self.row)["counts"]["exists"], 1)
        self.assertEqual(proposal_paths(self.root).ledger.read_text(encoding="utf-8"), before)

    def test_unresolved_writes_no_event(self) -> None:
        session = FakeSession({})
        self.records.write_text(json.dumps({"record_id": "r9", "title": "Nonexistent work about nothing in particular at all"}) + "\n", encoding="utf-8")
        run(self.root, self.records, self.task, session=session)
        self.assertFalse(proposal_paths(self.root).ledger.exists())


class InitLedgerTest(unittest.TestCase):
    def test_existing_entries_registered_as_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            (root / "references" / "myexample.bib").write_text(ENTRY_A + "\n" + ENTRY_B, encoding="utf-8")
            result = init_proposal(root, title="T", project_type="青年科学基金")
            ledger = load_ledger(proposal_paths(root).ledger)
            self.assertEqual({k: v["source"] for k, v in ledger.items()}, {"a2020": "user", "b2021": "user"})
            self.assertIn("已有 2 条文献按申请人提供登记", result.warnings)
            again = init_proposal(root, title="T", project_type="青年科学基金")
            self.assertEqual(len(proposal_paths(root).ledger.read_text(encoding="utf-8").splitlines()), 2)
            self.assertFalse([w for w in again.warnings if "登记" in w])

    def test_registration_is_noted_in_assumptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            (root / "references" / "myexample.bib").write_text(ENTRY_A, encoding="utf-8")
            init_proposal(root, title="T", project_type="青年科学基金")
            self.assertIn("已有 1 条文献按申请人提供登记", proposal_paths(root).assumptions.read_text(encoding="utf-8"))

    def test_note_added_when_proposal_dir_exists_without_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            init_proposal(root, title="T", project_type="青年科学基金")
            paths = proposal_paths(root)
            paths.ledger.unlink()
            (root / "references" / "myexample.bib").write_text(ENTRY_A + "\n" + ENTRY_B, encoding="utf-8")
            result = init_proposal(root, title="T", project_type="青年科学基金")
            self.assertIn("已有 2 条文献按申请人提供登记", result.warnings)
            text = paths.assumptions.read_text(encoding="utf-8")
            self.assertEqual(text.count("已有 2 条文献按申请人提供登记"), 1)
            self.assertIn("## 待核实项", text)

    def test_empty_bib_creates_empty_ledger_without_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            result = init_proposal(root, title="T", project_type="青年科学基金")
            self.assertTrue(proposal_paths(root).ledger.is_file())
            self.assertEqual(load_ledger(proposal_paths(root).ledger), {})
            self.assertFalse([w for w in result.warnings if "登记" in w])


if __name__ == "__main__":
    unittest.main()
