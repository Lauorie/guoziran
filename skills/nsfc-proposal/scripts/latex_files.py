"""沿 main.tex 的 \\input/\\include 遍历编译树，找出被编译的 .tex 与 \\bibliography 指向的 .bib。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from proposal_common import ProposalError, split_latex_comment

INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
BIB_RE = re.compile(r"\\(?:bibliography|addbibresource(?:\[[^\]]*\])?)\{([^}]+)\}")
ENTRY_START_RE = re.compile(r"@([A-Za-z]+)\s*[{(]\s*([^,\s]*)\s*,?")
DOI_FIELD_RE = re.compile(r"\bdoi\s*=\s*[{\"]\s*([^}\"]+?)\s*[}\"]", re.IGNORECASE)
NON_ENTRY_TYPES = {"comment", "string", "preamble"}


@dataclass(frozen=True)
class LatexTree:
    tex_files: list[Path]
    bib_files: list[Path]


@dataclass(frozen=True)
class BibIndex:
    keys: frozenset[str]
    doi_keys: dict[str, str] = field(default_factory=dict)

    @property
    def dois(self) -> frozenset[str]:
        return frozenset(self.doi_keys)


def _inside(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def scan_latex_tree(project_root: Path) -> LatexTree:
    root = Path(project_root).resolve()
    main = root / "main.tex"
    if not main.is_file():
        raise ProposalError(f"project_root 缺少 main.tex：{root}")
    tex_files: list[Path] = []
    bib_files: list[Path] = []
    queue = [main]
    while queue:
        tex = queue.pop(0)
        if tex in tex_files or not tex.is_file():
            continue
        tex_files.append(tex)
        for raw in tex.read_text(encoding="utf-8", errors="replace").splitlines():
            line, _ = split_latex_comment(raw)
            for match in INPUT_RE.finditer(line):
                name = match.group(1).strip()
                child = (root / (name if name.endswith(".tex") else name + ".tex")).resolve()
                if _inside(root, child):
                    queue.append(child)
            for match in BIB_RE.finditer(line):
                for name in match.group(1).split(","):
                    name = name.strip()
                    if not name:
                        continue
                    bib = (root / (name if name.endswith(".bib") else name + ".bib")).resolve()
                    if _inside(root, bib) and bib not in bib_files:
                        bib_files.append(bib)
    return LatexTree(tex_files=tex_files, bib_files=bib_files)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip().replace("\\_", "_")
    raw = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^doi:\s*", "", raw, flags=re.IGNORECASE).strip().rstrip(".,;")
    return raw.lower() or None


def read_bib_index(bib_files: list[Path]) -> BibIndex:
    keys: set[str] = set()
    doi_keys: dict[str, str] = {}
    for path in bib_files:
        if not Path(path).is_file():
            continue
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        starts = list(ENTRY_START_RE.finditer(text))
        for index, match in enumerate(starts):
            if match.group(1).lower() in NON_ENTRY_TYPES or not match.group(2):
                continue
            key = match.group(2)
            keys.add(key)
            end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
            doi_match = DOI_FIELD_RE.search(text, match.end(), end)
            doi = normalize_doi(doi_match.group(1)) if doi_match else None
            if doi:
                doi_keys.setdefault(doi, key)
    return BibIndex(keys=frozenset(keys), doi_keys=doi_keys)


def relpath(project_root: Path, path: Path) -> str:
    return Path(path).resolve().relative_to(Path(project_root).resolve()).as_posix()
