"""Stage 4 - consolidation by consensus.

All instances of one quantity are grouped into *variants* (the same formula,
however it was typed).  Variants are then merged into one unified formula by
generalisation, never by guessing:

    a number where another variant has a symbol   -> the symbol is kept
                                                     ("source fixes γ_C = 1.5")
    a factor only one variant has                  -> kept; 1 for the others
                                                     ("per unit width: b_w = 1")
    a term only one variant has                    -> kept; 0 for the others
                                                     ("no axial stress: σ_cp = 0")
    a max()/min() bound only one variant has       -> kept
                                                     ("source omits the lower bound")

A merge is accepted only if every merged variant is numerically a special
case of the unified formula over the whole parameter range.  Variants that
cannot be merged this way are a disagreement between sources; they are kept
side by side for an engineer to decide.

Consensus is a way of clustering, not a proof of correctness.  Correctness
comes from the benchmarks (every source value must be reproduced) and from
the independent reference (see ``benchmarks.py`` and ``reference.py``).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .. import expr as X
from .decompose import LOCAL, Instance, tidy
from .taxonomy import Taxonomy

SAMPLES = 60


@dataclass
class Diff:
    """What a variant lacks compared with the unified formula."""
    kind: str                 # literal | factor | term | bound | alias
    sym: str = ""
    value: float | None = None
    expr: X.Node | None = None
    fn: str = ""
    args: tuple = ()

    def describe(self, name) -> str:
        if self.kind == "literal":
            return f"fixes {name(self.sym)} = {X._short(self.value)}"
        if self.kind == "factor":
            return f"has no factor {name(self.sym)} (equivalent to {name(self.sym)} = 1)"
        if self.kind == "term":
            return f"has no term {X.to_text(self.expr, name)} (equivalent to it being zero)"
        if self.kind == "bound":
            word = "lower" if self.fn == "max" else "upper"
            return f"omits the {word} bound {', '.join(X.to_text(a, name) for a in self.args)}"
        return f"calls {name(self.sym)} by a project name"


@dataclass
class Variant:
    formula: X.Node
    instances: list[Instance] = field(default_factory=list)
    diffs: list[Diff] = field(default_factory=list)
    merged: bool = False
    reason: str = ""          # why it was not merged

    @property
    def sources(self) -> list[str]:
        return sorted({i.doc for i in self.instances})

    @property
    def publishable(self) -> bool:
        return not any(s.startswith(LOCAL) for s in X.symbols(self.formula))


@dataclass
class Consolidation:
    concept: str
    variants: list[Variant] = field(default_factory=list)
    unified: X.Node | None = None
    status: str = ""          # consensus | unified | single source | disagreement | project-specific
    neutral: dict = field(default_factory=dict)     # parameter -> value that switches it off

    @property
    def merged(self) -> list[Variant]:
        return [v for v in self.variants if v.merged]

    @property
    def conflicts(self) -> list[Variant]:
        return [v for v in self.variants if not v.merged]

    @property
    def params(self) -> list[str]:
        return X.symbols(self.unified) if self.unified is not None else []


# --------------------------------------------------------------------------
# sampling
# --------------------------------------------------------------------------
def domain(sym: str, tax: Taxonomy, observed: dict) -> tuple[float, float]:
    c = tax.concepts.get(sym)
    if c is not None and c.canonical_range:
        return c.canonical_range
    vals = [v for v in observed.get(sym, []) if isinstance(v, (int, float))]
    if vals:
        lo, hi = min(vals), max(vals)
        if lo == hi:
            lo, hi = (0.5 * lo, 1.5 * lo) if lo > 0 else (1.5 * lo, 0.5 * lo) if lo < 0 else (0.0, 1.0)
        return (lo, hi)
    return (0.5, 2.0)


def samples(symbols: list[str], tax: Taxonomy, observed: dict, n: int = SAMPLES, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        env = {}
        for s in sorted(symbols):
            lo, hi = domain(s, tax, observed)
            env[s] = rng.uniform(lo, hi)
        out.append(env)
    return out


def _eq(a, b, rel: float = 1e-9) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        return str(a).strip().lower() == str(b).strip().lower()
    return math.isclose(a, b, rel_tol=rel, abs_tol=1e-12)


def equivalent(a: X.Node, b: X.Node, tax: Taxonomy, observed: dict) -> bool:
    """Do two formulas give the same number everywhere (same symbols)?"""
    sa, sb = set(X.symbols(a)), set(X.symbols(b))
    if sa != sb:
        return False
    ok = 0
    for env in samples(sorted(sa), tax, observed):
        try:
            if not _eq(X.evaluate(a, env), X.evaluate(b, env)):
                return False
            ok += 1
        except X.ExprError:
            continue
    return ok >= SAMPLES // 3


# --------------------------------------------------------------------------
# merging two formulas
# --------------------------------------------------------------------------
class Merger:
    def __init__(self, tax: Taxonomy):
        self.tax = tax
        self._active: set = set()      # pairs being merged (guards against going in circles)

    def _literal_ok(self, sym: str, value: float) -> bool:
        """A number may stand for a symbol only if it is a plausible value of it."""
        c = self.tax.concepts.get(sym)
        if c is None:
            return False
        if c.kind == "coefficient":
            return True
        rng = c.canonical_range
        return bool(rng) and rng[0] <= value <= rng[1]

    def _neutral_factor(self, n: X.Node) -> bool:
        if not isinstance(n, X.Sym):
            return False
        c = self.tax.concepts.get(n.name)
        return c is not None and (c.strip or (c.kind == "coefficient" and not any(c.dims)))

    def merge(self, a: X.Node, b: X.Node, da: list, db: list) -> X.Node | None:
        """Unified tree, or None.  ``da`` / ``db`` collect what a / b lack."""
        sig = (X.key(a), X.key(b))
        if sig in self._active:
            return None
        self._active.add(sig)
        try:
            return self._merge(a, b, da, db)
        finally:
            self._active.discard(sig)

    def _merge(self, a: X.Node, b: X.Node, da: list, db: list) -> X.Node | None:
        if X.same(a, b):
            return a
        if isinstance(a, X.Num) and isinstance(b, X.Sym):
            if self._literal_ok(b.name, a.value):
                da.append(Diff("literal", sym=b.name, value=a.value))
                return b
            return None
        if isinstance(a, X.Sym) and isinstance(b, X.Num):
            if self._literal_ok(a.name, b.value):
                db.append(Diff("literal", sym=a.name, value=b.value))
                return a
            return None
        if isinstance(a, X.Sym) and isinstance(b, X.Sym):
            la, lb = a.name.startswith(LOCAL), b.name.startswith(LOCAL)
            if la and not lb:
                da.append(Diff("alias", sym=b.name, expr=a))
                return b
            if lb and not la:
                db.append(Diff("alias", sym=a.name, expr=b))
                return a
            return None
        # a bound present on one side only: max(X, bound) against X
        for x, y, dx, dy, swap in ((a, b, da, db, False), (b, a, db, da, True)):
            if isinstance(x, X.Call) and x.fn in ("max", "min") and not (
                    isinstance(y, X.Call) and y.fn == x.fn):
                for i, arg in enumerate(x.args):
                    tx, ty = [], []
                    m = self.merge(y, arg, ty, tx) if swap else self.merge(arg, y, tx, ty)
                    if m is not None:
                        others = tuple(o for j, o in enumerate(x.args) if j != i)
                        dx.extend(tx)
                        dy.extend(ty)
                        dy.append(Diff("bound", fn=x.fn, args=others))
                        return X.Call(x.fn, x.args[:i] + (m,) + x.args[i + 1:])
        if isinstance(a, X.Call) and isinstance(b, X.Call) and a.fn == b.fn and len(a.args) == len(b.args):
            orders = [list(range(len(a.args)))]
            if a.fn in ("max", "min") and len(a.args) == 2:
                orders.append([1, 0])
            for order in orders:
                ta, tb, out = [], [], []
                for i, j in enumerate(order):
                    m = self.merge(a.args[i], b.args[j], ta, tb)
                    if m is None:
                        break
                    out.append(m)
                else:
                    da.extend(ta)
                    db.extend(tb)
                    return X.Call(a.fn, tuple(out))
            return None
        if isinstance(a, X.If) and isinstance(b, X.If) and X.same(a.cond, b.cond):
            ta, tb = [], []
            then = self.merge(a.then, b.then, ta, tb)
            other = self.merge(a.other, b.other, ta, tb) if then is not None else None
            if then is None or other is None:
                return None
            da.extend(ta)
            db.extend(tb)
            return X.If(a.cond, then, other)
        if isinstance(a, X.Bin) and isinstance(b, X.Bin) and a.op == "**" and b.op == "**":
            ta, tb = [], []
            base = self.merge(a.left, b.left, ta, tb)
            if base is None or not X.same(a.right, b.right):
                return None
            da.extend(ta)
            db.extend(tb)
            return X.Bin("**", base, a.right)
        ta, tb = X.terms(a), X.terms(b)
        if len(ta) > 1 or len(tb) > 1:
            return self._sum(a, b, ta, tb, da, db)
        fa, fb = X.factors(a), X.factors(b)
        if len(fa[0]) + len(fa[1]) > 1 or len(fb[0]) + len(fb[1]) > 1:
            return self._product(fa, fb, da, db)
        return None

    # ---- sums -------------------------------------------------------------
    def _sum(self, a, b, ta, tb, da, db):
        ra, rb = list(ta), list(tb)
        for item in list(ra):
            for other in rb:
                if item[0] == other[0] and X.same(item[1], other[1]):
                    ra.remove(item)
                    rb.remove(other)
                    break
        if not ra and not rb:
            return a
        if ra and rb:
            xa, xb = [], []
            if len(ra) == 1 and len(rb) == 1 and ra[0][0] == rb[0][0]:
                m = self.merge(ra[0][1], rb[0][1], xa, xb)
                if m is None:
                    return None
                da.extend(xa)
                db.extend(xb)
                return X.total([(s, m) if (s, t) == ra[0] else (s, t) for s, t in ta])
            return None
        extra, lacking, base = (rb, da, b) if rb else (ra, db, a)
        for sign, term in extra:
            if not X.symbols(term):
                return None                       # a bare number cannot be switched off
            lacking.append(Diff("term", expr=term if sign > 0 else X.Neg(term)))
        return base

    # ---- products ---------------------------------------------------------
    def _product(self, fa, fb, da, db):
        xa, xb = [], []
        numer = self._pair(list(fa[0]), list(fb[0]), xa, xb)
        denom = self._pair(list(fa[1]), list(fb[1]), xa, xb) if numer is not None else None
        if numer is None or denom is None:
            return None
        da.extend(xa)
        db.extend(xb)
        return X.product(numer, denom)

    def _pair(self, la: list, lb: list, da: list, db: list) -> list | None:
        """Match the factors of two products; returns the unified factor list."""
        slots: list = [None] * len(lb)          # result follows the order of b where matched
        left_a = []
        used: set[int] = set()
        for x in la:
            for j, y in enumerate(lb):
                if j not in used and X.same(x, y):
                    used.add(j)
                    slots[j] = x
                    break
            else:
                left_a.append(x)
        rest_a = []
        for x in left_a:
            hit = None
            for j, y in enumerate(lb):
                if j in used:
                    continue
                ta, tb = [], []
                m = self.merge(x, y, ta, tb)
                if m is not None:
                    hit = (j, m, ta, tb)
                    break
            if hit:
                j, m, ta, tb = hit
                used.add(j)
                slots[j] = m
                da.extend(ta)
                db.extend(tb)
            else:
                rest_a.append(x)
        rest_b = [(j, y) for j, y in enumerate(lb) if j not in used]
        if rest_a and rest_b:
            # several factors on one side against one composite factor on the other
            ta, tb = [], []

            def composite(n):          # a sum or a bound: something a product can sit inside
                return (isinstance(n, X.Bin) and n.op in "+-") or isinstance(n, X.Neg) or (
                    isinstance(n, X.Call) and n.fn in ("max", "min"))

            if len(rest_b) == 1 and composite(rest_b[0][1]):
                m = self.merge(X.product(rest_a), rest_b[0][1], ta, tb)
            elif len(rest_a) == 1 and composite(rest_a[0]):
                m = self.merge(rest_a[0], X.product([y for _, y in rest_b]), ta, tb)
            else:
                m = None
            if m is None:
                return None
            da.extend(ta)
            db.extend(tb)
            slots[rest_b[0][0]] = m
            for j, _ in rest_b[1:]:
                slots[j] = "drop"
            rest_a, rest_b = [], []
        # a factor only one side has must be able to act as 1 on the other side:
        # a dimensionless coefficient, or a width in a per-unit-width source
        for x in rest_a:
            if not self._neutral_factor(x):
                return None
            db.append(Diff("factor", sym=x.name))
        for j, y in rest_b:
            if not self._neutral_factor(y):
                return None
            da.append(Diff("factor", sym=y.name))
            slots[j] = y
        out = [s for s in slots if s is not None and not (isinstance(s, str) and s == "drop")]
        return out + rest_a


# --------------------------------------------------------------------------
# is a variant a special case of the unified formula?
# --------------------------------------------------------------------------
def specialise(env: dict, diffs: list[Diff], own: set[str], observed: dict) -> dict | None:
    """Apply a variant's differences to a sample point (None if impossible)."""
    env = dict(env)
    for d in diffs:
        if d.kind == "literal":
            env[d.sym] = d.value
        elif d.kind == "factor":
            env[d.sym] = 1.0
        elif d.kind == "alias":
            env[d.expr.name] = env.get(d.sym, env.get(d.expr.name))
            env[d.sym] = env[d.expr.name]
        elif d.kind == "term":
            z = zero_symbol(d.expr, own, observed)
            if z is None:
                return None
            env[z] = 0.0
    return env


def zero_symbol(term: X.Node, own: set[str], observed: dict) -> str | None:
    """The symbol whose value 0 switches a term off (σ_cp in k_1·σ_cp)."""
    cands = [s for s in X.symbols(term) if s not in own]
    good = []
    for s in cands:
        probe = {k: 1.3 for k in X.symbols(term)}
        probe[s] = 0.0
        try:
            if X.evaluate(term, probe) == 0:
                good.append(s)
        except X.ExprError:
            continue
    if not good:
        return None
    # prefer the one sources actually set to zero, then the one that varies most
    def rank(s):
        vals = [v for v in observed.get(s, []) if isinstance(v, (int, float))]
        spread = (max(vals) - min(vals)) if vals else 0.0
        return (0 if any(v == 0 for v in vals) else 1, -spread)

    return sorted(good, key=rank)[0]


def is_special_case(unified: X.Node, variant: Variant, tax: Taxonomy, observed: dict) -> bool:
    own = set(X.symbols(variant.formula))
    bounds = [d for d in variant.diffs if d.kind == "bound"]
    syms = sorted(set(X.symbols(unified)) | own)
    ok = 0
    for env in samples(syms, tax, observed):
        env = specialise(env, variant.diffs, own, observed)
        if env is None:
            return False
        try:
            u = X.evaluate(unified, env)
            v = X.evaluate(variant.formula, env)
            if bounds:
                # the unified value is the variant's value or one of the bounds it lacks
                limits = [X.evaluate(arg, env) for d in bounds for arg in d.args]
                if not (_eq(u, v) or any(_eq(u, lim) for lim in limits)):
                    return False
            elif not _eq(u, v):
                return False
            ok += 1
        except X.ExprError:
            continue
    return ok >= SAMPLES // 3


# --------------------------------------------------------------------------
def consolidate(concept: str, instances: list[Instance], tax: Taxonomy, observed: dict) -> Consolidation:
    out = Consolidation(concept)
    # ---- variants: the same formula, however it was typed --------------------
    for inst in instances:
        if inst.formula is None:
            continue
        for v in out.variants:
            if X.same(v.formula, inst.formula):
                v.instances.append(inst)
                break
        else:
            out.variants.append(Variant(inst.formula, [inst]))
    # formulas written differently but numerically identical are one variant
    merged_any = True
    while merged_any:
        merged_any = False
        for i, v in enumerate(out.variants):
            for w in out.variants[i + 1:]:
                if equivalent(v.formula, w.formula, tax, observed):
                    keep, drop = (v, w) if len(v.instances) >= len(w.instances) else (w, v)
                    keep.instances.extend(drop.instances)
                    out.variants.remove(drop)
                    merged_any = True
                    break
            if merged_any:
                break
    if not out.variants:
        return out
    # most support first: number of sources, then number of instances
    out.variants.sort(key=lambda v: (-v.publishable, -len(v.sources), -len(v.instances)))

    usable = [v for v in out.variants if v.publishable]
    for v in out.variants:
        if not v.publishable:
            v.reason = "uses project-specific quantities: " + ", ".join(
                s[1:] for s in X.symbols(v.formula) if s.startswith(LOCAL))
    if not usable:
        out.status = "project-specific"
        return out

    merger = Merger(tax)
    unified = usable[0].formula
    usable[0].merged = True
    members = [usable[0]]
    for v in usable[1:]:
        cand = merger.merge(unified, v.formula, [], [])
        if cand is None:
            v.reason = "the formulas differ in a way that is not a generalisation of one another"
            continue
        cand = tidy(cand)
        # every member, and the newcomer, must be a special case of the candidate
        trial = members + [v]
        fits = True
        new_diffs = {}
        for m in trial:
            dm: list[Diff] = []
            dc: list[Diff] = []
            back = merger.merge(m.formula, cand, dm, dc)
            probe = Variant(m.formula, m.instances, dm)
            if back is None or dc or not X.same(back, cand) or not is_special_case(cand, probe, tax, observed):
                fits = False
                break
            # a missing width is only a unit strip if the source works per unit width
            if any(d.kind == "factor" and tax.concepts[d.sym].strip for d in dm) and not all(
                    i.per_width for i in m.instances):
                fits = False
                break
            new_diffs[id(m)] = dm
        if not fits:
            v.reason = "merging would change the result of another variant"
            continue
        unified = cand
        v.merged = True
        members.append(v)
        for m in members:
            m.diffs = new_diffs[id(m)]
    out.unified = unified

    for m in members:
        own = set(X.symbols(m.formula))
        for d in m.diffs:
            if d.kind == "term":
                z = zero_symbol(d.expr, own, observed)
                if z:
                    out.neutral[z] = 0.0

    n_sources = len({s for m in members for s in m.sources})
    if out.conflicts and any(v.publishable for v in out.conflicts):
        out.status = "disagreement"
    elif n_sources < 2:
        out.status = "single source"
    elif len(members) == 1:
        out.status = "consensus"
    else:
        out.status = "unified"
    return out
