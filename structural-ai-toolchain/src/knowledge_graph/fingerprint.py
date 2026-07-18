"""Structural formula fingerprinting.

Answers "is this the same formula?" independent of variable naming:
``k_3*c + k_1*k_2*k_4*phi/rho_p_eff`` and
``k3*cnom + k1*k2*k4*dia/rho_eff`` hash identically, so the knowledge
graph can recognize a library atom (or a formula from another tool)
inside a freshly ingested legacy sheet.

Method: parse with sympy (which canonicalizes structure), then assign
positional placeholders to the free symbols by walking the tree with
commutative arguments ordered by a *name-blind shape key* (the subtree
with every symbol collapsed to one placeholder). This makes the label
assignment — and therefore the hash — independent of the original
variable names, which would otherwise leak in through sympy's
name-based commutative argument sorting.

Known limitation: expressions containing several same-shaped commutative
siblings that share symbols asymmetrically (e.g. ``a*b + a*c``) can tie
in the shape ordering and occasionally miss a rename-equivalence; this
errs toward "new formula", never toward a false duplicate.
"""

from __future__ import annotations

import hashlib
import re

import sympy as sp

_ALLOWED = {
    "sqrt": sp.sqrt, "min": sp.Min, "max": sp.Max, "abs": sp.Abs,
    "exp": sp.exp, "log": sp.log, "ln": sp.log, "pi": sp.pi,
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse_locals(expression: str) -> dict:
    """Locals dict mapping every identifier to a Symbol (plus functions).

    Without this, sympy hijacks single-letter engineering names:
    ``E`` becomes Euler's number, ``I`` the imaginary unit, ``N``/``S``
    sympy internals — silently corrupting formulas.
    """
    local = dict(_ALLOWED)
    for name in set(_IDENT.findall(expression)):
        if name not in local:
            local[name] = sp.Symbol(name)
    return local

class FingerprintError(Exception):
    pass


def _shape_key(expr: sp.Basic) -> str:
    """Name-blind description of a subtree, used to order siblings."""
    symbols = {s: sp.Symbol("_s") for s in expr.free_symbols}
    return sp.srepr(expr.xreplace(symbols))


def _assign_placeholders(expr: sp.Basic, mapping: dict) -> None:
    """Walk the tree, commutative args in shape order, labeling symbols."""
    if expr.is_Symbol:
        if expr not in mapping:
            mapping[expr] = sp.Symbol(f"_v{len(mapping):02d}")
        return
    args = expr.args
    if expr.is_Add or expr.is_Mul:
        args = sorted(args, key=_shape_key)
    for arg in args:
        _assign_placeholders(arg, mapping)


def canonical_form(expression: str) -> str:
    """Name-independent canonical string of a formula."""
    try:
        expr = sp.sympify(expression, locals=parse_locals(expression))
    except (sp.SympifyError, SyntaxError, TypeError) as exc:
        raise FingerprintError(
            f"Cannot parse {expression!r}: {exc}"
        ) from exc

    mapping: dict = {}
    _assign_placeholders(expr, mapping)
    return sp.srepr(expr.xreplace(mapping))


def fingerprint(expression: str) -> str:
    """Short stable hash of the canonical form."""
    return hashlib.sha1(
        canonical_form(expression).encode("utf-8")
    ).hexdigest()[:16]


def try_fingerprint(expression: str) -> str | None:
    """Fingerprint, or None when the expression is unparseable."""
    try:
        return fingerprint(expression)
    except FingerprintError:
        return None


_MIN_MATCH_OPS = 3


def fingerprint_if_matchable(expression: str) -> str | None:
    """Fingerprint only if the formula has enough structure to *match*.

    Trivial shapes (``a*b``, ``a/b``, ``a-b/3``) are structurally
    identical across semantically unrelated formulas — ``w_k =
    s_r_max*eps_diff`` and ``f_cm(t) = beta_cc*f_cm`` are both plain
    products. Below ~3 operations a structural match means nothing, so
    such formulas are excluded from duplicate/reuse matching (they can
    still be reused deliberately via ``sheet.apply()``).
    """
    try:
        expr = sp.sympify(expression, locals=parse_locals(expression))
    except (sp.SympifyError, SyntaxError, TypeError):
        return None
    if sp.count_ops(expr) < _MIN_MATCH_OPS:
        return None
    return try_fingerprint(expression)
