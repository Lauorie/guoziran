#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ai_integration import AIIntegration
from .config_access import get_bool, get_mapping, get_str
from .diagnostic import DiagnosticReport
from .prompt_templates import get_prompt
from .style import get_style_mode, style_preamble_text


def _load_dod_checklist(skill_root: Path) -> str:
    p = (Path(skill_root).resolve() / "references" / "dod_checklist.md").resolve()
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore").strip()


def _fallback_review_markdown(*, report: DiagnosticReport, dod_checklist: str, style_mode: str) -> str:
    t1 = report.tier1
    if style_mode == "engineering":
        qs = [
            "你的一句话问题定义是否让“非本细分领域评审”也能理解？",
            "现有方案的 2–4 条不足是否是可验证的（指标/对照/边界条件），而不是口号？",
            "关键技术难点与关键科学问题是否一一映射（避免“堆功能”）？",
            "验证方案是否可复现：数据来源/评价指标/对照设置/统计检验是否明确？",
            "项目切入点是否明确差异化切口 + 可验证指标（而非泛泛“做平台/做系统”）？",
            "是否自然承上启下到用户指定的相关研究内容（而不是戛然而止）？",
            "是否存在不可核验绝对表述（国际领先/国内首次等）？如有，如何改成可验证指标？",
            "引用是否都可追溯（bibkey 存在且来源可核验）？",
            "术语/缩写/指标口径是否与用户指定的相关章节保持一致？",
            "每段能否让大同行顺着“已有事实—缺口—本段结论”读下去？是否有长句层级、指代或缩写界定造成额外负担？",
        ]
    else:
        qs = [
            "你的一句话问题定义是否让“非本细分领域评审”也能理解？",
            "现有方案在理论层面的瓶颈是否是 2–4 条可验证的不足（如假设过强/框架不统一/因果缺失/界不紧），而不是口号？",
            "核心假说是否可证伪，且对应的关键科学问题是否一一映射（指向理论阐明/证明）？",
            "项目切入点是否明确“理论差异化切口 + 验证指标（理论证明/定理/数值验证）”？",
            "是否自然承上启下到用户指定的相关研究内容（而不是戛然而止）？",
            "是否存在不可核验绝对表述（国际领先/国内首次等）？如有，如何改成可验证指标？",
            "引用是否都可追溯（bibkey 存在且来源可核验）？",
            "术语/缩写/指标口径是否与用户指定的相关章节保持一致？",
            "每段能否让大同行顺着“已有事实—缺口—本段结论”读下去？是否有长句层级、指代或缩写界定造成额外负担？",
        ]
    structure_enabled = bool(getattr(t1, "structure_check_enabled", False))
    if structure_enabled and not t1.structure_ok:
        qs.insert(0, "用户或 legacy 配置要求的结构是否满足？若无显式要求，只新增 allowed_new_heading_commands 允许的标题命令。")
    if not t1.citation_ok:
        qs.insert(0, f"缺失引用 keys：{', '.join(t1.missing_citation_keys[:10])}（是否需要补 bib 或删除未核验引用）？")

    adv: List[str] = []
    if structure_enabled and not t1.structure_ok:
        adv.append("按用户或 legacy 配置修复缺失结构；未显式要求时只修正文论证链，只新增 allowed_new_heading_commands 允许的标题。")
    if not t1.citation_ok:
        adv.append("修复所有缺失 bibkey：提供 DOI/链接（或可核验题录信息），补齐 references/*.bib 后再写入 \\cite{...}。")
    if t1.avoid_commands_hits:
        adv.append("移除 \\section/\\subsection/\\input/\\include 等命令，避免破坏模板。")
    adv.append("每段都补一个“可验证锚点”：理论证明/定理/数值验证/对照实验/数据来源/指标定义。")
    adv.append("对每个可读性问题记录“原句特征/位置→障碍类型→大同行理解影响→保留含义→保真改法”：长句可拆为事实—转折—结论，指代/缩写可用原文已有信息补足；不得改变事实、限定、术语或 LaTeX 结构，已清楚的专业表述无需为通俗而改写。")
    adv.append("在正文结尾补充自然过渡，指向用户指定的研究内容与技术路线，不假定固定章节名称。")

    md = [
        "# 评审人视角质疑与建议（自动生成）",
        "",
        "## 写作导向",
        "",
        style_preamble_text(style_mode).strip(),
        "",
        "## DoD 复核要点",
        dod_checklist.strip() if dod_checklist.strip() else "（未找到 dod_checklist.md）",
        "",
        "## 专业可读性复核",
        "- 面向熟悉本学科但未必熟悉该细分方向的大同行，定位长句层级、指代/缩写界定、抽象名词关系和段内事实—缺口—结论衔接；说明阅读影响与保真改法。",
        "- 仅作表达建议，不删除必要术语、事实、限定、可证伪条件、引用命令或 LaTeX 结构；已清楚的专业表述无需为通俗而改写。",
        "",
        "## 评审人可能会问的问题",
        "",
    ] + [f"- {q}" for q in qs[:12]] + [
        "",
        "## 对应的可执行修改建议",
        "",
    ] + [f"- {a}" for a in adv[:12]]
    return "\n".join(md).strip() + "\n"


async def generate_review_markdown(
    *,
    skill_root: Path,
    config: Dict[str, Any],
    report: DiagnosticReport,
    tex_text: str,
    ai: Optional[AIIntegration] = None,
) -> str:
    skill_root = Path(skill_root).resolve()
    dod_checklist = _load_dod_checklist(skill_root)

    ai_obj = ai
    if ai_obj is None:
        ai_cfg = get_mapping(config, "ai")
        ai_obj = AIIntegration(enable_ai=get_bool(ai_cfg, "enabled", True), config=config)

    prompt = get_prompt(
        name="review_suggestions",
        default="",
        skill_root=skill_root,
        config=config,
        variant=get_str(config, "active_preset", "").strip() or None,
    )
    style_mode = get_style_mode(config)
    style_preamble = style_preamble_text(style_mode).strip()

    def _fallback() -> str:
        return _fallback_review_markdown(report=report, dod_checklist=dod_checklist, style_mode=style_mode)

    if not prompt.strip():
        return _fallback()

    t1_json = json.dumps(report.to_dict().get("tier1", {}), ensure_ascii=False, indent=2)
    filled = prompt.format(
        style_preamble=style_preamble,
        dod_checklist=dod_checklist,
        tier1_json=t1_json,
        tex=(tex_text or "")[:12000],
    )
    obj = await ai_obj.process_request(task="review_suggestions", prompt=filled, fallback=_fallback, output_format="text")
    return str(obj).strip() + "\n"
