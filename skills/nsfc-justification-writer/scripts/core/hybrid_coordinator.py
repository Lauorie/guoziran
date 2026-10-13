#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .ai_integration import AIIntegration
from .config_access import get_bool, get_mapping, get_str
from .config_loader import get_cache_dir, get_runs_dir, load_config
from .diagnostic import DiagnosticReport, format_tier1, run_tier1
from .errors import MissingCitationKeysError, SectionNotFoundError, TargetFileNotFoundError, TargetResolutionError
from .editor import ApplyResult, apply_new_content
from .example_matcher import recommend_examples_markdown
from .io_utils import read_text_streaming
from .latex_parser import match_title_via_ai, replace_subsubsection_body_hybrid, suggest_titles
from .observability import Observability, ensure_run_dir, make_run_id
from .reference_validator import check_citations
from .security import build_write_policy, choose_target_relpath, discover_target_candidates, resolve_target_path, validate_write_target, validate_target_file
from .wordcount import count_cjk_chars, describe_word_count_mode
from .review_advice import generate_review_markdown
from .writing_coach import coach_markdown
from .quality_gate import check_new_body_quality
from .word_target import resolve_word_target


@dataclass(frozen=True)
class CoordinatorPaths:
    skill_root: Path
    runs_root: Path


class HybridCoordinator:
    def __init__(
        self,
        *,
        skill_root: Path,
        config: Optional[Dict[str, Any]] = None,
        ai_integration: Optional[AIIntegration] = None,
        observability: Optional[Observability] = None,
    ) -> None:
        self.skill_root = Path(skill_root).resolve()
        self.config = config or load_config(self.skill_root)
        ai_cfg = get_mapping(self.config, "ai")
        self.ai = ai_integration or AIIntegration(enable_ai=get_bool(ai_cfg, "enabled", True), config=self.config)
        self.obs = observability or Observability()
        self.paths = CoordinatorPaths(skill_root=self.skill_root, runs_root=get_runs_dir(self.skill_root, self.config))

    def _target_relpath(self, project_root: Optional[Path] = None) -> str:
        targets = get_mapping(self.config, "targets")
        configured = get_str(targets, "justification_tex", "").strip()
        if configured:
            return configured
        if project_root is not None:
            candidates = discover_target_candidates(project_root)
            return choose_target_relpath(project_root, candidates)
        return "extraTex/1.1.立项依据.tex"

    def _resolve_target(self, project_root: Path) -> Path:
        return validate_target_file(
            project_root=project_root,
            target_path=resolve_target_path(project_root, self._target_relpath(project_root)),
            require_exists=False,
        )

    def target_path(self, *, project_root: Path) -> Path:
        return self._resolve_target(Path(project_root).resolve())

    def diagnose(
        self,
        *,
        project_root: Path,
        include_tier2: bool = True,
    ) -> DiagnosticReport:
        project_root = Path(project_root).resolve()
        target = self._resolve_target(project_root)
        tex = read_text_streaming(target).text if target.exists() else ""
        info_form_text = ""
        for candidate in [
            project_root / "info_form.md",
            project_root / "references" / "info_form.md",
        ]:
            if candidate.exists():
                try:
                    info_form_text = candidate.read_text(encoding="utf-8", errors="ignore")
                    break
                except (OSError, UnicodeError):
                    continue
        word_spec = resolve_word_target(config=self.config, user_intent_text="", info_form_text=info_form_text)
        tier1 = run_tier1(tex_text=tex, project_root=project_root, config=self.config)
        report = DiagnosticReport(
            tier1=tier1,
            tier2=None,
            word_target={"target": word_spec.target, "tolerance": word_spec.tolerance, "source": word_spec.source, "evidence": word_spec.evidence},
            notes=[],
        )
        self.obs.add("diagnose.tier1", **report.to_dict()["tier1"])

        ai_cfg = get_mapping(self.config, "ai")
        cache_dir = get_cache_dir(self.skill_root, self.config)

        report.notes.append(
            "Tier1 已完成；Tier2 必须由当前宿主 AI 读取 references/tier2_semantic_review.md 后直接执行。"
        )
        return report

    def format_diagnose(self, report: DiagnosticReport) -> str:
        out = ["诊断结果：", format_tier1(report.tier1).rstrip()]
        if report.word_target:
            tgt = report.word_target
            src = tgt.get("source", "")
            ev = tgt.get("evidence", "")
            out.append(f"- 🎯 目标字数：{tgt.get('target')}（容差 ±{tgt.get('tolerance')}，来源：{src}{'，线索：'+ev if ev else ''}）")
        if report.tier2:
            out.append("")
            out.append("Tier2（AI 语义分析）：")
            for k in ["logic", "terminology", "evidence", "readability", "suggestions"]:
                v = report.tier2.get(k) if isinstance(report.tier2, dict) else None
                if not v:
                    continue
                out.append(f"- {k}:")
                if isinstance(v, list):
                    for item in v[:10]:
                        out.append(f"  - {item}")
                else:
                    out.append(f"  - {v}")
        if report.notes:
            out.append("")
            out.append("备注：")
            for n in report.notes:
                out.append(f"- {n}")
        return "\n".join(out).strip() + "\n"

    def apply_section_body(
        self,
        *,
        project_root: Path,
        title: str,
        new_body: str,
        backup: bool = True,
        run_id: Optional[str] = None,
        allow_missing_citations: bool = False,
        strict_quality: bool = False,
    ) -> ApplyResult:
        project_root = Path(project_root).resolve()
        target = self._resolve_target(project_root)
        policy = build_write_policy(self.config)
        validate_write_target(project_root=project_root, target_path=target, policy=policy)
        if not target.exists():
            raise TargetFileNotFoundError(target_relpath=self._target_relpath(project_root), project_root=str(project_root))

        src = read_text_streaming(target).text
        structure_cfg = get_mapping(self.config, "structure")
        strict = get_bool(structure_cfg, "strict_title_match", True)
        try:
            min_sim = float(structure_cfg.get("min_title_similarity", 0.6))
        except (TypeError, ValueError):
            min_sim = 0.6

        # strict=False 时：先做“候选标题提示”，并在 AI 可用时尝试语义匹配
        chosen = title
        if not strict:
            cands = suggest_titles(src, query=title, limit=30)
            if self.ai.is_available() and cands:
                ai_cfg = get_mapping(self.config, "ai")
                cache_dir = get_cache_dir(self.skill_root, self.config)
                matched = asyncio.run(match_title_via_ai(query=title, candidates=cands, ai=self.ai, cache_dir=cache_dir))
                if matched:
                    chosen = matched

        new_text, changed, matched_title = replace_subsubsection_body_hybrid(
            src,
            title=chosen,
            new_body=new_body,
            strict=strict,
            min_similarity=min_sim,
        )
        if not changed:
            raise SectionNotFoundError(title=title, suggestions=suggest_titles(src, query=title, limit=12))

        ref_cfg = get_mapping(self.config, "references")
        allow_missing = get_bool(ref_cfg, "allow_missing_citations", False) or bool(allow_missing_citations)

        quality_cfg = get_mapping(self.config, "quality")
        strict_on_apply = get_bool(quality_cfg, "strict_on_apply", False) or bool(strict_quality)
        if strict_on_apply:
            qr = check_new_body_quality(new_body=new_body, config=self.config)
            if not qr.ok:
                from .errors import QualityGateError

                raise QualityGateError(avoid_commands=qr.avoid_commands_hits)

        if not allow_missing:
            targets = get_mapping(self.config, "targets")
            bib_globs = targets.get("bib_globs", ["references/*.bib"])
            cite_result = check_citations(tex_text=new_text, project_root=project_root, bib_globs=bib_globs)
            if cite_result.missing_keys:
                raise MissingCitationKeysError(cite_result.missing_keys)

        run_id = run_id or make_run_id("apply")
        run_dir = ensure_run_dir(self.paths.runs_root, run_id)
        backup_root = (run_dir / "backup").resolve() if backup else None
        try:
            rel = target.relative_to(project_root).as_posix()
        except ValueError:
            rel = self._target_relpath(project_root)
        result = apply_new_content(
            target_path=target,
            new_text=new_text,
            backup_root=backup_root,
            run_id=run_id,
            target_relpath=rel,
        )
        self.obs.add("apply.section", title=str(matched_title or title), changed=result.changed)
        if result.backup_path:
            self.obs.add("apply.backup", path=str(result.backup_path))
        return result

    def word_count_status(
        self,
        *,
        project_root: Path,
        mode: Optional[str] = None,
        info_form_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        project_root = Path(project_root).resolve()
        target = self._resolve_target(project_root)
        tex = read_text_streaming(target).text if target.exists() else ""
        wc_cfg = get_mapping(self.config, "word_count")
        used_mode = str(mode or wc_cfg.get("mode", "cjk_only")).strip() or "cjk_only"
        current = count_cjk_chars(tex, mode=used_mode).cjk_count

        info_form_text = ""
        candidates = [
            project_root / "info_form.md",
            project_root / "references" / "info_form.md",
        ]
        if info_form_path is not None:
            candidates.insert(0, Path(info_form_path))
        for candidate in candidates:
            if candidate.exists():
                try:
                    info_form_text = candidate.read_text(encoding="utf-8", errors="ignore")
                    break
                except (OSError, UnicodeError):
                    continue

        word_spec = resolve_word_target(
            config=self.config,
            user_intent_text="",
            info_form_text=info_form_text,
        )
        target_n = int(word_spec.target)
        tol = int(word_spec.tolerance)
        status = "within_tolerance" if abs(current - target_n) <= tol else ("need_expand" if current < target_n else "need_compress")
        self.obs.add("wordcount", current=current, target=target_n, tolerance=tol, status=status)
        return {
            "current": current,
            "mode": used_mode,
            "mode_definition": describe_word_count_mode(used_mode),
            "target": target_n,
            "tolerance": tol,
            "source": word_spec.source,
            "evidence": word_spec.evidence,
            "status": status,
            "delta": current - target_n,
        }

    def recommend_examples(self, *, query: str, top_k: int = 3) -> str:
        ai_cfg = get_mapping(self.config, "ai")
        cache_dir = get_cache_dir(self.skill_root, self.config)
        return recommend_examples_markdown(skill_root=self.skill_root, query=query, top_k=top_k, ai=self.ai, cache_dir=cache_dir)

    def coach(self, *, project_root: Path, stage: str = "auto", info_form_text: str = "") -> str:
        return asyncio.run(
            coach_markdown(
                skill_root=self.skill_root,
                project_root=Path(project_root),
                config=self.config,
                stage=stage,  # type: ignore[arg-type]
                info_form_text=info_form_text,
                ai=self.ai,
            )
        )

    def reviewer_advice(
        self,
        *,
        project_root: Path,
        include_tier2: bool = True,
    ) -> str:
        project_root = Path(project_root).resolve()
        target = self._resolve_target(project_root)
        tex = read_text_streaming(target).text if target.exists() else ""
        report = self.diagnose(
            project_root=project_root,
            include_tier2=include_tier2,
        )
        return asyncio.run(
            generate_review_markdown(
                skill_root=self.skill_root,
                config=self.config,
                report=report,
                tex_text=tex,
                ai=self.ai,
            )
        )
