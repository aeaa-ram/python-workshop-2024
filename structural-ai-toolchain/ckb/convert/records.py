"""Build a source document from a list of transcribed quantities.

Used wherever a calculation arrives as text rather than as live formulas: a
Word report, a scan or handwritten sheet transcribed by a vision model, or a
PDF whose formulas a model has read.  Each record is

    {"name", "formula", "value", "unit", "label", "clause", "section"}

Nothing in a record is trusted.  A formula is accepted only if it reproduces
the stated value from the stated inputs - tried first in consistent units
(N, mm, MPa; how a hand calculation or Mathcad sheet works) and then with the
numbers exactly as written (how a spreadsheet works).
"""
from __future__ import annotations

from .. import expr as X
from .. import units as U
from ..ir import SourceDocument, Statement, close
from ..notation import ident


def build_from_records(doc: SourceDocument, records: list[dict], id_prefix: str = "q",
                       rel: float = 2e-3) -> SourceDocument:
    latest: dict[str, str] = {}       # identifier -> statement id
    by_id: dict[str, Statement] = {}
    for n, rec in enumerate(records, 1):
        name = str(rec.get("name") or "").strip()
        if not name:
            continue
        st = Statement(id=f"{id_prefix}{n}", name=name, label=str(rec.get("label") or ""),
                       clause=str(rec.get("clause") or ""), loc=str(rec.get("loc") or ""),
                       section=[s for s in (rec.get("section") or []) if s]
                       if isinstance(rec.get("section"), list) else [str(rec["section"])] if rec.get("section") else [],
                       case=str(rec.get("case") or ""), kind="printed")
        unit = str(rec.get("unit") or "").strip()
        factor = 1.0
        if unit:
            try:
                info = U.parse_unit(unit)
                st.unit, factor = info.text, info.factor
            except U.UnitError:
                doc.issues.append(f"{name}: unit {unit!r} not understood")
        value = rec.get("value")
        if isinstance(value, str):
            try:
                value = float(value.replace(",", "."))
            except ValueError:
                pass
        st.value = value
        st.precision = float(rec.get("precision") or 0.0)
        formula = str(rec.get("formula") or "").strip()
        if formula:
            st.raw = formula
            try:
                tree = X.substitute(X.parse(formula), dict(latest))
                unknown = [s for s in X.symbols(tree) if s not in by_id]
                if unknown:
                    raise X.ExprError(f"refers to {unknown[0]!r}, which is not defined above")
                st.expr = tree
                st.kind = "input" if not X.symbols(tree) else "calc"
            except X.ExprError as exc:
                st.note = f"formula not converted: {exc}"
                doc.issues.append(f"{name}: {exc}")
        if st.expr is not None and st.kind == "calc":
            _verify(st, by_id, factor, rel)
        elif st.expr is not None and st.kind == "input" and st.value is None:
            try:
                st.value = X.evaluate(st.expr, {})
            except X.ExprError:
                pass
        elif st.expr is None and isinstance(st.value, (int, float)) and not formula:
            st.kind = "printed"
        doc.statements.append(st)
        by_id[st.id] = st
        latest[ident(name)] = st.id
        if rec.get("var"):
            latest[str(rec["var"])] = st.id
    return doc


def _verify(st: Statement, by_id: dict[str, Statement], factor: float, rel: float) -> None:
    """Accept the formula only if it reproduces the stated value."""
    def canon(s: Statement):
        if s.canonical or not isinstance(s.value, (int, float)):
            return s.value
        try:
            return s.value * (U.parse_unit(s.unit).factor if s.unit else 1.0)
        except U.UnitError:
            return s.value

    refs = [by_id[r] for r in st.refs]
    stated = st.value
    tol = max(rel, (st.precision / abs(stated)) if isinstance(stated, (int, float)) and stated else 0)
    # 1) consistent units
    try:
        got = X.evaluate(st.expr, {r.id: canon(r) for r in refs})
        if stated is None:
            st.recomputed, st.fidelity, st.canonical = got, "unverified", True
            st.value = got
            return
        target = stated * factor if isinstance(stated, (int, float)) else stated
        if close(got, target, rel=tol):
            st.recomputed, st.fidelity, st.canonical = got, "ok", True
            st.value = target
            return
    except X.ExprError:
        got = None
    # 2) numbers exactly as written
    try:
        raw = X.evaluate(st.expr, {r.id: (r.value / (U.parse_unit(r.unit).factor if r.unit else 1.0)
                                          if r.canonical and isinstance(r.value, (int, float)) else r.value)
                                   for r in refs})
        if close(raw, stated, rel=tol):
            st.recomputed, st.fidelity, st.canonical = raw, "ok", False
            return
        st.recomputed = got if got is not None else raw
    except X.ExprError as exc:
        st.note = f"not evaluated: {exc}"
    st.fidelity = "mismatch"
    st.note = (st.note + "; " if st.note else "") + "formula does not reproduce the stated value"
