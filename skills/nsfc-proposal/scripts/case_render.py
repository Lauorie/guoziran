"""把科学论证渲染成确认点 Markdown 和三个写作 skill 的信息表。

信息表的字段和标题照抄各写作 skill 的 references/info_form.md，正文中不出现内部编号。
"""

from __future__ import annotations

import functools
import importlib.util
from types import ModuleType
from typing import Any, Mapping

from case_validate import PLAN_KEYWORDS
from proposal_common import SKILL_ROOT, ProposalError

WRITERS = ("nsfc-justification-writer", "nsfc-research-content-writer", "nsfc-research-foundation-writer")
NONE = "（无）"
STATUS_LABELS = {"draft": "草稿", "confirmed": "已确认", "bypassed": "未确认（先继续）"}
SUPPORT_LABELS = {"multi_verified": "多篇核实", "single_verified": "单篇核实", "unsupported": "无文献支持", "applicant_material": "申请人材料"}
FEASIBILITY_GROUPS = (
    ("### 1.1 已发表/已接收论文", {"paper"}),
    ("### 1.2 专利/软件著作权/数据集/平台/原型", {"patent", "data", "platform"}),
    ("### 1.3 预实验/初步结果", {"preliminary"}),
    ("### 2.1 关键成员", {"team"}),
    ("### 2.2 合作单位", {"collaborator"}),
    ("## 3. 条件与资源", {"condition"}),
)
RISK_GROUPS = (("### 4.1 技术风险", "technical"), ("### 4.2 进度风险", "schedule"), ("### 4.3 资源风险", "resource"))
# 研究期限的年数表只在 content-writer 的 config.yaml（yearly_plan），由它的 plan_years.py 读取
PLAN_YEARS_PY = SKILL_ROOT.parent / "nsfc-research-content-writer" / "scripts" / "plan_years.py"


def _t(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _items(case: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = case.get(key)
    return [v for v in value if isinstance(v, Mapping)] if isinstance(value, list) else []


def _strs(value: Any) -> list[str]:
    return [v.strip() for v in value if isinstance(v, str) and v.strip()] if isinstance(value, list) else []


def _bullets(lines: list[str], indent: str = "") -> str:
    return "\n".join(f"{indent}- {line}" for line in lines) if lines else f"{indent}- {NONE}"


def _id_texts(case: Mapping[str, Any]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for key, field in (("gaps", "text"), ("questions", "text"), ("tasks", "aim")):
        for item in _items(case, key):
            if _t(item.get("id")):
                texts[_t(item["id"])] = _t(item.get(field)) or NONE
    return texts


def _describe(ref: str, ids: Mapping[str, str]) -> str:
    if ref in PLAN_KEYWORDS:
        return PLAN_KEYWORDS[ref]
    text = ids.get(ref, ref)
    return text if len(text) <= 24 else text[:24] + "…"


def _plan_entries(plan: Mapping[str, Any] | None, writer: str) -> list[Mapping[str, Any]]:
    if not plan:
        return []
    return [f for f in _items(plan, "files") if f.get("writer") == writer]


def _ai_marker(item: Mapping[str, Any]) -> str:
    return "（AI 拟定，待确认）" if item.get("source") == "ai_proposed" else ""


def _placeholder(text: str) -> str:
    return f"【待补充：{text}】"


@functools.lru_cache(maxsize=1)
def _plan_years() -> ModuleType:
    """按路径加载 content-writer 的 plan_years.py；用独立模块名，不改 sys.path。"""
    spec = importlib.util.spec_from_file_location("nrcw_plan_years", PLAN_YEARS_PY)
    if spec is None or spec.loader is None or not PLAN_YEARS_PY.is_file():
        raise ProposalError(
            "找不到 nsfc-research-content-writer 的 plan_years.py；"
            "请确认该 skill 与 nsfc-proposal 位于同一 skills 目录，且含 scripts/plan_years.py"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _duration_line(case: Mapping[str, Any]) -> str:
    project = case.get("project") if isinstance(case.get("project"), Mapping) else {}
    project_type = _t(project.get("type"))
    plan_years = _plan_years()  # 找不到脚本时直接报 ProposalError，不当作配置错误
    try:
        years, matched = plan_years.duration_years(project_type)
    except ValueError as exc:
        raise ProposalError(f"nsfc-research-content-writer 的 yearly_plan 配置有误：{exc}") from exc
    line = f"研究期限 {years} 年（项目类型：{project_type or '未写明'}）；按 {years} 年分年度写，不跨年"
    if matched:
        return line
    reason = f"项目类型「{project_type}」不在年数表中" if project_type else "项目类型未写明"
    return line + f"；{reason}，按 {years} 年；请在 assumptions.md 记一条 AI 拟定项"


def render_case_md(case: Mapping[str, Any], evidence: Mapping[str, Any] | None, plan: Mapping[str, Any] | None) -> str:
    ids = _id_texts(case)
    gaps = {k: v for k, v in ids.items() if any(_t(g.get("id")) == k for g in _items(case, "gaps"))}
    hypothesis = case.get("hypothesis") if isinstance(case.get("hypothesis"), Mapping) else {}
    falsification = hypothesis.get("falsification") if isinstance(hypothesis.get("falsification"), Mapping) else {}
    obj = case.get("research_object") if isinstance(case.get("research_object"), Mapping) else {}
    status = STATUS_LABELS.get(str(case.get("status")), str(case.get("status")))
    out = [f"# 科学论证（第 {case.get('version')} 版，状态：{status}）", "", "> 由 proposal/scientific_case.yaml 生成，请勿手改本文件。", ""]

    out += ["## 科学问题", ""]
    for question in _items(case, "questions"):
        answered = "；".join(gaps.get(g, g) for g in _strs(question.get("answers_gaps")))
        out.append(f"- {_t(question.get('text')) or NONE}（回应的缺口：{answered or NONE}）")
    out.append("")

    out += ["## 科学假设", "", _t(hypothesis.get("statement")) or NONE, ""]
    out.append(f"- 否定条件：{_t(falsification.get('condition')) or NONE}")
    out.append(f"- 判定指标：{_t(falsification.get('metric')) or NONE}")
    for prediction in _strs(hypothesis.get("predictions")):
        out.append(f"- 可检验的推论：{prediction}")
    out.append("")

    out += ["## 术语界定", ""]
    out.append(_bullets([f"**{_t(t.get('term'))}**：{_t(t.get('definition'))}{_ai_marker(t)}" for t in _items(case, "terms")]))
    out.append("")

    out += ["## 研究对象", ""]
    for label, key in (("研究对象", "object"), ("目标人群", "target_population"), ("样本来源", "sample_source"),
                       ("样本与目标人群的差异", "sample_vs_target_gap"), ("偏倚处理", "bias_handling")):
        out.append(f"- {label}：{_t(obj.get(key)) or NONE}")
    if obj.get("source") == "ai_proposed":
        out.append("- 以上由 AI 拟定，待确认")
    out.append("")

    out += ["## 各章分工", "", "| 文件 | 写作 skill | 必写 | 不写 | 篇幅 |", "|---|---|---|---|---|"]
    for entry in _items(plan or {}, "files"):
        include = "；".join(_describe(r, ids) for r in _strs(entry.get("must_include"))) or NONE
        exclude = "；".join(_strs(entry.get("must_exclude"))) or NONE
        length = entry.get("length") if isinstance(entry.get("length"), Mapping) else None
        size = f"{length.get('min')}–{length.get('max')} 字" if length else NONE
        out.append(f"| {entry.get('file')} | {entry.get('writer')} | {include} | {exclude} | {size} |")
    out.append("")

    ai_items = [f"术语「{_t(t.get('term'))}」" for t in _items(case, "terms") if t.get("source") == "ai_proposed"]
    if obj.get("source") == "ai_proposed":
        ai_items.insert(0, "研究对象与样本来源")
    ai_items += [f"约束「{_t(c.get('text'))}」" for c in _items(case, "constraints") if c.get("source") == "ai_proposed"]
    out += ["## AI 拟定的条目（需要你确认）", "", _bullets(ai_items), ""]

    counts = {label: 0 for label in SUPPORT_LABELS.values()}
    for claim in _items(evidence or {}, "claims"):
        label = SUPPORT_LABELS.get(str(claim.get("support")))
        if label:
            counts[label] += 1
    total = sum(counts.values())
    out += ["## 证据概况", "", f"论断 {total} 条：" + "，".join(f"{k} {v}" for k, v in counts.items()), ""]
    return "\n".join(out)


def _section_notes(plan: Mapping[str, Any] | None, writer: str) -> list[str]:
    notes = []
    for entry in _plan_entries(plan, writer):
        length = entry.get("length") if isinstance(entry.get("length"), Mapping) else None
        if length:
            notes.append(f"{entry.get('file')} 篇幅：{length.get('min')}–{length.get('max')} 字")
        exclude = _strs(entry.get("must_exclude"))
        if exclude:
            notes.append(f"{entry.get('file')} 不写：{'；'.join(exclude)}")
        placeholders = _strs(entry.get("placeholders"))
        if placeholders:
            notes.append(f"{entry.get('file')} 占位（逐字照抄，不改写）：{'；'.join(placeholders)}")
    notes.append("措辞强度不得超过 proposal/evidence_map.yaml 中各论断的 support；正文不得出现任何内部编号")
    return notes


def _object_line(case: Mapping[str, Any]) -> str:
    obj = case.get("research_object") if isinstance(case.get("research_object"), Mapping) else {}
    parts = [f"{label}：{_t(obj.get(key))}" for label, key in (("研究对象", "object"), ("目标人群", "target_population"),
             ("样本来源", "sample_source"), ("样本与目标人群的差异", "sample_vs_target_gap"), ("偏倚处理", "bias_handling")) if _t(obj.get(key))]
    return "；".join(parts) or NONE


def _justification_form(case: Mapping[str, Any], plan: Mapping[str, Any] | None) -> str:
    hypothesis = case.get("hypothesis") if isinstance(case.get("hypothesis"), Mapping) else {}
    falsification = hypothesis.get("falsification") if isinstance(hypothesis.get("falsification"), Mapping) else {}
    prior = [f"{_t(f.get('text'))}（申请人材料）" if f.get("source") == "user_material" else f"缺失：正文写占位 {_placeholder(_t(f.get('text')))}" for f in _items(case, "feasibility")]
    extra = [f"术语口径：{_t(t.get('term'))}——{_t(t.get('definition'))}" for t in _items(case, "terms")]
    extra.append(f"否定条件：{_t(falsification.get('condition')) or NONE}（判定指标：{_t(falsification.get('metric')) or NONE}）")
    extra += _section_notes(plan, "nsfc-justification-writer")
    lines = [
        f"# NSFC 写作信息表（nsfc-proposal 第 {case.get('version')} 版科学论证）", "",
        "## 必填",
        f"1. **研究对象/应用场景**：{_object_line(case)}",
        "2. **痛点与现有不足**：", _bullets([_t(g.get("text")) for g in _items(case, "gaps")], "   "),
        "3. **关键科学问题（疑问句，非研究目标）**：", _bullets([_t(q.get("text")) for q in _items(case, "questions")], "   "),
        f"4. **核心科学假设（陈述句，预测性结果，不写验证方式）**：{_t(hypothesis.get('statement')) or NONE}",
        "5. **本项目切入点（差异化切口）**：", _bullets([_t(case.get("entry_point"))] if _t(case.get("entry_point")) else [], "   "),
        "", "## 选填",
        "6. **拟解决技术/方法概览**：", _bullets([_t(t.get("aim")) for t in _items(case, "tasks")], "   "),
        "7. **前期基础（可核验）**：", _bullets(prior, "   "),
        "8. **主流路线与代表工作（引用先核验）**：", _bullets([f"{_t(r.get('name'))}：{_t(r.get('limitation'))}" for r in _items(case, "mainstream_routes")], "   "),
        "", "## 可选补充", _bullets(extra),
    ]
    return "\n".join(lines) + "\n"


def _content_form(case: Mapping[str, Any], plan: Mapping[str, Any] | None) -> str:
    hypothesis = case.get("hypothesis") if isinstance(case.get("hypothesis"), Mapping) else {}
    questions = {_t(q.get("id")): _t(q.get("text")) for q in _items(case, "questions")}
    tasks = _items(case, "tasks")
    aims = {_t(t.get("id")): _t(t.get("aim")) for t in tasks}
    subgoals, breakdown, validations = [], [], []
    for task in tasks:
        subgoals.append(
            f"子目标：{_t(task.get('aim')) or NONE}；对应科学问题：{questions.get(_t(task.get('question')), NONE)}；"
            f"指标：{_t(task.get('indicator')) or NONE}；对照/基线：{'、'.join(_strs(task.get('baselines'))) or NONE}；"
            f"需控制的混杂：{'、'.join(_strs(task.get('confounders'))) or NONE}；数据来源与验证：{_t(task.get('validation')) or NONE}")
        resolved_deps = [aims.get(d) for d in _strs(task.get("depends_on")) if d in aims]
        deps = "、".join(resolved_deps)
        breakdown.append(f"{_t(task.get('aim')) or NONE}：{'；'.join(_strs(task.get('subtasks'))) or NONE}" + (f"（依赖：{deps}）" if deps else ""))
        validations.append(f"{_t(task.get('aim')) or NONE}：{_t(task.get('validation')) or NONE}")
    routes = [f"{_t(r.get('name'))}：{_t(r.get('limitation'))}" for r in _items(case, "mainstream_routes")]
    if _t(case.get("entry_point")):
        routes.append(f"本项目切入点：{_t(case.get('entry_point'))}")
    constraints = [_t(c.get("text")) + ("（AI 拟定）" if c.get("source") == "ai_proposed" else "") for c in _items(case, "constraints")]
    risks = [f"{_t(r.get('risk'))}；应对：{_t(r.get('mitigation'))}" for r in _items(case, "risks")]
    lines = [
        f"# NSFC 写作信息表（面向（二）研究内容；nsfc-proposal 第 {case.get('version')} 版科学论证）", "",
        f"1. **研究对象/应用场景**：{_object_line(case)}",
        f"2. **核心科学问题与假说**：假说：{_t(hypothesis.get('statement')) or NONE}；科学问题：{'；'.join(questions.values()) or NONE}",
        f"3. **总体目标**：{_t(case.get('aim')) or NONE}",
        "4. **子目标（3–4 个，强制可检验）**：", _bullets(subgoals, "   "),
        f"5. **技术路线概览**：{' → '.join(a for a in aims.values() if a) or NONE}",
        "6. **关键方法与验证**：", _bullets(validations, "   "),
        "7. **年度资源约束**：", _bullets(constraints, "   "),
        "8. **任务分解**：", _bullets(breakdown, "   "),
        "9. **创新对照坐标系**：", _bullets(routes, "   "),
        f"10. **研究期限与分年硬约束**：{_duration_line(case)}", _bullets(constraints, "   "),
        "11. **关键风险与备选路线**：", _bullets(risks, "   "),
        "", "## 可选补充", _bullets(_section_notes(plan, "nsfc-research-content-writer") + ["子目标编号只用于内部规划，正文用自然语言指代"]),
    ]
    return "\n".join(lines) + "\n"


def _foundation_form(case: Mapping[str, Any], plan: Mapping[str, Any] | None) -> str:
    feasibility = _items(case, "feasibility")
    lines = [f"# NSFC 写作信息表（面向（三）研究基础；nsfc-proposal 第 {case.get('version')} 版科学论证）", "", "## 1. 前期基础（证据链素材）"]
    for heading, kinds in FEASIBILITY_GROUPS:
        if heading.startswith("### 2.1"):
            lines += ["", "## 2. 团队与分工"]
        entries = []
        for item in feasibility:
            if item.get("kind") not in kinds:
                continue
            text = _t(item.get("text"))
            entries.append(text if item.get("source") == "user_material" else f"缺失：{text}。正文写「可选补充」中列出的对应占位，逐字照抄，不得略去或编造")
        lines += ["", heading, _bullets(entries)]
    lines += ["", "## 4. 风险清单"]
    for heading, category in RISK_GROUPS:
        risks = [f"{_t(r.get('risk'))}；应对：{_t(r.get('mitigation'))}" for r in _items(case, "risks") if r.get("category") == category]
        lines += ["", heading, _bullets(risks)]
    lines += ["", "## 研究任务（可行性需逐条覆盖）", _bullets([_t(t.get("aim")) for t in _items(case, "tasks")])]
    lines += ["", "## 可选补充", _bullets(_section_notes(plan, "nsfc-research-foundation-writer"))]
    return "\n".join(lines) + "\n"


def info_form(case: Mapping[str, Any], plan: Mapping[str, Any] | None, writer: str) -> str:
    builders = {
        "nsfc-justification-writer": _justification_form,
        "nsfc-research-content-writer": _content_form,
        "nsfc-research-foundation-writer": _foundation_form,
    }
    if writer not in builders:
        raise ProposalError(f"未知写作 skill：{writer}；可选：{'、'.join(WRITERS)}")
    return builders[writer](case, plan)
