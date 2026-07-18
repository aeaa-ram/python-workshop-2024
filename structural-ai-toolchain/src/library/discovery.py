"""Finding atoms: a drill-down catalog tree AND a free-text search.

Two complementary ways to find a formula, because engineers think both
ways:

- ``catalog()`` -> nested dict you navigate like a flowchart / dropdown:
  jurisdiction -> code -> chapter -> clause -> [atoms]. Good when you know
  "Denmark, Eurocode 2, chapter 6, clause 6.2.1".
- ``search("crack width")`` -> ranked hits across id, description, clause,
  result symbol and concept. Good when you only know what it does.

Both are plain data so the CLI, the tkinter GUI and the HTML dashboard can
all present them without re-implementing the logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.library.registry import Atom, all_atoms

_TOKEN = re.compile(r"[a-z0-9]+")


def catalog() -> dict:
    """Nested tree: jurisdiction -> code -> chapter -> clause -> [atom_id]."""
    tree: dict = {}
    for atom in all_atoms():
        juris, code, chapter, clause = atom.path()
        (tree.setdefault(juris, {})
             .setdefault(code, {})
             .setdefault(chapter, {})
             .setdefault(clause, [])).append(atom.atom_id)
    return tree


def catalog_lines() -> list[str]:
    """Flat, indented rendering of the catalog for a terminal."""
    lines: list[str] = []
    tree = catalog()
    for juris in sorted(tree):
        lines.append(juris)
        for code in sorted(tree[juris]):
            lines.append(f"  {code}")
            for chapter in sorted(tree[juris][code]):
                lines.append(f"    {chapter}")
                for clause in sorted(tree[juris][code][chapter]):
                    ids = tree[juris][code][chapter][clause]
                    lines.append(f"      {clause}")
                    for atom_id in sorted(ids):
                        lines.append(f"        • {atom_id}")
    return lines


@dataclass
class SearchHit:
    atom: Atom
    score: float

    def __str__(self) -> str:
        return (
            f"[{self.score:.2f}] {self.atom.atom_id}  "
            f"({self.atom.result} = {self.atom.expression})\n"
            f"        {self.atom.description} "
            f"[{self.atom.clause or self.atom.code}]"
        )


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def search(query: str, limit: int = 12) -> list[SearchHit]:
    """Rank atoms by relevance to a free-text query."""
    q = _tokens(query)
    if not q:
        return []
    hits: list[SearchHit] = []
    for atom in all_atoms():
        haystacks = {
            "id": atom.atom_id.replace(".", " ") + " " + atom.result,
            "desc": atom.description,
            "clause": f"{atom.clause} {atom.code} {atom.chapter}",
            "concept": atom.concept.replace(".", " "),
        }
        weights = {"id": 1.0, "desc": 1.2, "clause": 0.8, "concept": 0.9}
        score = 0.0
        for field, text in haystacks.items():
            toks = _tokens(text)
            if not toks:
                continue
            overlap = len(q & toks)
            if overlap:
                score += weights[field] * overlap / len(q)
            # substring bonus (e.g. "crack" in "crack_width")
            if query.lower() in text.lower():
                score += weights[field] * 0.5
        if score > 0:
            hits.append(SearchHit(atom, score))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
