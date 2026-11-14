"""Running a calculation object: inputs in engineering units, a traced result out.

``run`` is the one entry point behind every way of using the knowledge base - the
web calculator shows the same steps, the reports print them, the terminal prompt
asks for the same inputs, an AI assistant calls it as a tool.  A result carries the
design logic only: every step with its clause, the applicability checks, and the
scope and limitations of the objects used.  Evidence about sources stays out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import expr as X
from .. import units as U
from ..kb.objects import KnowledgeBase, ResolveError
from ..notation import symkey
from .style import Style


@dataclass
class Line:
    id: str
    text: str                  # symbol as text
    name: str
    reference: str
    value: float | str         # canonical
    shown: float | str         # in the display unit
    unit: str                  # display unit
    formula: X.Node | None = None
    env: dict = field(default_factory=dict)
    source: str = ""           # inputs: entered | recommended | example | given | fixed


@dataclass
class Result:
    target: str
    inputs: list[Line]
    steps: list[Line]
    value: float | str
    shown: float | str
    unit: str
    style: Style = field(default_factory=Style)
    check: dict | None = None
    checks: list = field(default_factory=list)        # applicability checks
    limitations: list = field(default_factory=list)   # scope and limitations of the objects used
    warnings: list = field(default_factory=list)      # inputs outside the usual range, violated checks

    def env(self) -> dict:
        out = {ln.id: ln.value for ln in self.inputs}
        out.update({ln.id: ln.value for ln in self.steps})
        return out


def lookup(kb: KnowledgeBase, name: str, among=None) -> str | None:
    """Find an object or parameter by id, code name or symbol (V_Rd,c / VRd.c / V_Rd_c)."""
    pool = list(among) if among is not None else list(kb.objects) + list(kb.quantities)
    if name in pool:
        return name
    key = symkey(name)
    for sid in pool:
        if key in (symkey(sid), symkey(kb.var(sid)), symkey(kb.name(sid))):
            return sid
    low = key.lower()
    hits = [sid for sid in pool if low in (symkey(sid).lower(), symkey(kb.var(sid)).lower(), symkey(kb.name(sid)).lower())]
    return hits[0] if len(hits) == 1 else None


def parse_assignments(kb: KnowledgeBase, target: str, pairs: list[str], given=()) -> tuple[dict, list[str]]:
    """``["d=491.5", "f_ck=35 MPa", "b_w=0.5 m"]`` -> canonical values.

    A value without a unit is in the quantity's usual unit.  Naming an
    intermediate quantity (``k=1.6``) fixes it instead of calculating it.
    Returns (values, given).
    """
    values: dict = {}
    given = list(given)
    steps, _ = kb.plan(target)
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"expected name=value, got {pair!r}")
        raw, _, val = pair.partition("=")
        m = re.fullmatch(r"\s*([-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)\s*(.*?)\s*", val)
        if not m:
            raise ValueError(f"{pair!r}: {val!r} is not a number")
        sid = lookup(kb, raw.strip())
        if sid is None:
            raise ValueError(f"{raw.strip()!r} is not a quantity of this calculation")
        number = float(m.group(1).replace(",", "."))
        unit = m.group(2) or kb.unit(sid)
        try:
            info = U.parse_unit(unit)
            want = U.parse_unit(kb.unit(sid))
        except U.UnitError as exc:
            raise ValueError(f"{pair!r}: {exc}") from exc
        if tuple(info.dims) != tuple(want.dims):
            raise ValueError(f"{pair!r}: {kb.name(sid)} is in {kb.unit(sid)}, not {unit}")
        values[sid] = number * info.factor
        if sid in steps and sid != target and sid not in given:
            given.append(sid)
    return values, given


def starting_values(kb: KnowledgeBase, target: str, given=()) -> tuple[dict, dict]:
    """Recommended values for coefficients, example values for everything else."""
    values, origin = {}, {}
    for p, v in kb.defaults(target, given).items():
        values[p] = v
        q = kb.quantities.get(p)
        origin[p] = "recommended" if q is not None and q.kind == "coefficient" else "example"
    return values, origin


def run(kb: KnowledgeBase, target: str, values: dict, given=(), origin: dict | None = None,
        check_value: float | None = None, style: Style | None = None) -> Result:
    """Evaluate ``target`` from canonical ``values`` and return every step."""
    style = style or Style()
    origin = origin or {}
    value, trace = kb.evaluate(target, values, given)
    _, inputs = kb.plan(target, given)
    obj = kb.objects[target]

    def line(sid: str, v, **kw) -> Line:
        item = kb.item(sid)
        ref = ""
        if sid in kb.objects:
            ref = kb.objects[sid].reference_text
        elif item is not None and getattr(item, "clause", ""):
            c = item.clause
            code = item.code or ""
            ref = f"{code} " + (c if c.lower().startswith(("table", "fig")) else f"cl. {c}")
        return Line(sid, kb.name(sid), item.name if item else sid, ref.strip(), v, style.show(kb, sid, v),
                    style.unit(kb, sid), **kw)

    res = Result(target, [], [], value, style.show(kb, target, value), style.unit(kb, target), style=style)
    for p in inputs:
        res.inputs.append(line(p, values[p], source="given" if p in given else origin.get(p, "entered")))
    for k, v in obj.fixed.items():
        res.inputs.append(line(k, v, source="fixed"))
    for step in trace:
        o = kb.objects[step.id]
        res.steps.append(line(step.id, step.value, formula=o.tree, env=step.env))
        for text in o.limitations:
            res.limitations.append(f"{o.text}: {text}")
    env = res.env()
    res.checks = kb.checks_for(target, env, given)
    for c in res.checks:
        if c["status"] == "violated":
            res.warnings.append(f"Not met: {c['text']} ({c['clause']}).")
    for ln in res.inputs:
        q = kb.quantities.get(ln.id)
        if q is not None and q.range and isinstance(ln.value, (int, float)):
            lo, hi = q.range
            if not (lo - 1e-9 <= ln.value <= hi + 1e-9):
                res.warnings.append(
                    f"{ln.text} = {style.fmt(ln.shown)} {ln.unit} is outside the usual range "
                    f"{style.fmt(style.show(kb, ln.id, lo))} to {style.fmt(style.show(kb, ln.id, hi))} {ln.unit}.")
    if obj.check and check_value is not None and isinstance(value, (int, float)) and value != 0:
        demand_is_action = obj.sense == "resistance"
        ratio = (check_value / value) if demand_is_action else (value / check_value)
        res.check = {"against": obj.check, "text": kb.name(obj.check), "value": check_value,
                     "shown": style.show(kb, obj.check, check_value), "unit": style.unit(kb, obj.check),
                     "utilisation": ratio, "ok": ratio <= 1.0,
                     "expression": (f"{kb.name(obj.check)} / {obj.text}" if demand_is_action
                                    else f"{obj.text} / {kb.name(obj.check)}")}
    return res
