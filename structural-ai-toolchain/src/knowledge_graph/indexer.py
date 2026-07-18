"""Repository indexer for the AI Knowledge Graph.

Walks ``/repository``, loads every tool manifest and builds:

- a searchable document per tool (title + description + variable names +
  formulas), used by the similarity engine
- a relationship map: tools that share variables/concepts, so reviewers
  can see which calculations feed or mirror each other

The index is cached at ``repository/.index.json`` and rebuilt on demand.
An embedding backend can be plugged in later (see similarity.py) without
changing this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolRecord:
    slug: str
    title: str
    description: str = ""
    reference: str = ""
    variables: list[str] = field(default_factory=list)
    formulas: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    def document(self) -> str:
        """Flat text used for similarity scoring."""
        return " ".join(
            [self.title, self.description, self.reference]
            + self.variables
            + self.formulas
            + self.checks
        )


def load_records(repo_dir: str | Path) -> list[ToolRecord]:
    repo_dir = Path(repo_dir)
    records: list[ToolRecord] = []
    if not repo_dir.exists():
        return records
    for manifest_path in sorted(repo_dir.glob("*/manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        records.append(
            ToolRecord(
                slug=data.get("tool_id", manifest_path.parent.name),
                title=data.get("title", ""),
                description=data.get("description", ""),
                reference=data.get("reference", ""),
                variables=[v["name"] for v in data.get("variables", [])],
                formulas=[
                    v["expression"]
                    for v in data.get("variables", [])
                    if v.get("expression")
                ],
                checks=data.get("checks", []),
            )
        )
    return records


def build_index(repo_dir: str | Path) -> dict:
    """Rebuild and persist the knowledge-graph index."""
    repo_dir = Path(repo_dir)
    records = load_records(repo_dir)
    relationships = _shared_variable_map(records)
    index = {
        "tools": [
            {
                "slug": r.slug,
                "title": r.title,
                "variables": r.variables,
                "formulas": r.formulas,
            }
            for r in records
        ],
        "relationships": relationships,
    }
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / ".index.json").write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )
    return index


def _shared_variable_map(records: list[ToolRecord]) -> list[dict]:
    """Edges between tools that reuse the same variable names."""
    edges: list[dict] = []
    for i, a in enumerate(records):
        for b in records[i + 1 :]:
            shared = sorted(set(a.variables) & set(b.variables))
            if len(shared) >= 2:
                edges.append(
                    {"tools": [a.slug, b.slug], "shared_variables": shared}
                )
    return edges
