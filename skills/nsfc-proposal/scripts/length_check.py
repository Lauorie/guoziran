#!/usr/bin/env python3
"""国自然申请书篇幅检查：按文件、章节统计可见字数，对照 config.yaml 的 length_standard 预算，可选统计 PDF 页数。"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from length_tex import (
    collect_included_files,
    count_all_units,
    count_unit,
    detect_main_tex,
    iter_input_files,
    md_visible_text,
    read_text,
    split_tex_sections,
    tex_visible_text,
)
from proposal_common import SKILL_ROOT, ProposalError, load_config

TEMPLATE_PATH = SKILL_ROOT / "assets" / "length_report_template.md"


@dataclass(frozen=True)
class _Budget:
    name: str
    match: str
    target: int | None
    min_value: int | None
    max_value: int | None
    notes: str | None

    def bounds(self, *, tolerance_ratio: float) -> tuple[int | None, int | None]:
        if self.min_value is not None or self.max_value is not None:
            return self.min_value, self.max_value
        if self.target is None:
            return None, None
        delta = max(1, int(round(self.target * tolerance_ratio)))
        return self.target - delta, self.target + delta


def _load_budgets(
    cfg: dict[str, Any],
) -> tuple[str, float, dict[str, Any], dict[str, Any], list[_Budget]]:
    std = cfg.get("length_standard") or {}
    if not isinstance(std, dict):
        raise ProposalError("config.yaml 的 length_standard 必须是映射")
    unit = str(std.get("unit") or "cjk_chars")
    tolerance_ratio = float(std.get("tolerance_ratio") or 0.08)
    overall = std.get("overall") or {}
    if not isinstance(overall, dict):
        overall = {}
    pages = std.get("pages") or {}
    if not isinstance(pages, dict):
        pages = {}
    file_rules_raw = std.get("files") or []
    if not isinstance(file_rules_raw, list):
        raise ProposalError("config.yaml 的 length_standard.files 必须是列表")
    budgets: list[_Budget] = []
    for item in file_rules_raw:
        if not isinstance(item, dict):
            continue
        budgets.append(
            _Budget(
                name=str(item.get("name") or item.get("match") or "unknown"),
                match=str(item.get("match") or ""),
                target=int(item["target"]) if "target" in item and item["target"] is not None else None,
                min_value=int(item["min"]) if "min" in item and item["min"] is not None else None,
                max_value=int(item["max"]) if "max" in item and item["max"] is not None else None,
                notes=str(item.get("notes")) if item.get("notes") else None,
            )
        )
    return unit, tolerance_ratio, overall, pages, budgets


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


def _count_pdf_pages(pdf_path: Path) -> int | None:
    # Best-effort page counting:
    # - Prefer pure-Python libraries if installed.
    # - Fall back to `pdfinfo` if available.
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        pass

    try:
        import PyPDF2  # type: ignore

        reader = PyPDF2.PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        pass

    try:
        cp = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if cp.returncode == 0 and cp.stdout:
            for line in cp.stdout.splitlines():
                if line.lower().startswith("pages:"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        return _to_int(parts[1].strip())
    except Exception:
        pass
    return None


def _pick_budget(rel_path: str, budgets: list[_Budget]) -> _Budget | None:
    for b in budgets:
        if not b.match:
            continue
        if fnmatch.fnmatch(rel_path, b.match) or fnmatch.fnmatch(Path(rel_path).name, b.match):
            return b
    return None


def _render_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    out: list[str] = []
    for idx, row in enumerate(rows):
        out.append("| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |")
        if idx == 0:
            out.append("| " + " | ".join("-" * widths[i] for i in range(len(widths))) + " |")
    return "\n".join(out)


def _load_template() -> str:
    if not TEMPLATE_PATH.exists():
        return "# 篇幅对齐报告\n\n（未找到模板）\n"
    return read_text(TEMPLATE_PATH)


def _render_template(text: str, values: dict[str, str]) -> str:
    rendered = text
    for k, v in values.items():
        rendered = rendered.replace(f"{{{{{k}}}}}", v)
    return rendered


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="NSFC proposal length checker (file/section budgets)")
    parser.add_argument("--input", required=True, help="Path to proposal dir or a single file")
    parser.add_argument(
        "--pdf",
        default="",
        help="Optional PDF to count pages for (page limit is a hard constraint in 2026+ templates)",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="报告输出目录（必填）；相对路径按当前工作目录解析",
    )
    parser.add_argument(
        "--fail-if-exists",
        action="store_true",
        help="Fail if report files already exist (prevents accidental overwrite)",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"error: input not found: {input_path}", file=sys.stderr)
        return 2

    try:
        cfg = load_config()
        unit, tolerance_ratio, overall, pages_cfg, budgets = _load_budgets(cfg)
        count_unit("x", unit)
    except ProposalError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    checker = cfg.get("length_checker") or {}
    if not isinstance(checker, dict):
        checker = {}
    include_globs = [str(x) for x in (checker.get("include_globs") or ["*.tex", "*.md"])]
    exclude_globs = [str(x) for x in (checker.get("exclude_globs") or [])]
    latex_cfg = checker.get("latex") or {}
    if not isinstance(latex_cfg, dict):
        latex_cfg = {}
    follow_inputs_raw = latex_cfg.get("follow_inputs", "auto")
    follow_inputs: str | bool
    if isinstance(follow_inputs_raw, bool):
        follow_inputs = follow_inputs_raw
    else:
        follow_inputs = str(follow_inputs_raw).strip().lower() if follow_inputs_raw is not None else "auto"
    section_commands = latex_cfg.get("section_commands") or ["section", "subsection", "subsubsection"]
    if not isinstance(section_commands, list):
        section_commands = ["section", "subsection", "subsubsection"]
    section_commands = [str(x) for x in section_commands]

    discovery: dict[str, Any] = {"mode": "filesystem"}
    base_dir = input_path if input_path.is_dir() else input_path.parent

    files: list[Path] = []
    main_tex: Path | None = None
    if (follow_inputs is True) or (follow_inputs == "auto"):
        main_tex = detect_main_tex(input_path, exclude_globs=exclude_globs)
        if main_tex is not None:
            included = collect_included_files(main_tex)

            def _glob_match(path: str, pattern: str) -> bool:
                if fnmatch.fnmatch(path, pattern):
                    return True
                if pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]):
                    return True
                if pattern.startswith("./") and fnmatch.fnmatch(path, pattern[2:]):
                    return True
                return False

            def _matches_any(path: str, patterns: list[str]) -> bool:
                name = Path(path).name
                return any(_glob_match(path, g) or _glob_match(name, g) for g in patterns)

            filtered: list[Path] = []
            for p in included:
                try:
                    rel = str(p.relative_to(base_dir))
                except Exception:
                    rel = p.name
                if _matches_any(rel, exclude_globs):
                    continue
                if _matches_any(rel, include_globs):
                    filtered.append(p)
            files = filtered
            discovery = {
                "mode": "latex_inputs",
                "main_tex": str(main_tex),
                "included_count": len(included),
                "counted_count": len(files),
            }

    if not files:
        files = list(iter_input_files(input_path, include_globs=include_globs, exclude_globs=exclude_globs))
        discovery = {"mode": "filesystem", "counted_count": len(files)}
    file_results: list[dict[str, Any]] = []
    section_results: list[dict[str, Any]] = []
    unmatched_budget_files: list[str] = []

    total_value = 0
    totals_all = {"cjk_chars": 0, "chars": 0}
    for f in files:
        rel = str(f.relative_to(base_dir))
        raw = read_text(f)

        visible = ""
        sections: list[tuple[str, str]] = []
        if f.suffix.lower() == ".tex":
            visible = tex_visible_text(
                raw,
                strip_math=bool(latex_cfg.get("strip_math", True)),
                strip_commands=bool(latex_cfg.get("strip_commands", True)),
            )
            if bool(latex_cfg.get("split_sections", True)):
                sections = split_tex_sections(
                    raw,
                    commands=section_commands,
                    strip_math=bool(latex_cfg.get("strip_math", True)),
                    strip_commands=bool(latex_cfg.get("strip_commands", True)),
                )
        elif f.suffix.lower() in {".md", ".markdown"}:
            visible = md_visible_text(raw)
        else:
            continue

        all_counts = count_all_units(visible)
        value = all_counts[unit]
        total_value += value
        totals_all["cjk_chars"] += all_counts["cjk_chars"]
        totals_all["chars"] += all_counts["chars"]
        budget = _pick_budget(rel, budgets)
        min_v, max_v = (None, None)
        budget_name = None
        budget_notes = None
        if budget:
            min_v, max_v = budget.bounds(tolerance_ratio=tolerance_ratio)
            budget_name = budget.name
            budget_notes = budget.notes
        else:
            unmatched_budget_files.append(rel)

        file_results.append(
            {
                "path": rel,
                "value": value,
                "unit": unit,
                "values": all_counts,
                "budget": {
                    "name": budget_name,
                    "min": min_v,
                    "max": max_v,
                    "target": budget.target if budget else None,
                    "notes": budget_notes,
                    "match": budget.match if budget else None,
                }
                if budget
                else None,
            }
        )

        if sections:
            for title, seg_raw in sections:
                seg_visible = tex_visible_text(
                    seg_raw,
                    strip_math=bool(latex_cfg.get("strip_math", True)),
                    strip_commands=bool(latex_cfg.get("strip_commands", True)),
                )
                if not seg_visible:
                    continue
                section_results.append(
                    {
                        "file": rel,
                        "section": title,
                        "value": count_unit(seg_visible, unit),
                        "unit": unit,
                    }
                )

    # Overall (text) budget can be expressed as:
    # - min/max (explicit), or
    # - target (+/- tolerance_ratio)
    overall_target = _to_int(overall.get("target"))
    overall_min_cfg = _to_int(overall.get("min"))
    overall_max_cfg = _to_int(overall.get("max"))
    overall_bounds = None
    overall_delta = None
    overall_budget_notes = overall.get("notes")
    overall_min = overall_min_cfg
    overall_max = overall_max_cfg
    if overall_min is None and overall_max is None and overall_target is not None:
        overall_min = overall_target - max(1, int(round(overall_target * tolerance_ratio)))
        overall_max = overall_target + max(1, int(round(overall_target * tolerance_ratio)))
    if overall_min is not None or overall_max is not None or overall_target is not None:
        overall_bounds = {"min": overall_min, "max": overall_max, "target": overall_target, "notes": overall_budget_notes}
        if overall_min is not None and total_value < overall_min:
            overall_delta = f"-{overall_min - total_value}"
        elif overall_max is not None and total_value > overall_max:
            overall_delta = f"+{total_value - overall_max}"
        else:
            overall_delta = "OK"

    # Optional page budget (PDF-based).
    pdf_path = Path(args.pdf).expanduser().resolve() if args.pdf else None
    page_count = None
    pdf_error = None
    if pdf_path:
        if not pdf_path.exists():
            pdf_error = f"pdf not found: {pdf_path}"
        elif pdf_path.suffix.lower() != ".pdf":
            pdf_error = f"not a pdf: {pdf_path}"
        else:
            page_count = _count_pdf_pages(pdf_path)
            if page_count is None:
                pdf_error = "failed to count pages (install `pypdf` or `PyPDF2`, or ensure `pdfinfo` is available)"

    pages_max = _to_int(pages_cfg.get("max"))
    pages_min = _to_int(pages_cfg.get("min"))
    pages_target = _to_int(pages_cfg.get("target"))
    pages_hard_max = _to_int(pages_cfg.get("hard_max"))
    pages_notes = pages_cfg.get("notes")

    # If only target is given, interpret it as "recommended max" by default.
    if pages_max is None and pages_target is not None:
        pages_max = pages_target

    page_delta = None
    if page_count is not None:
        if pages_hard_max is not None and page_count > pages_hard_max:
            page_delta = f"FAIL:+{page_count - pages_hard_max} (over hard_max)"
        elif pages_max is not None and page_count > pages_max:
            page_delta = f"WARN:+{page_count - pages_max} (over max)"
        elif pages_min is not None and page_count < pages_min:
            page_delta = f"-{pages_min - page_count}"
        else:
            page_delta = "OK"

    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "unit": unit,
        "tolerance_ratio": tolerance_ratio,
        "input": str(input_path),
        "discovery": discovery,
        "pdf": {
            "path": str(pdf_path) if pdf_path else None,
            "page_count": page_count,
            "error": pdf_error,
        },
        "file_count": len(file_results),
        "total_value": total_value,
        "total_values": dict(totals_all),
        "overall_budget": {"min": overall_min_cfg, "max": overall_max_cfg, "target": overall_target, "notes": overall_budget_notes},
        "overall_bounds": overall_bounds,
        "overall_delta": overall_delta,
        "page_budget": {"min": pages_min, "max": pages_max, "target": pages_target, "hard_max": pages_hard_max, "notes": pages_notes},
        "page_delta": page_delta,
        "unmatched_budget_files": unmatched_budget_files,
        "files": file_results,
        "sections": section_results,
    }

    out_dir = Path(args.out_dir).expanduser().resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"error: cannot create out dir: {out_dir} ({e})", file=sys.stderr)
        print(
            "提示：请确认 --out-dir 可写，或换一个目录",
            file=sys.stderr,
        )
        return 2
    json_path = out_dir / "length_report.json"
    md_path = out_dir / "length_report.md"

    if args.fail_if_exists and (json_path.exists() or md_path.exists()):
        print(f"error: report already exists (use a different --out-dir): {out_dir}", file=sys.stderr)
        return 2

    try:
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"error: cannot write json report: {json_path} ({e})", file=sys.stderr)
        print(
            "提示：请确认 --out-dir 可写，或换一个目录",
            file=sys.stderr,
        )
        return 2

    table_rows: list[list[str]] = [["文件", unit, "预算(min~max)", "偏差"]]
    for r in file_results:
        b = r.get("budget")
        bounds = "-"
        delta = "-"
        if b and b.get("min") is not None and b.get("max") is not None:
            bounds = f"{b['min']}~{b['max']}"
            if r["value"] < b["min"]:
                delta = f"-{b['min'] - r['value']}"
            elif r["value"] > b["max"]:
                delta = f"+{r['value'] - b['max']}"
            else:
                delta = "OK"
        table_rows.append([str(r["path"]), str(r["value"]), bounds, delta])

    file_table = _render_table(table_rows)

    section_table = ""
    if section_results:
        s_rows: list[list[str]] = [["文件", "章节", unit]]
        for s in section_results:
            s_rows.append([s["file"], s["section"], str(s["value"])])
        section_table = _render_table(s_rows)

    template_text = _load_template()
    overall_bounds_text = "-"
    if overall_bounds and overall_bounds.get("min") is not None and overall_bounds.get("max") is not None:
        overall_bounds_text = f"{overall_bounds['min']}~{overall_bounds['max']}"
    unmatched_text = "（无）"
    if unmatched_budget_files:
        unmatched_text = ", ".join(unmatched_budget_files[:20])
        if len(unmatched_budget_files) > 20:
            unmatched_text += f" ... (+{len(unmatched_budget_files) - 20})"
    md = _render_template(
        template_text,
        {
            "generated_at": report["generated_at"],
            "unit": unit,
            "file_count": str(len(file_results)),
            "discovery_mode": str((report.get("discovery") or {}).get("mode") or "-"),
            "main_tex": str((report.get("discovery") or {}).get("main_tex") or "-"),
            "total_value": str(total_value),
            "total_cjk_chars": str(totals_all["cjk_chars"]),
            "total_chars": str(totals_all["chars"]),
            "overall_budget": str(overall_target) if overall_target is not None else "-",
            "overall_bounds": overall_bounds_text,
            "overall_delta": str(overall_delta) if overall_delta is not None else "-",
            "pdf_path": str(pdf_path) if pdf_path else "-",
            "page_count": str(page_count) if page_count is not None else "-",
            "page_budget_max": str(pages_max) if pages_max is not None else "-",
            "page_budget_hard_max": str(pages_hard_max) if pages_hard_max is not None else "-",
            "page_delta": str(page_delta) if page_delta is not None else "-",
            "page_notes": str(pages_notes) if pages_notes else "-",
            "unmatched_files": unmatched_text,
            "file_table": file_table or "（无）",
            "section_table": section_table or "（未启用或无可解析章节）",
        },
    )
    try:
        md_path.write_text(md, encoding="utf-8")
    except OSError as e:
        print(f"error: cannot write md report: {md_path} ({e})", file=sys.stderr)
        print(
            "提示：请确认 --out-dir 可写，或换一个目录",
            file=sys.stderr,
        )
        return 2

    print(f"OK: total {unit}={total_value} files={len(file_results)}")
    if page_count is not None:
        print(f"- pdf pages: {page_count} (delta={page_delta or '-'})")
    elif pdf_path and pdf_error:
        print(f"- pdf pages: - ({pdf_error})")
    print(f"- json: {json_path}")
    print(f"- md:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
