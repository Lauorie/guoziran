"""nsfc-proposal 脚本共用的路径、YAML、配置与文本工具。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_DIRNAME = "proposal"


class ProposalError(ValueError):
    """输入、路径或文件内容不合法；CLI 以退出码 2 报告。"""


@dataclass(frozen=True)
class ProposalPaths:
    root: Path
    case: Path
    case_md: Path
    evidence: Path
    plan: Path
    assumptions: Path
    leads: Path


def read_yaml(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProposalError(f"文件不存在：{path}") from exc
    except yaml.YAMLError as exc:
        raise ProposalError(f"{Path(path).name} 不是合法 YAML：{exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ProposalError(f"{Path(path).name} 顶层必须是映射")
    return data


def write_yaml(path: Path, data: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


def load_config() -> Dict[str, Any]:
    return read_yaml(SKILL_ROOT / "config.yaml")


def resolve_project_root(path: Path | str) -> Path:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ProposalError(f"project_root 不存在或不是目录：{root}")
    return root


def project_path(project_root: Path, relpath: str) -> Path:
    root = Path(project_root).resolve()
    target = (root / relpath).resolve()
    if target != root and root not in target.parents:
        raise ProposalError(f"路径越出 project_root：{relpath}")
    return target


def proposal_paths(project_root: Path) -> ProposalPaths:
    base = project_path(project_root, PROPOSAL_DIRNAME)
    return ProposalPaths(
        root=base,
        case=base / "scientific_case.yaml",
        case_md=base / "scientific_case.md",
        evidence=base / "evidence_map.yaml",
        plan=base / "section_plan.yaml",
        assumptions=base / "assumptions.md",
        leads=base / "literature_leads.md",
    )


def split_latex_comment(line: str) -> tuple[str, str]:
    """把一行 LaTeX 拆成（正文，注释）。前面有奇数个反斜杠的 % 是转义字符，不是注释。"""
    for index, char in enumerate(line):
        if char != "%":
            continue
        backslashes = 0
        j = index - 1
        while j >= 0 and line[j] == "\\":
            backslashes += 1
            j -= 1
        if backslashes % 2 == 0:
            return line[:index], line[index + 1:]
    return line, ""


def append_under_heading(path: Path, heading: str, line: str) -> None:
    """在 Markdown 文件的指定二级标题下追加一行；标题不存在时在文件末尾新建。"""
    target = Path(path)
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    if heading in lines:
        start = lines.index(heading)
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        if insert_at == start + 1:
            lines[insert_at:insert_at] = ["", line]
        else:
            lines.insert(insert_at, line)
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([heading, "", line])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
