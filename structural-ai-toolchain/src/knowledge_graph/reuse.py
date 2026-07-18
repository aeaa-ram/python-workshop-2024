"""Atomic reuse analysis — "what in this sheet is truly new?"

For every derived formula of an ingested (or hypothetical) tool, the
analyzer reports one of:

- ``matches_atom``  — the formula IS a library atom: don't re-implement,
  ``sheet.apply()`` the atom (single source of truth).
- ``matches_tool``  — an existing repository tool already computes this
  exact structure: candidate for extraction into a new shared atom.
- ``new``           — genuinely new logic; after review it may itself
  become an atom if it is reusable.

This is the atomic breakdown the Gatekeeper shows before anything is
committed, so shared math converges into ``src/library`` instead of
being copy-pasted across tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.knowledge_graph.fingerprint import (
    fingerprint_if_matchable,
    try_fingerprint,
)
from src.models.calculation import ParsedTool


@dataclass
class FormulaFinding:
    name: str            # variable the formula computes
    expression: str
    status: str          # 'matches_atom' | 'matches_tool' | 'new'
    match_id: str = ""   # atom id or "tool_slug:variable"
    fingerprint: str = ""

    def __str__(self) -> str:
        if self.status == "matches_atom":
            return (
                f"♻️  {self.name}: reuses library atom '{self.match_id}' "
                f"— use sheet.apply() instead of re-typing it"
            )
        if self.status == "matches_tool":
            return (
                f"🔁 {self.name}: same formula already lives in "
                f"'{self.match_id}' — consider extracting a shared atom"
            )
        return f"🆕 {self.name}: new logic"


def _atom_fingerprints() -> dict[str, str]:
    from src.library import all_atoms

    out: dict[str, str] = {}
    for atom in all_atoms():
        fp = fingerprint_if_matchable(atom.expression)
        if fp:
            out[fp] = atom.atom_id
    return out


def _repository_fingerprints(
    repo_dir: str | Path, exclude_slug: str = ""
) -> dict[str, str]:
    """fingerprint -> 'slug:variable' for every stored derived formula."""
    out: dict[str, str] = {}
    repo_dir = Path(repo_dir)
    if not repo_dir.exists():
        return out
    for manifest_path in sorted(repo_dir.glob("*/manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        slug = data.get("tool_id", manifest_path.parent.name)
        if slug == exclude_slug:
            continue
        for var in data.get("variables", []):
            expr = var.get("expression")
            if not expr:
                continue
            # Match only on formulas with enough structure to be
            # meaningful (see fingerprint_if_matchable) — not on the
            # stored full fingerprint, which exists for every formula.
            fp = fingerprint_if_matchable(expr)
            if fp:
                out.setdefault(fp, f"{slug}:{var['name']}")
    return out


def analyze_reuse(
    tool: ParsedTool, repo_dir: str | Path = "repository"
) -> list[FormulaFinding]:
    """Classify every derived formula of a parsed tool."""
    atom_index = _atom_fingerprints()
    repo_index = _repository_fingerprints(repo_dir)
    findings: list[FormulaFinding] = []
    for var in tool.variables:
        if var.role != "derived" or not var.expression:
            continue
        fp = fingerprint_if_matchable(var.expression)
        if fp is None:
            # Either unparseable or too trivial to match structurally —
            # treat as new logic (record the full fingerprint if any).
            findings.append(
                FormulaFinding(
                    var.name, var.expression, "new", "",
                    try_fingerprint(var.expression) or "",
                )
            )
            continue
        if fp in atom_index:
            findings.append(
                FormulaFinding(
                    var.name, var.expression, "matches_atom",
                    atom_index[fp], fp,
                )
            )
        elif fp in repo_index:
            findings.append(
                FormulaFinding(
                    var.name, var.expression, "matches_tool",
                    repo_index[fp], fp,
                )
            )
        else:
            findings.append(
                FormulaFinding(var.name, var.expression, "new", "", fp)
            )
    return findings
