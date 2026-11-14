"""The registry: design codes, their clause structure, their quantities and formulas.

It is loaded from ``data/common.yaml`` (quantities that belong to no single code) and
``data/codes/*.yaml`` (one file per design code).  It answers two questions:

* ``resolve`` - which quantity is this name?  The evidence is, in this order, the
  symbol (compared without separators), the same symbol with a project qualifier
  dropped (``d_c`` -> ``d``), and the words of the descriptive label.  A symbol that
  means different things in different clauses (``k_1`` in shear and in crack width)
  is decided by context: the clause printed next to it, the heading it stands under,
  and the clause of the formula that uses it.

* which object already holds this expression?  When a second code states a formula
  the registry compares it with every existing object.  The same expression becomes a
  reference to the existing object; a special case of it (EN 1994-1-1 f_cd = f_ck/γ_C
  is EN 1992-1-1 f_cd with α_cc = 1) shares the object and records the fixed value for
  that code.  Nothing is calculated twice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .. import expr as X
from .. import units as U
from ..notation import mathml, pretty, symkey

DATA = Path(__file__).resolve().parent.parent / "data"


class RegistryError(Exception):
    pass


@dataclass
class Concept:
    id: str
    name: str = ""
    kind: str = "input"              # input | coefficient | derived
    code: str | None = None          # the code that defines it (None: common quantity)
    topic: str = ""
    var: str = ""                    # identifier used in generated code
    symbol: str = ""                 # display form, e.g. "V_{Rd,c}"
    clause: str = ""
    eq: str = ""
    unit: str = "-"
    range: tuple | None = None       # in the usual unit
    example: float | None = None     # in the usual unit
    value: float | None = None       # recommended value of a coefficient, usual unit
    choices: list = field(default_factory=list)
    ndp: bool = False
    basis: str = ""                  # code | mechanics | definition
    formula: str = ""
    alternatives: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    background: list = field(default_factory=list)
    inverse: dict = field(default_factory=dict)
    sense: str = ""                  # resistance | effect
    aliases: list[str] = field(default_factory=list)
    words: list[str] = field(default_factory=list)
    ref: str = ""
    check: str = ""
    strip: bool = False              # a width: per-unit-width sources leave it out
    context: list = field(default_factory=list)    # clauses where this is the usual reading of the symbol
    order: int = 0
    refs: list = field(default_factory=list)       # every code that uses it: {code, clause, eq, topic, symbol, how}
    fixed_by: dict = field(default_factory=dict)   # code -> {quantity: value} that code fixes

    def __post_init__(self):
        self.var = self.var or self.id
        info = U.parse_unit(self.unit)
        self.unit, self.factor, self.dims = info.text, info.factor, info.dims
        self.words = [w.lower() for w in self.words]
        self.keys = {symkey(a) for a in self.aliases + [self.id, self.var]}
        if self.range:
            self.range = tuple(float(v) for v in self.range)
        self._tree = None

    @property
    def tree(self) -> X.Node | None:
        if self.formula and self._tree is None:
            self._tree = X.parse(self.formula)
        return self._tree if self.formula else None

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
    def canonical_value(self) -> float | None:
        return None if self.value is None else self.value * self.factor

    @property
    def canonical_example(self) -> float | None:
        if self.example is not None:
            return self.example * self.factor
        return self.canonical_value

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
    m = re.search(r"(\d+(?:\.\d+)+|\b\d+\b)(?=\s*(?:\(|$|,))", text.split("cl.")[-1])
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
    """All codes and quantities.  (Kept under its historical name.)"""

    def __init__(self, common: dict, codes: list[dict]):
        self.references = {r["id"]: r["text"] for r in common.get("references", [])}
        self.concepts: dict[str, Concept] = {}
        self.codes: list[dict] = []
        self.topics: dict[tuple, dict] = {}         # (code, topic id) -> topic
        self.id_alias: dict[str, str] = {}          # an id one code uses for another code's object
        self.links: list[dict] = []                 # how each code's formulas were linked
        order = 0
        for q in common.get("quantities", []):
            self._add(dict(q), None, order)
            order += 1
        pending = []
        for data in sorted(codes, key=lambda d: d.get("order", 99)):
            code = data["code"]
            self.codes.append({k: data.get(k, "") for k in ("code", "title", "edition", "values")})
            for t in data.get("topics", []):
                self.topics[(code, t["id"])] = dict(t, code=code)
            for q in data.get("quantities", []):
                q = dict(q)
                if q.get("same_as"):
                    target = self.concepts.get(q["same_as"])
                    if target is None:
                        raise RegistryError(f"{code}: {q['id']} refers to unknown object {q['same_as']!r}")
                    target.refs.append({"code": code, "clause": q.get("clause", ""), "eq": q.get("eq", ""),
                                        "topic": q.get("topic", ""), "symbol": target.text, "how": "same object"})
                    self.links.append({"code": code, "id": q["id"], "target": target.id, "how": "same object (declared)"})
                    continue
                if q.get("formula") and (q["id"] in self.concepts or "unit" not in q):
                    pending.append((code, q))            # compare with what exists before creating anything
                    continue
                self._add(q, code, order)
                order += 1
        for code, q in pending:
            self._link(code, q, order)
            order += 1
        # formulas use the ids of the shared objects
        if self.id_alias:
            for c in self.concepts.values():
                if c.formula:
                    tree = X.substitute(c.tree, dict(self.id_alias))
                    c.formula, c._tree = X.to_python(tree), tree
        self._check_formulas()
        self.index: dict[str, list[Concept]] = {}
        self.lower: dict[str, list[Concept]] = {}
        for c in self.concepts.values():
            for k in c.keys:
                self.index.setdefault(k, []).append(c)
                self.lower.setdefault(k.lower(), []).append(c)

    # ------------------------------------------------------------------
    def _add(self, q: dict, code: str | None, order: int) -> Concept:
        if q["id"] in self.concepts:
            raise RegistryError(f"{code or 'common'}: quantity {q['id']!r} is defined twice")
        fields = {k: v for k, v in q.items() if k in Concept.__dataclass_fields__}
        c = Concept(order=order, code=code, **fields)
        if code:
            c.refs.append({"code": code, "clause": c.clause, "eq": c.eq, "topic": c.topic, "symbol": c.text,
                           "how": "defined here"})
        self.concepts[c.id] = c
        return c

    def _link(self, code: str, q: dict, order: int) -> None:
        """A formula of a later code: reuse an existing object if it holds the same logic."""
        from .consolidate import Merger, Variant, is_special_case, equivalent

        tree = X.substitute(X.parse(q["formula"]), dict(self.id_alias))
        syms = set(X.symbols(tree))
        cands = [c for c in self.concepts.values() if c.formula and c.kind == "derived"]
        cands.sort(key=lambda c: (c.id != q["id"], c.order))     # same id first
        merger = Merger(self)
        for c in cands:
            if "unit" in q and U.parse_unit(q["unit"]).dims != c.dims:
                continue
            same = set(X.symbols(c.tree)) == syms and (X.same(c.tree, tree) or equivalent(c.tree, tree, self, {}))
            fixed = {}
            if not same:
                d_new, d_old = [], []
                if merger.merge(c.tree, tree, d_old, d_new) is None or d_old:
                    continue
                if any(d.kind not in ("literal", "factor") for d in d_new):
                    continue
                if not is_special_case(c.tree, Variant(tree, [], d_new), self, {}):
                    continue
                fixed = {d.sym: (d.value if d.kind == "literal" else 1.0) for d in d_new}
            how = "same expression" if not fixed else "special case: " + ", ".join(
                f"{self.concepts[k].text} = {X._short(v)}" for k, v in fixed.items())
            if q["id"] != c.id:
                self.id_alias[q["id"]] = c.id
                for a in [q["id"]] + list(q.get("aliases", [])):
                    c.keys.add(symkey(a))
            symbol = pretty(q["id"], q.get("symbol", "")) if q.get("symbol") or q["id"] != c.id else c.text
            c.refs.append({"code": code, "clause": q.get("clause", ""), "eq": q.get("eq", ""),
                           "topic": q.get("topic", ""), "symbol": symbol, "how": how})
            if fixed:
                c.fixed_by.setdefault(code, {}).update(fixed)
            self.links.append({"code": code, "id": q["id"], "target": c.id, "how": how})
            return
        if "unit" not in q:
            raise RegistryError(f"{code}: {q['id']} = {q['formula']} matches no existing object; "
                                "give its name, unit and range to define it as a new one")
        self._add(q, code, order)

    def _check_formulas(self) -> None:
        for c in self.concepts.values():
            if not c.formula:
                continue
            unknown = [s for s in X.symbols(c.tree) if s not in self.concepts]
            if unknown:
                raise RegistryError(f"{c.code}: formula of {c.id} uses unknown quantities {unknown}")

    # ------------------------------------------------------------------
    def code_meta(self, code: str | None) -> dict:
        return next((c for c in self.codes if c["code"] == code), {})

    def fixed_for(self, code: str | None) -> dict:
        """Values a code fixes in objects it shares with other codes."""
        out = {}
        for c in self.concepts.values():
            out.update(c.fixed_by.get(code, {}))
        return out

    def topic_path(self, topic: str, code: str | None = None) -> list[dict]:
        """Chapter, section, clause ... down to the topic."""
        parts = topic.split(".")
        out = []
        for n in range(1, len(parts) + 1):
            tid = ".".join(parts[:n])
            t = self.topics.get((code, tid))
            if t is not None:
                out.append(t)
        return out

    def context_topics(self, texts) -> set[str]:
        """Topics whose keywords appear in headings or sheet names."""
        blob = " ".join(texts).lower()
        found = set()
        for (code, tid), t in self.topics.items():
            if any(k in blob for k in t.get("keywords", [])):
                found.add(tid)
        return found

    def is_global(self, c: Concept) -> bool:
        return c.code is None or c.topic.split(".")[0] in ("2", "3") or c.topic in ("6", "7")

    def dependencies(self, cid: str) -> list[str]:
        """Every quantity an object needs, recursively, in evaluation order."""
        out: list[str] = []

        def walk(q: str, trail: tuple):
            if q in out or q in trail:
                return
            c = self.concepts.get(q)
            if c is not None and c.formula:
                for s in X.symbols(c.tree):
                    walk(s, trail + (q,))
            out.append(q)

        walk(cid, ())
        return out

    def inline(self, tree: X.Node, keep: set[str], wanted: set[str] | None = None) -> X.Node:
        """Replace derived quantities not in ``keep`` by their formulas (one level).

        With ``wanted``, only those whose formula brings in a wanted symbol are replaced:
        f_yd is expanded to meet a source that writes f_yk/γ_S, but η is left alone when
        the other side simply has no η.
        """
        mapping = {}
        for s in X.symbols(tree):
            c = self.concepts.get(s)
            if s in keep or c is None or not c.formula:
                continue
            if wanted is not None and not (set(self.dependencies(s)) & wanted):
                continue
            mapping[s] = c.tree
        return X.substitute(tree, mapping) if mapping else tree

    def synonyms(self, a: str, b: str) -> bool:
        """Can a source's ``a`` be the code's ``b``?  (A_s and A_sl, b and b_w, f_yk and f_ywk.)"""
        ca, cb = self.concepts.get(a), self.concepts.get(b)
        return ca is not None and cb is not None and a != b and bool(ca.keys & cb.keys) and ca.dims == cb.dims

    # ------------------------------------------------------------------
    def resolve(self, name: str, label: str = "", clause: str = "", section=(),
                scope=None, argument: bool = False) -> Match | None:
        """``scope`` is the concept (or topic id) of the formula that uses the quantity."""
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

        scope_topic, scope_code = (scope.topic, scope.code) if isinstance(scope, Concept) else (scope or "", None)
        # where a quantity is *used* decides its role; where it was defined does not
        ctx_clause, ctx_eq = ("", "") if argument else (clause_number(clause), eq_number(clause))
        ctx_topics = self.context_topics(section) if section and not argument else set()
        best: Match | None = None
        for cid, (score, how) in cands.items():
            c = self.concepts[cid]
            own = clause_number("cl. " + c.clause)
            if ctx_eq and c.eq and any(eq_number("eq. " + e.strip()) == ctx_eq for e in c.eq.split(",")):
                score += 0.6
            elif ctx_clause and (related(c.topic, ctx_clause) or related(own, ctx_clause)):
                score += 0.4
            elif ctx_clause and c.topic.split(".")[:2] == ctx_clause.split(".")[:2]:
                score += 0.15                      # neighbouring clause of the same section
            elif ctx_clause and not self.is_global(c):
                score -= 0.2
            if scope_topic and (scope_code is None or c.code in (scope_code, None)):
                if c.topic == scope_topic:
                    score += 0.45
                elif related(c.topic, scope_topic) and not self.is_global(c):
                    score += 0.3
                elif any(related(t, scope_topic) for t in c.context):
                    score += 0.4
            if ctx_topics and any(related(c.topic, t) for t in ctx_topics) and not self.is_global(c):
                score += 0.2
            if best is None or score > best.score + 1e-9 or (abs(score - best.score) <= 1e-9
                                                             and c.order < best.concept.order):
                best = Match(c, score, how)
        threshold = 0.5 if argument else 0.9
        return best if best and best.score >= threshold - 1e-9 else None


def read_data(root: Path = DATA) -> tuple[dict, list[dict]]:
    common = yaml.safe_load((root / "common.yaml").read_text(encoding="utf-8"))
    codes = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((root / "codes").glob("*.yaml"))]
    return common, codes


@lru_cache(maxsize=4)
def load(path: str | None = None) -> Taxonomy:
    common, codes = read_data(Path(path) if path else DATA)
    return Taxonomy(common, codes)
