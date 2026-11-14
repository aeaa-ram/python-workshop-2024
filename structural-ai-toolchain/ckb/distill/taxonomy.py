"""The taxonomy: clause structure of the code plus its notation.

``Taxonomy.resolve`` answers the question every later step depends on: *which
quantity of the code is this?*  The evidence is, in this order, the symbol
(compared without separators), the same symbol with a project qualifier
dropped (``d_c`` -> ``d``), and the words of the descriptive label.  A symbol
that means different things in different clauses (``k_1`` in shear and in
crack width, ``A_s`` in bending and in shear) is decided by context: the
clause printed next to it, the heading it stands under, and the clause of the
formula that uses it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .. import units as U
from ..notation import mathml, pretty, symkey

DATA = Path(__file__).resolve().parent.parent / "data" / "taxonomy.yaml"


@dataclass
class Concept:
    id: str
    name: str
    topic: str
    kind: str = "derived"            # derived | input | coefficient
    var: str = ""                    # identifier used in generated code
    symbol: str = ""                 # display form, e.g. "V_{Rd,c}"
    clause: str = ""
    eq: str = ""
    unit: str = "-"
    range: tuple | None = None       # in the customary unit
    aliases: list[str] = field(default_factory=list)
    words: list[str] = field(default_factory=list)
    ref: str = ""
    check: str = ""
    notes: list[str] = field(default_factory=list)
    strip: bool = False              # a width: per-unit-width sources leave it out
    order: int = 0

    def __post_init__(self):
        self.var = self.var or self.id
        info = U.parse_unit(self.unit)
        self.unit, self.factor, self.dims = info.text, info.factor, info.dims
        self.keys = {symkey(a) for a in self.aliases + [self.id, self.var]}
        self.words = [w.lower() for w in self.words]

    @property
    def text(self) -> str:
        return pretty(self.var, self.symbol)

    @property
    def ml(self) -> str:
        return mathml(self.var, self.symbol)

    @property
    def canonical_range(self) -> tuple | None:
        if not self.range:
            return None
        return (self.range[0] * self.factor, self.range[1] * self.factor)

    @property
    def reference(self) -> str:
        """Clause and expression as one string."""
        bits = [f"cl. {self.clause}" if self.clause and not self.clause.lower().startswith("table") else self.clause]
        if self.eq:
            bits.append(f"expr. {self.eq}")
        return ", ".join(b for b in bits if b)


@dataclass
class Match:
    concept: Concept
    score: float
    how: str


def clause_number(text: str) -> str:
    """'EN 1992-1-1 cl. 6.2.2(1)' -> '6.2.2'; '' when the text names an expression."""
    if not text or re.search(r"\b(eq|expr)\.", text):
        return ""
    m = re.search(r"(\d+(?:\.\d+)+|\b\d+\b)(?=\s*(?:\(|$))", text.split("cl.")[-1])
    return m.group(1) if m else ""


def eq_number(text: str) -> str:
    """'eq. (6.2.a)' -> '6.2a'."""
    m = re.search(r"(?:eq|expr)\.\s*\(?\s*(\d+(?:\.\d+)*)\.?([A-Za-z]{0,2})\)?", text or "")
    return (m.group(1) + m.group(2)).lower() if m else ""


def related(a: str, b: str) -> bool:
    """Is one clause number inside the other (6.2.2 and 6.2)?"""
    if not a or not b:
        return False
    pa, pb = a.split("."), b.split(".")
    n = min(len(pa), len(pb))
    return pa[:n] == pb[:n]


def _drops(name: str) -> list[tuple[str, int]]:
    """A name with trailing project qualifiers removed: A_s.y.total -> A_s.y, A_s."""
    s = name.strip()
    base, sep, sub = s.partition("_")
    if not sep:
        return []
    parts = [p for p in re.split(r"[.,]", sub) if p]
    out = []
    for n in range(1, len(parts) + (1 if len(base) == 1 else 0)):
        dropped = parts[len(parts) - n:]
        if any(re.fullmatch(r"\d+", p) for p in dropped):
            break                      # a numbered subscript is part of the identity (k_1, z_2)
        keep = parts[:len(parts) - n]
        out.append((base + ("_" + ".".join(keep) if keep else ""), n))
    return out


class Taxonomy:
    def __init__(self, data: dict):
        self.code = data.get("code", "")
        self.branch = data.get("branch", "")
        self.title = data.get("title", "")
        self.topics: dict[str, dict] = {t["id"]: dict(t) for t in data.get("topics", [])}
        self.concepts: dict[str, Concept] = {}
        for i, c in enumerate(data.get("concepts", [])):
            c = dict(c)
            if c.get("range"):
                c["range"] = tuple(float(v) for v in c["range"])
            concept = Concept(order=i, **c)
            self.concepts[concept.id] = concept
        self.index: dict[str, list[Concept]] = {}
        self.lower: dict[str, list[Concept]] = {}
        for c in self.concepts.values():
            for k in c.keys:
                self.index.setdefault(k, []).append(c)
                self.lower.setdefault(k.lower(), []).append(c)

    # ------------------------------------------------------------------
    def topic_path(self, topic: str) -> list[dict]:
        """Chapter, section, clause ... down to the topic."""
        parts = topic.split(".")
        out = []
        for n in range(1, len(parts) + 1):
            tid = ".".join(parts[:n])
            if tid in self.topics:
                out.append(self.topics[tid])
        return out

    def topic_title(self, topic: str) -> str:
        t = self.topics.get(topic)
        return f"{topic} {t['title']}" if t else topic

    def context_topics(self, texts) -> set[str]:
        """Topics whose keywords appear in headings or sheet names."""
        blob = " ".join(texts).lower()
        found = set()
        for t in self.topics.values():
            if any(k in blob for k in t.get("keywords", [])):
                found.add(t["id"])
        return found

    def is_global(self, c: Concept) -> bool:
        return c.topic.split(".")[0] in ("2", "3") or c.topic in ("6", "7")

    # ------------------------------------------------------------------
    def resolve(self, name: str, label: str = "", clause: str = "", section=(),
                scope: str = "", argument: bool = False) -> Match | None:
        cands: dict[str, tuple[float, str]] = {}

        def add(c: Concept, score: float, how: str):
            if c.id not in cands or cands[c.id][0] < score:
                cands[c.id] = (score, how)

        key = symkey(name)
        if key:
            for c in self.index.get(key, []):
                add(c, 1.0, "symbol")
            if not cands:
                for c in self.lower.get(key.lower(), []):
                    add(c, 0.85, "symbol (ignoring case)")
            if not cands:
                for shorter, n in _drops(name):
                    hits = self.index.get(symkey(shorter), [])
                    for c in hits:
                        add(c, 0.70 - 0.05 * n, f"symbol {shorter} (qualifier dropped)")
                    if hits:
                        break
        text = (label or "").lower()
        if text:
            for c in self.concepts.values():
                if any(w and w in text for w in c.words):
                    if c.id in cands:
                        cands[c.id] = (cands[c.id][0] + 0.3, cands[c.id][1] + " + label")
                    elif not argument:
                        add(c, 0.6, "label")
        if not cands:
            return None

        # where a quantity is *used* decides its role; where it was defined does not
        ctx_clause, ctx_eq = ("", "") if argument else (clause_number(clause), eq_number(clause))
        ctx_topics = self.context_topics(section) if section and not argument else set()
        best: Match | None = None
        for cid, (score, how) in cands.items():
            c = self.concepts[cid]
            own = clause_number("cl. " + c.clause)
            if ctx_eq and c.eq and eq_number("eq. " + c.eq) == ctx_eq:
                score += 0.6
            elif ctx_clause and (related(c.topic, ctx_clause) or related(own, ctx_clause)):
                score += 0.4
            elif ctx_clause and c.topic.split(".")[:2] == ctx_clause.split(".")[:2]:
                score += 0.15                      # neighbouring clause of the same section
            elif ctx_clause and not self.is_global(c):
                score -= 0.2
            if scope:
                if c.topic == scope:
                    score += 0.45
                elif related(c.topic, scope) and not self.is_global(c):
                    score += 0.3
            if ctx_topics and any(related(c.topic, t) for t in ctx_topics) and not self.is_global(c):
                score += 0.2
            if best is None or score > best.score + 1e-9 or (abs(score - best.score) <= 1e-9
                                                             and c.order < best.concept.order):
                best = Match(c, score, how)
        threshold = 0.5 if argument else 0.9
        return best if best and best.score >= threshold - 1e-9 else None


@lru_cache(maxsize=4)
def load(path: str | None = None) -> Taxonomy:
    p = Path(path) if path else DATA
    return Taxonomy(yaml.safe_load(p.read_text(encoding="utf-8")))
