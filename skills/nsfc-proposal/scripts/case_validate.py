"""scientific_case / evidence_map / section_plan 的确定性校验（设计文档 5.2–5.4 节）。

只做能用规则判断的检查，论证是否成立由 AI 判断。函数返回错误列表，不抛异常。
"""

from __future__ import annotations

from typing import Any, Mapping

CASE_STATUSES = {"draft", "confirmed", "bypassed"}
SOURCES = {"user", "ai_proposed"}
FEASIBILITY_KINDS = {"paper", "patent", "data", "platform", "preliminary", "team", "collaborator", "condition"}
FEASIBILITY_SOURCES = {"user_material", "missing"}
RISK_CATEGORIES = {"technical", "schedule", "resource"}
CLAIM_TYPES = {"background", "gap", "mechanism", "applicant_result"}
SUPPORT_RANK = {"unsupported": 0, "single_verified": 1, "multi_verified": 2}
SUPPORT_LEVELS = set(SUPPORT_RANK) | {"applicant_material"}
EVIDENCE_ROLES = {"supporting", "counter"}
EVIDENCE_BASES = {"fulltext", "full_abstract"}
QUESTION_ENDINGS = ("？", "?")
FOUNDATION_MARK = "研究基础"
PLAN_KEYWORDS = {
    "hypothesis": "科学假设",
    "entry_point": "切入点",
    "aim": "总体目标",
    "terms": "术语界定",
    "research_object": "研究对象",
    "importance": "重要性",
    "mainstream_routes": "主流路线",
    "feasibility": "可行性",
    "risks": "风险与应对",
    "constraints": "约束",
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _in(value: Any, allowed: set[str]) -> bool:
    """Check if value is a string and in the allowed set, avoiding TypeError on unhashable types."""
    return isinstance(value, str) and value in allowed


def _items(container: Mapping[str, Any], key: str, errors: list[str]) -> list[Mapping[str, Any]]:
    value = container.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} 必须是列表")
        return []
    items: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            items.append(item)
        else:
            errors.append(f"{key}[{index}] 必须是映射（键值对）")
    return items


def case_ids(case: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("gaps", "questions", "tasks"):
        for item in _items(case, key, []):
            if _text(item.get("id")):
                ids.add(_text(item.get("id")))
    return ids


def claim_ids(evidence: Mapping[str, Any] | None) -> set[str]:
    if not evidence:
        return set()
    return {_text(c.get("id")) for c in _items(evidence, "claims", []) if _text(c.get("id"))}


def _claim_refs(case: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("importance", "gaps", "mainstream_routes"):
        for item in _items(case, key, []):
            refs.update(_str_list(item.get("claim_ids")))
    return refs


def validate_case(case: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> list[str]:
    errors: list[str] = []
    version = case.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append("version 必须是不小于 1 的整数")
    if not _in(case.get("status"), CASE_STATUSES):
        errors.append("status 必须是 draft、confirmed 或 bypassed")

    research_object = _mapping(case.get("research_object"))
    if not _text(research_object.get("sample_vs_target_gap")):
        errors.append("research_object.sample_vs_target_gap 不能为空；样本与目标人群无差异时写「无」")
    if research_object and not _in(research_object.get("source"), SOURCES):
        errors.append("research_object.source 必须是 user 或 ai_proposed")

    terms = _items(case, "terms", errors)
    if not [t for t in terms if _text(t.get("term")) and _text(t.get("definition"))]:
        errors.append("terms 至少界定一个术语（term 与 definition 都要填）")
    for term in terms:
        if not _in(term.get("source"), SOURCES):
            errors.append(f"术语「{_text(term.get('term')) or '?'}」的 source 必须是 user 或 ai_proposed")

    gap_ids = {_text(g.get("id")) for g in _items(case, "gaps", errors) if _text(g.get("id"))}

    questions = _items(case, "questions", errors)
    if not questions and not isinstance(case.get("questions"), (str, int)):
        errors.append("questions 至少一条")
    question_ids: set[str] = set()
    for question in questions:
        qid = _text(question.get("id")) or "?"
        question_ids.add(qid)
        if not _text(question.get("text")).endswith(QUESTION_ENDINGS):
            errors.append(f"科学问题 {qid} 必须是以问号结尾的疑问句")
        answers = _str_list(question.get("answers_gaps"))
        if not answers:
            errors.append(f"科学问题 {qid} 至少回应一个缺口（answers_gaps）")
        for gid in answers:
            if gid not in gap_ids:
                errors.append(f"科学问题 {qid} 引用了不存在的缺口 {gid}")

    hypothesis = _mapping(case.get("hypothesis"))
    falsification = _mapping(hypothesis.get("falsification"))
    if not _text(hypothesis.get("statement")):
        errors.append("hypothesis.statement 不能为空")
    if not (_text(falsification.get("condition")) and _text(falsification.get("metric"))):
        errors.append("hypothesis.falsification 的 condition 和 metric 都不能为空")

    covered: set[str] = set()
    for task in _items(case, "tasks", errors):
        tid = _text(task.get("id")) or "?"
        ref = _text(task.get("question"))
        if ref not in question_ids:
            errors.append(f"研究任务 {tid} 指向不存在的科学问题 {ref or '（空）'}")
        covered.add(ref)
        if not _str_list(task.get("baselines")):
            errors.append(f"研究任务 {tid} 缺少必比基线（baselines）")
    for qid in sorted(question_ids - covered - {"?"}):
        errors.append(f"科学问题 {qid} 没有对应的研究任务")

    for item in _items(case, "constraints", errors):
        if not _in(item.get("source"), SOURCES):
            errors.append(f"约束「{_text(item.get('text')) or '?'}」的 source 必须是 user 或 ai_proposed")
    for item in _items(case, "feasibility", errors):
        label = _text(item.get("text")) or "?"
        if not _in(item.get("kind"), FEASIBILITY_KINDS):
            errors.append(f"可行性条目「{label}」的 kind 不在允许值内")
        if not _in(item.get("source"), FEASIBILITY_SOURCES):
            errors.append(f"可行性条目「{label}」的 source 必须是 user_material 或 missing")
    risks = _items(case, "risks", errors)
    for risk in risks:
        if not _in(risk.get("category"), RISK_CATEGORIES):
            errors.append(f"风险「{_text(risk.get('risk')) or '?'}」的 category 必须是 technical、schedule 或 resource")
    if FOUNDATION_MARK in _str_list(_mapping(case.get("project")).get("sections")) and len(risks) < 3:
        errors.append("要写研究基础时，risks 至少 3 条")

    refs = _claim_refs(case)
    if refs and evidence is None:
        errors.append("scientific_case 引用了论断编号，但缺少 evidence_map.yaml")
    elif refs:
        for ref in sorted(refs - claim_ids(evidence)):
            errors.append(f"论断编号 {ref} 在 evidence_map.yaml 中不存在")
    return errors


def validate_evidence(evidence: Mapping[str, Any], bib_keys: set[str] | None) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for claim in _items(evidence, "claims", errors):
        cid = _text(claim.get("id")) or "?"
        if cid in seen:
            errors.append(f"论断编号 {cid} 重复")
        seen.add(cid)
        if not _text(claim.get("text")):
            errors.append(f"论断 {cid} 的 text 不能为空")
        claim_type = claim.get("type")
        if not _in(claim_type, CLAIM_TYPES):
            errors.append(f"论断 {cid} 的 type 必须是 {'、'.join(sorted(CLAIM_TYPES))} 之一")
        support = claim.get("support")
        if not _in(support, SUPPORT_LEVELS):
            errors.append(f"论断 {cid} 的 support 必须是 {'、'.join(sorted(SUPPORT_LEVELS))} 之一")
            continue
        entries = claim.get("evidence") or []
        if not isinstance(entries, list):
            errors.append(f"论断 {cid} 的 evidence 必须是列表")
            entries = []
        verified_refs: set[str] = set()
        for entry in entries:
            if not isinstance(entry, Mapping):
                errors.append(f"论断 {cid} 的 evidence 条目必须是映射")
                continue
            ref = _text(entry.get("ref"))
            if not _in(entry.get("role"), EVIDENCE_ROLES):
                errors.append(f"论断 {cid} 的证据 {ref or '?'} 的 role 必须是 supporting 或 counter")
            is_lead = ref.startswith("lead:")
            if ref and not is_lead and bib_keys is not None and ref not in bib_keys:
                errors.append(f"论断 {cid} 的证据 {ref} 不在 .bib 中")
            if entry.get("role") == "supporting" and ref and not is_lead and _in(entry.get("basis"), EVIDENCE_BASES):
                verified_refs.add(ref)
        verified = len(verified_refs)
        if support == "applicant_material":
            if claim_type != "applicant_result":
                errors.append(f"论断 {cid}：applicant_material 只能用于 applicant_result 类论断")
            continue
        allowed = "multi_verified" if verified >= 2 else ("single_verified" if verified == 1 else "unsupported")
        if SUPPORT_RANK[support] > SUPPORT_RANK[allowed]:
            errors.append(f"论断 {cid} 记为 {support}，但已核实的支持证据只够 {allowed}")
    return errors


def validate_plan(plan: Mapping[str, Any], case: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    files = _items(plan, "files", errors)
    if not files:
        errors.append("section_plan.files 至少一条")
    ids = case_ids(case)
    missing_feasibility = [f for f in _items(case, "feasibility", []) if f.get("source") == "missing"]
    seen: set[str] = set()
    for entry in files:
        name = _text(entry.get("file")) or "?"
        if name in seen:
            errors.append(f"文件 {name} 重复出现")
        seen.add(name)
        if not _text(entry.get("writer")):
            errors.append(f"{name} 缺少 writer")
        for key in ("must_include", "must_exclude", "placeholders"):
            if not isinstance(entry.get(key, []), list):
                errors.append(f"{name} 的 {key} 必须是列表")
        for ref in _str_list(entry.get("must_include")):
            if ref not in ids and ref not in PLAN_KEYWORDS:
                errors.append(f"{name} 的 must_include 含未知编号或字段 {ref}")
        length = entry.get("length")
        if length is not None:
            low, high = _mapping(length).get("min"), _mapping(length).get("max")
            if not (isinstance(low, int) and isinstance(high, int) and 0 < low <= high):
                errors.append(f"{name} 的 length 需要满足 0 < min ≤ max 的整数")
        version = entry.get("written_with_case_version")
        if version is not None and (not isinstance(version, int) or isinstance(version, bool)):
            errors.append(f"{name} 的 written_with_case_version 必须是整数或 null")
        if FOUNDATION_MARK in name and len(_str_list(entry.get("placeholders"))) < len(missing_feasibility):
            errors.append(f"{name} 的 placeholders 少于科学论证中标为 missing 的可行性条目（{len(missing_feasibility)} 条）")
    return errors


def validate_all(
    case: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    plan: Mapping[str, Any] | None,
    *,
    bib_keys: set[str] | None = None,
) -> list[str]:
    problems = [f"[scientific_case] {e}" for e in validate_case(case, evidence)]
    if evidence is not None:
        problems += [f"[evidence_map] {e}" for e in validate_evidence(evidence, bib_keys)]
    if plan is not None:
        problems += [f"[section_plan] {e}" for e in validate_plan(plan, case)]
    return problems
