"""Dimensional analysis over a formula's expression tree.

Every unit in ``units.py`` carries a dimension vector over (Force,
Length). Walking the sympy tree with those vectors answers two questions
the master reviewer cares about:

1. Is the formula *homogeneous*? ``a + b`` with a in N and b in mm is a
   real error; ``1 + sqrt(200/d)`` (EN 1992-1-1 6.2.2) is a deliberate
   *empirical* formula that only holds in the code's own units.
2. What dimension does the result have, and does it match the unit the
   sheet declares for it? A stress formula labelled kN is caught here,
   whatever the numbers look like.

Unknown units (empty labels from legacy Excel) make a sub-tree "unknown"
rather than wrong, so the check never invents an error it cannot prove.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

import sympy as sp

from src.qa import units as U

Dim = tuple  # (Fraction force_exp, Fraction length_exp)
DIMENSIONLESS: Dim = (Fraction(0), Fraction(0))

_SAME_DIM_FUNCS = (sp.Min, sp.Max, sp.Abs, sp.floor, sp.ceiling)
_DIMENSIONLESS_FUNCS = (sp.sin, sp.cos, sp.tan, sp.cot, sp.sec, sp.csc,
                        sp.asin, sp.acos, sp.atan, sp.acot, sp.sinh,
                        sp.cosh, sp.tanh, sp.exp, sp.log)

_NAMES = {
    (0, 0): "dimensionless", (1, 0): "force", (0, 1): "length",
    (0, 2): "area", (0, 3): "volume / section modulus",
    (0, 4): "second moment of area", (1, -2): "stress", (1, 1): "moment",
    (1, -1): "line load", (0, -1): "1/length",
}


def describe_dim(dim: Dim | None) -> str:
    if dim is None:
        return "unknown"
    f, l = dim
    key = (int(f), int(l)) if f.denominator == 1 and l.denominator == 1 else None
    if key in _NAMES:
        return _NAMES[key]
    parts = [f"F^{f}" if f else "", f"L^{l}" if l else ""]
    return "·".join(p for p in parts if p) or "dimensionless"


def unit_dim(unit: str) -> Dim | None:
    """Dimension of a unit label; '' (unlabelled) is unknown, '-' is 1."""
    if unit is None or unit.strip() == "":
        return None
    d = U.dim_of(unit)
    if d is None:
        return None
    return (Fraction(d[0]), Fraction(d[1]))


@dataclass
class DimResult:
    dim: Dim | None
    homogeneous: bool = True
    conflicts: list[str] = field(default_factory=list)


class _Walker:
    def __init__(self, dims: dict[str, Dim | None]) -> None:
        self.dims = dims
        self.conflicts: list[str] = []

    def walk(self, e) -> Dim | None:
        if e.is_Number or e in (sp.pi, sp.E) or isinstance(e, sp.NumberSymbol):
            return DIMENSIONLESS
        if isinstance(e, sp.Symbol):
            return self.dims.get(e.name)
        if isinstance(e, (sp.logic.boolalg.BooleanTrue,
                          sp.logic.boolalg.BooleanFalse)):
            return DIMENSIONLESS
        if isinstance(e, sp.Add):
            return self._same(e.args, "added terms")
        if isinstance(e, sp.Mul):
            total = [Fraction(0), Fraction(0)]
            for a in e.args:
                d = self.walk(a)
                if d is None:
                    return None
                total[0] += d[0]
                total[1] += d[1]
            return (total[0], total[1])
        if isinstance(e, sp.Pow):
            base = self.walk(e.base)
            if e.exp.is_Number:
                if base is None:
                    return None
                k = Fraction(str(sp.nsimplify(e.exp)))
                return (base[0] * k, base[1] * k)
            exp_dim = self.walk(e.exp)
            if exp_dim not in (None, DIMENSIONLESS):
                self.conflicts.append(f"exponent {e.exp} has a dimension")
            if base not in (None, DIMENSIONLESS):
                self.conflicts.append(
                    f"{describe_dim(base)} raised to a symbolic power {e.exp}")
                return None
            return base
        if isinstance(e, sp.Piecewise):
            for _, cond in e.args:
                self.walk(cond)
            return self._same([v for v, _ in e.args], "conditional branches")
        if isinstance(e, sp.core.relational.Relational):
            self._same([e.lhs, e.rhs], "compared quantities")
            return DIMENSIONLESS
        if isinstance(e, (sp.And, sp.Or, sp.Not)):
            for a in e.args:
                self.walk(a)
            return DIMENSIONLESS
        if isinstance(e, _SAME_DIM_FUNCS):
            return self._same(e.args, f"arguments of {type(e).__name__}")
        if isinstance(e, _DIMENSIONLESS_FUNCS):
            for a in e.args:
                d = self.walk(a)
                if d not in (None, DIMENSIONLESS):
                    self.conflicts.append(
                        f"{type(e).__name__}() of a {describe_dim(d)}")
            return DIMENSIONLESS
        return None

    def _same(self, args, what: str) -> Dim | None:
        known = []
        for a in args:
            d = self.walk(a)
            if d is not None:
                known.append(d)
        if not known:
            return None
        first = known[0]
        if any(d != first for d in known[1:]):
            kinds = sorted({describe_dim(d) for d in known})
            self.conflicts.append(f"{what} mix {' and '.join(kinds)}")
            return None
        return first


def analyse(expr, dims: dict[str, Dim | None]) -> DimResult:
    w = _Walker(dims)
    d = w.walk(expr)
    return DimResult(dim=d, homogeneous=not w.conflicts, conflicts=w.conflicts)


def sheet_dims(sheet) -> dict[str, Dim | None]:
    return {name: unit_dim(unit) for name, unit in sheet.units.items()}
