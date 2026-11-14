"""Stage 3 - decomposition: from statements to instances of code quantities.

Every statement of a converted source is asked which quantity of the code it
is.  A statement that calculates a code-defined quantity becomes an
*instance*: the formula rewritten in consistent units (N, mm, MPa) with the
code's own symbols, together with the numbers the source used and the result
it got.  That instance is a variant to consolidate and, at the same time, a
benchmark the consolidated logic must reproduce.

Whatever is not recognised is kept and listed - it is project-specific logic,
or a topic the taxonomy does not yet cover.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import expr as X
from .. import units as U
from ..ir import SourceDocument, Statement, close
from ..notation import ident
from .taxonomy import Concept, Taxonomy

LOCAL = "~"        # prefix of a symbol that is not a quantity of the taxonomy


@dataclass
class Instance:
    concept: str
    doc: str                       # source id
    stmt: str                      # statement id in that source
    kind: str                      # formula | printed
    value: float | str | None      # the source's result, canonical units
    formula: X.Node | None = None  # canonical units; symbols are concept ids or ~local names
    args: dict = field(default_factory=dict)   # symbol -> {"value", "stmt", "name"}
    unit: str = ""                 # unit the source shows the result in
    precision: float = 0.0         # canonical; half the last printed digit
    loc: str = ""
    case: str = ""
    section: list = field(default_factory=list)
    clause: str = ""
    name: str = ""                 # the name used in the source
    how: str = ""                  # how the quantity was recognised
    per_width: bool = False        # the source works per unit width (kN/m, mm²/m)
    notes: list = field(default_factory=list)

    @property
    def locals(self) -> list[str]:
        return [s for s in (X.symbols(self.formula) if self.formula is not None else []) if s.startswith(LOCAL)]

    def to_json(self) -> dict:
        return {
            "concept": self.concept, "doc": self.doc, "stmt": self.stmt, "kind": self.kind,
            "name": self.name, "value": self.value, "unit": self.unit, "precision": self.precision,
            "formula": X.to_python(self.formula) if self.formula is not None else None,
            "args": {k: v["value"] for k, v in self.args.items()},
            "loc": self.loc, "case": self.case, "section": self.section, "clause": self.clause,
            "how": self.how, "per_width": self.per_width, "notes": self.notes,
        }


@dataclass
class Decomposition:
    doc: SourceDocument
    producer: dict[str, tuple[Concept, str]] = field(default_factory=dict)  # stmt id -> (concept, how)
    instances: list[Instance] = field(default_factory=list)
    observations: dict[str, list] = field(default_factory=dict)             # concept -> values seen
    unmapped: list[Statement] = field(default_factory=list)                 # calculated, not recognised
    glue: list[Statement] = field(default_factory=list)                     # formulas for input quantities
    issues: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        calc = [s for s in self.doc.statements if s.kind in ("calc", "printed")]
        return {
            "statements": len(self.doc.statements),
            "recognised": len(self.producer),
            "instances_with_formula": sum(i.kind == "formula" for i in self.instances),
            "printed_values": sum(i.kind == "printed" for i in self.instances),
            "project_specific_formulas": len(self.glue),
            "not_recognised": len(self.unmapped),
            "calculated_or_printed": len(calc),
        }


def unit_factor(st: Statement, concept: Concept | None) -> tuple[float, bool, tuple | None]:
    """Factor from the statement's number to canonical units.

    Returns (factor, assumed, dims): ``assumed`` is True when the source states
    no unit and the customary unit of the quantity was taken.
    """
    if st.canonical:
        dims = None
        if st.unit:
            try:
                dims = U.parse_unit(st.unit).dims
            except U.UnitError:
                pass
        return 1.0, False, dims
    if st.unit:
        try:
            info = U.parse_unit(st.unit)
            return info.factor, False, info.dims
        except U.UnitError:
            pass
    if concept is not None:
        return concept.factor, concept.unit != "-", None
    return 1.0, False, None


def canonical_value(st: Statement, concept: Concept | None):
    v = st.best_value()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v * unit_factor(st, concept)[0]
    return v


def decompose(doc: SourceDocument, tax: Taxonomy) -> Decomposition:
    out = Decomposition(doc)
    by_id = doc.by_id()

    # ---- which quantity does each statement define? -------------------------
    for st in doc.statements:
        m = tax.resolve(st.name, st.label, st.clause, st.section)
        if m is not None and _plausible(st, m.concept, m.how):
            out.producer[st.id] = (m.concept, m.how)

    for st in doc.statements:
        hit = out.producer.get(st.id)
        if hit is None:
            if st.kind == "calc" and st.expr is not None:
                out.unmapped.append(st)
            continue
        concept, how = hit
        value = canonical_value(st, concept)
        factor, assumed, dims = unit_factor(st, concept)
        if isinstance(value, (int, float)) and (dims is None or tuple(dims) == tuple(concept.dims)):
            out.observations.setdefault(concept.id, []).append(value)     # per-unit-width values excluded

        if st.kind == "printed":
            inst = Instance(concept.id, doc.id, st.id, "printed", value, unit=st.unit or concept.unit,
                            precision=st.precision * factor, loc=st.loc, case=st.case,
                            section=st.section, clause=st.clause, name=st.name, how=how)
            if dims is not None and tuple(dims) != tuple(concept.dims):
                if _per_width(dims, concept.dims):
                    inst.per_width = True
                else:
                    inst.notes.append(f"unit {st.unit} does not fit {concept.text} [{concept.unit}]")
                    out.issues.append(f"{st.loc}: {st.name}: unit {st.unit} does not fit {concept.text}")
                    continue
            out.instances.append(inst)
            continue
        if st.kind == "input" and concept.formula and isinstance(value, (int, float)) \
                and isinstance(st.expr, X.Num) and not inst_dims_mismatch(dims, concept):
            # a value the source typed for a quantity the code calculates (E_cm = 34 GPa):
            # checked like a printed value, within the digits it was typed with
            digits = re.sub(r"[^0-9.]", "", (st.expr.text or "").split(" ")[0])
            dec = len(digits.split(".")[1]) if "." in digits else 0
            try:
                factor = U.parse_unit(st.unit).factor if st.unit else concept.factor
            except U.UnitError:
                factor = concept.factor
            out.instances.append(Instance(concept.id, doc.id, st.id, "printed", value, unit=st.unit or concept.unit,
                                          precision=0.5 * 10 ** (-dec) * factor, loc=st.loc, case=st.case,
                                          section=st.section, clause=st.clause, name=st.name, how=how,
                                          notes=["value typed in the source"]))
            continue
        if st.expr is None or st.kind == "input" or isinstance(st.expr, (X.Num, X.Str)):
            continue
        if concept.kind != "derived":
            out.glue.append(st)                 # e.g. d = h - cover - bar/2 : project geometry
            continue
        if st.fidelity in ("mismatch", "failed"):
            out.issues.append(f"{st.loc}: {st.name}: formula not used (it does not reproduce the source value)")
            continue

        # ---- the formula in consistent units with the code's symbols --------
        inst = Instance(concept.id, doc.id, st.id, "formula", value, unit=st.unit or concept.unit,
                        loc=st.loc, case=st.case, section=st.section, clause=st.clause,
                        name=st.name, how=how)
        if assumed:
            inst.notes.append(f"no unit stated; taken as {concept.unit}")
        if dims is not None and tuple(dims) != tuple(concept.dims):
            if _per_width(dims, concept.dims):
                inst.per_width = True
                inst.notes.append(f"per unit width ({st.unit})")
            else:
                out.issues.append(f"{st.loc}: {st.name}: unit {st.unit} does not fit {concept.text} [{concept.unit}]")
                continue
        mapping: dict[str, X.Node] = {}
        taken: dict[str, str] = {}
        for rid in st.refs:
            r = by_id[rid]
            role = tax.resolve(r.name, r.label, r.clause, r.section, scope=concept, argument=True)
            rc = role.concept if role else None
            if rc is None and rid in out.producer:
                rc = out.producer[rid][0]
            if rc is not None and (rc.id == concept.id or rc.id in taken):
                rc = None                       # the same quantity twice: keep them apart
            sym = rc.id if rc is not None else LOCAL + ident(r.name or rid)
            n = 2
            while sym in taken:
                sym = f"{LOCAL}{ident(r.name or rid)}_{n}"
                n += 1
            taken[sym] = rid
            f_r, r_assumed, r_dims = unit_factor(r, rc)
            if rc is not None and r_dims is not None and tuple(r_dims) != tuple(rc.dims):
                if _per_width(r_dims, rc.dims):
                    inst.per_width = True
                else:
                    inst.notes.append(f"{r.name} [{r.unit}] used as {rc.text} [{rc.unit}]")
            if r_assumed:
                inst.notes.append(f"{r.name}: no unit stated; taken as {rc.unit}")
            node: X.Node = X.Sym(sym)
            if not st.canonical and not _is_one(f_r):
                node = X.Bin("/", node, X.Num(f_r, conv=True))
            mapping[rid] = node
            v = r.best_value()
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                v = v * f_r
            inst.args[sym] = {"value": v, "stmt": rid, "name": r.name}
        tree = X.substitute(st.expr, mapping)
        if not st.canonical and not _is_one(factor):
            tree = X.Bin("*", tree, X.Num(factor, conv=True))
        inst.formula = tidy(X.fold(tree))
        # the rewritten formula must still give the source's number
        try:
            got = X.evaluate(inst.formula, {k: v["value"] for k, v in inst.args.items()})
            if not close(got, value, rel=1e-9):
                out.issues.append(f"{st.loc}: {st.name}: rewriting to consistent units changed the result "
                                  f"({got!r} vs {value!r}); not used")
                continue
        except X.ExprError as exc:
            out.issues.append(f"{st.loc}: {st.name}: {exc}; not used")
            continue
        out.instances.append(inst)
    return out


def _plausible(st: Statement, concept: Concept, how: str) -> bool:
    """Reject a match the value itself contradicts (a text result, a wrong
    dimension, or - for weak evidence - a number far outside the usual range)."""
    v = st.best_value()
    if isinstance(v, str):
        return False
    factor, _assumed, dims = unit_factor(st, concept)
    if dims is not None and tuple(dims) != tuple(concept.dims):
        return _per_width(dims, concept.dims)
    weak = how.startswith("label") or "qualifier dropped" in how
    rng = concept.canonical_range
    if weak and rng and isinstance(v, (int, float)):
        cv = abs(v * factor)
        lo, hi = min(abs(rng[0]), abs(rng[1])), max(abs(rng[0]), abs(rng[1]))
        if cv > hi * 4 or (lo > 0 and cv < lo / 4 and cv != 0):
            return False
    return True


def inst_dims_mismatch(dims, concept: Concept) -> bool:
    return dims is not None and tuple(dims) != tuple(concept.dims)


def _is_one(f: float) -> bool:
    return abs(f - 1.0) < 1e-12


def _per_width(dims, concept_dims) -> bool:
    """kN/m for a force, mm²/m for an area: the quantity per unit width."""
    d = tuple(dims)
    c = tuple(concept_dims)
    return d == (c[0], c[1] - 1, c[2], c[3])


def tidy(n: X.Node) -> X.Node:
    """Remove what carries no information: ``x * 1``, ``+x``, ``1 * x``."""
    def rep(x: X.Node):
        if isinstance(x, X.Bin) and x.op == "*":
            if isinstance(x.right, X.Num) and x.right.value == 1 and " " not in x.right.text:
                return x.left
            if isinstance(x.left, X.Num) and x.left.value == 1 and " " not in x.left.text:
                return x.right
        if isinstance(x, X.Bin) and x.op == "/" and isinstance(x.right, X.Num) and x.right.value == 1:
            return x.left
        if isinstance(x, X.Bin) and x.op == "**" and isinstance(x.right, X.Num) and x.right.value == 0.5 \
                and not isinstance(x.left, X.Sym):
            return X.Call("sqrt", (x.left,))                  # (200 / d) ** 0.5  ->  sqrt(200 / d)
        if isinstance(x, X.Bin) and x.op == "*" and isinstance(x.right, X.Bin) and x.right.op == "/" \
                and isinstance(x.right.left, X.Num) and x.right.left.value == 1 and " " not in x.right.left.text:
            return X.Bin("/", x.left, x.right.right)          # a * (1 / b)  ->  a / b
        return None

    return X.transform(n, rep)
