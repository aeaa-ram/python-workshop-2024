"""The machine-readable form of a source calculation.

Whatever the file type, a converted source is a ``SourceDocument``: an
ordered list of ``Statement`` objects.  A statement is one named quantity
with everything the source says about it - the formula, the value the source
shows, the unit, the descriptive text and code reference printed next to it,
and where in the file it sits.

Formulas are stored in canonical units (N, mm, MPa) and refer to other
statements by id, so a document is a dependency graph that can be
re-evaluated without the original application.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import expr as X


@dataclass
class Statement:
    id: str                       # unique in the document
    name: str                     # the name as written in the source
    kind: str = "calc"            # input | calc | printed
    expr: X.Node | None = None    # canonical-unit formula; symbols are statement ids
    raw: str = ""                 # the formula exactly as the source has it
    unit: str = ""                # unit the source shows the value in
    value: float | str | None = None       # value the source shows (canonical units)
    recomputed: float | str | None = None  # our own evaluation of the formula
    fidelity: str = "unverified"  # ok | mismatch | unverified | failed
    label: str = ""               # description next to the quantity
    clause: str = ""              # code reference printed next to it
    section: list[str] = field(default_factory=list)   # headings above it
    case: str = ""                # column / load case / phase it belongs to
    group: str = ""               # statements of one calculation run share a group
    loc: str = ""                 # where in the file
    note: str = ""
    precision: float = 0.0        # half of the last printed digit (printed values only)
    canonical: bool = False       # True: value and formula are already in N, mm, MPa

    @property
    def refs(self) -> list[str]:
        return X.symbols(self.expr) if self.expr is not None else []

    def best_value(self):
        """The value to trust: the source's own, else our recomputation."""
        return self.value if self.value is not None else self.recomputed

    def to_json(self) -> dict:
        d = asdict(self)
        d["expr"] = X.to_json(self.expr) if self.expr is not None else None
        return {k: v for k, v in d.items()
                if (v not in ("", None, [], {}, 0.0, False) or (k == "value" and v is not None)) or k in ("id", "name")}

    @classmethod
    def from_json(cls, d: dict) -> "Statement":
        d = dict(d)
        e = d.pop("expr", None)
        st = cls(**d)
        st.expr = X.from_json(e) if e else None
        return st


@dataclass
class SourceDocument:
    name: str                     # file name
    kind: str                     # mathcad | excel | pdf | python | notebook | word | scan
    sha256: str = ""
    converter: str = ""           # what did the conversion, with version
    meta: dict = field(default_factory=dict)
    statements: list[Statement] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)     # what could not be converted
    python: str = ""              # the source re-expressed as a Python script
    id: str = ""                  # short id given by the pipeline (S1, S2, ...)
    label: str = ""               # how the source is named in the knowledge base

    def by_id(self) -> dict[str, Statement]:
        return {s.id: s for s in self.statements}

    def summary(self) -> dict:
        n = len(self.statements)
        calc = [s for s in self.statements if s.kind == "calc"]
        return {
            "statements": n,
            "inputs": sum(s.kind == "input" for s in self.statements),
            "formulas": len(calc),
            "printed_values": sum(s.kind == "printed" for s in self.statements),
            "formulas_verified": sum(s.fidelity == "ok" for s in calc),
            "formulas_mismatch": sum(s.fidelity == "mismatch" for s in calc),
            "formulas_failed": sum(s.fidelity == "failed" for s in calc),
            "formulas_unverified": sum(s.fidelity == "unverified" for s in calc),
            "issues": len(self.issues),
        }

    def to_json(self) -> dict:
        return {
            "id": self.id, "label": self.label, "name": self.name, "kind": self.kind,
            "sha256": self.sha256, "converter": self.converter, "meta": self.meta,
            "summary": self.summary(), "issues": self.issues,
            "statements": [s.to_json() for s in self.statements],
        }

    @classmethod
    def from_json(cls, d: dict) -> "SourceDocument":
        doc = cls(name=d["name"], kind=d["kind"], sha256=d.get("sha256", ""),
                  converter=d.get("converter", ""), meta=d.get("meta", {}),
                  issues=d.get("issues", []), id=d.get("id", ""), label=d.get("label", ""))
        doc.statements = [Statement.from_json(s) for s in d.get("statements", [])]
        return doc

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=1, ensure_ascii=False), encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def close(a, b, rel: float = 1e-6, abs_tol: float = 1e-9) -> bool:
    """Do two values agree?  Text compares case-insensitively."""
    if isinstance(a, str) or isinstance(b, str):
        return str(a).strip().lower() == str(b).strip().lower()
    if a is None or b is None:
        return False
    try:
        return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_tol)
    except (TypeError, ValueError):
        return False


def recompute(doc: SourceDocument, rel: float = 1e-6, chained: bool = False) -> None:
    """Evaluate every formula again and compare with what the source shows.

    Each formula is evaluated from the *source's* values of the quantities it
    refers to, so one wrong cell does not hide behind another.  With
    ``chained`` the recomputed values are propagated instead (used when the
    source shows no intermediate values).
    """
    env: dict = {}
    for st in doc.statements:
        if st.kind == "printed":
            continue
        if st.expr is None:
            if st.value is not None:
                env[st.id] = st.value
            continue
        try:
            st.recomputed = X.evaluate(st.expr, env)
        except X.ExprError as exc:
            st.fidelity = "failed"
            st.note = (st.note + " " if st.note else "") + f"not evaluated: {exc}"
            if st.value is not None:
                env[st.id] = st.value
            continue
        if isinstance(st.recomputed, bool):
            st.recomputed = float(st.recomputed)
        if st.value is None:
            st.fidelity = "unverified"
            env[st.id] = st.recomputed
        else:
            st.fidelity = "ok" if close(st.recomputed, st.value, rel) else "mismatch"
            env[st.id] = st.recomputed if chained else st.value
