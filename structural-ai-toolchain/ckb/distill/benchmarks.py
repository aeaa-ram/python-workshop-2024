"""Benchmarks: every source value is a test the unified logic must pass.

The more often a piece of logic appears in the sources, the more benchmarks
it collects - repeated calculations are not waste, they are validation.

* A source *formula* instance is checked at the level of its own object: the
  unified formula is evaluated with the numbers that source used.  Where the
  source formula is a special case (it has no lower bound, or no axial-stress
  term), the missing quantity is looked up in the same calculation run, so a
  simplification that matters for that case shows up as a deviation.
* A *printed* value (PDF, Word, scan) is checked through the chain of objects
  from the printed inputs, within the rounding of the print.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .. import expr as X
from ..ir import Statement, close
from .consolidate import Consolidation, Variant
from .decompose import Decomposition, Instance, canonical_value
from .taxonomy import Taxonomy


@dataclass
class Benchmark:
    concept: str
    doc: str
    kind: str                   # formula | printed
    loc: str
    case: str
    name: str
    expected: float | str | None
    got: float | str | None = None
    status: str = "not comparable"     # agree | deviation | not comparable
    detail: str = ""
    tolerance: float = 0.0
    inputs: dict = field(default_factory=dict)
    assumed: dict = field(default_factory=dict)
    per_width: bool = False

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in ("", None, {}, 0.0) or k in ("expected", "got")}


class Context:
    """Finds, around a statement, the value a source gives to a quantity."""

    def __init__(self, dec: Decomposition, tax: Taxonomy):
        self.dec, self.tax = dec, tax
        self.statements = dec.doc.statements
        self.pos = {s.id: i for i, s in enumerate(self.statements)}
        self.by_id = dec.doc.by_id()
        self._roles: dict[str, dict[str, list]] = {}
        self.sequential = dec.doc.kind != "excel"
        # for a print of another source: which statement of that source each printed value is
        self.twin: dict[str, Instance] = {}       # printed statement id -> the formula instance behind it
        self.printed_of: dict[str, Statement] = {}  # statement id in the other source -> printed statement

    def roles(self, scope) -> dict[str, list]:
        key = getattr(scope, "id", scope)
        if key not in self._roles:
            table: dict[str, list] = {}
            for i, st in enumerate(self.statements):
                if not isinstance(st.best_value(), (int, float)):
                    continue
                m = self.tax.resolve(st.name, st.label, st.clause, st.section, scope=scope, argument=True)
                own = self.dec.producer.get(st.id)
                if m is not None:
                    table.setdefault(m.concept.id, []).append((i, m.score))
                if own and (m is None or own[0].id != m.concept.id):
                    table.setdefault(own[0].id, []).append((i, 0.6))
            self._roles[key] = table
        return self._roles[key]

    def find(self, concept: str, scope, near: Statement, same_group_only: bool = False) -> Statement | None:
        t = self.twin.get(near.id)
        if t is not None and concept in t.args:
            hit = self.printed_of.get(t.args[concept]["stmt"])
            if hit is not None:
                return hit
        here = self.pos[near.id]
        best, best_key = None, None
        for i, score in self.roles(scope).get(concept, []):
            st = self.statements[i]
            if st.id == near.id:
                continue
            same = st.group == near.group and near.group != ""
            before = i < here
            if not same and (same_group_only or not self.sequential):
                continue
            if self.sequential and not before:
                continue
            # the same calculation run first, then the surest match, then the nearest
            key = (0 if same or self.sequential else 1, -round(score, 1), abs(i - here))
            if best_key is None or key < best_key:
                best, best_key = st, key
        return best


def link_print(printed: Decomposition, other: Decomposition, ctx: "Context") -> None:
    """Pair each printed value with the statement of the source it is a print of."""
    from ..notation import symkey
    from .. import units as U
    inst_of = {i.stmt: i for i in other.instances if i.kind == "formula"}
    pool: dict[str, list] = {}
    for st in other.doc.statements:
        v = st.best_value()
        if isinstance(v, (int, float)):
            shown = U.from_canonical(v, st.unit) if (st.canonical and st.unit) else v
            pool.setdefault(symkey(st.name), []).append([st, shown, False])
    for st in printed.doc.statements:
        if not isinstance(st.value, (int, float)):
            continue
        tol = max(st.precision * 1.01, 1e-9 * abs(st.value))
        for entry in pool.get(symkey(st.name), []):
            if not entry[2] and abs(entry[1] - st.value) <= tol:
                entry[2] = True
                ctx.printed_of[entry[0].id] = st
                if entry[0].id in inst_of:
                    ctx.twin[st.id] = inst_of[entry[0].id]
                break


def typical_values(observed: dict, tax: Taxonomy | None = None) -> dict:
    """A value for each quantity: the recommended value of a coefficient, else the most
    frequent value in the sources."""
    out = {}
    for cid, vals in observed.items():
        nums = [float(f"{v:.6g}") for v in vals if isinstance(v, (int, float))]
        if nums:
            out[cid] = Counter(nums).most_common(1)[0][0]
    if tax is not None:
        for c in tax.concepts.values():
            if c.kind == "coefficient" and c.canonical_value is not None:
                out[c.id] = c.canonical_value
    return out


def _chain(pid: str, env: dict, formulas: dict, depth: int = 0):
    """Evaluate an object from the values at hand, resolving what it needs."""
    if depth > 12 or pid not in formulas:
        return None
    local = dict(env)
    for q in X.symbols(formulas[pid]):
        if q not in local:
            v = _chain(q, local, formulas, depth + 1)
            if v is None:
                return None
            local[q] = v
    try:
        return X.evaluate(formulas[pid], local)
    except X.ExprError:
        return None


def _inverse(pid: str, env: dict, tax: Taxonomy):
    """Recover a primary quantity from a derived one the source gives (θ from cot θ)."""
    for c in tax.concepts.values():
        expr = c.inverse.get(pid) if c.inverse else None
        if expr and c.id in env:
            try:
                return X.evaluate(X.parse(expr), env)
            except X.ExprError:
                continue
    return None


def bench_formula(inst: Instance, variant: Variant, cons: Consolidation, ctx: Context, tax: Taxonomy,
                  formulas: dict, typical: dict, name) -> Benchmark:
    from .baseline import effect, explain
    b = Benchmark(inst.concept, inst.doc, "formula", inst.loc, inst.case, inst.name, inst.value)
    b.per_width = inst.per_width
    concept = tax.concepts[inst.concept]
    reference = variant.reference if variant.reference is not None else cons.unified
    st = ctx.by_id[inst.stmt]
    env = {s: a["value"] for s, a in inst.args.items()}
    for old, new in variant.renamed.items():
        if old in env:
            env.setdefault(new, env[old])
            b.assumed[new] = f"the source's {name(old)}"
    for d in variant.diffs:
        if d.kind == "alias":
            env[d.sym] = env.get(d.expr.name)
        elif d.kind == "literal" and d.sym not in env:
            env[d.sym], b.assumed[d.sym] = d.value, "fixed in the source formula"
        elif d.kind == "factor" and d.sym not in env and tax.concepts.get(d.sym) is not None:
            c = tax.concepts[d.sym]
            if c.strip and inst.per_width:
                env[d.sym], b.assumed[d.sym] = 1.0, "per unit width"
            elif not c.formula:
                env[d.sym], b.assumed[d.sym] = 1.0, "not in the source formula"
    missing: list[str] = []

    def value(p: str, trail: tuple = ()):
        """The source's value of p, else derived from the source's values, else a stated assumption."""
        if p in env:
            return env[p]
        if p in trail or len(trail) > 12:
            return None
        r = ctx.find(p, concept, st, same_group_only=not ctx.sequential)
        if r is not None and isinstance(r.best_value(), (int, float)):
            env[p] = canonical_value(r, tax.concepts.get(p))
            b.assumed[p] = f"from {r.name} ({r.loc})"
            return env[p]
        v = _inverse(p, env, tax)
        if v is None and p in formulas:
            sub = [value(q, trail + (p,)) for q in X.symbols(formulas[p])]
            if all(x is not None for x in sub):
                try:
                    v = X.evaluate(formulas[p], env)
                except X.ExprError:
                    v = None
        if v is not None:
            env[p] = v
            b.assumed.setdefault(p, "calculated from the same inputs")
            return v
        if p in cons.neutral:
            env[p], b.assumed[p] = cons.neutral[p], "not in the source; no effect"
        elif typical.get(p) is not None:
            c = tax.concepts.get(p)
            env[p] = typical[p]
            b.assumed[p] = "recommended value" if c is not None and c.kind == "coefficient" else "typical value"
        else:
            missing.append(p)
            return None
        return env[p]

    for p in X.symbols(reference):
        value(p)
    if missing:
        b.detail = f"{name(missing[0])} is not given in the source"
        return b
    b.inputs = env
    try:
        b.got = X.evaluate(reference, env)
    except X.ExprError as exc:
        b.detail = str(exc)
        return b
    notes = [explain(d, tax, env, inst.per_width, name) for d in variant.diffs if d.kind != "alias"]
    if close(b.got, inst.value, rel=1e-6):
        b.status = "agree"
        b.detail = "; ".join(n for n in notes if n)
        return b
    b.status = "deviation"
    reasons = []
    for d in variant.diffs:
        try:
            if d.kind == "bound":
                for arg in d.args:
                    lim = X.evaluate(arg, env)
                    if close(b.got, lim, rel=1e-9):
                        word = "lower" if d.fn == "max" else "upper"
                        reasons.append(f"the {word} bound {X.to_text(arg, name)} governs here and the source does not apply it")
            elif d.kind == "term":
                if X.evaluate(d.expr, env) != 0:
                    reasons.append(f"the source leaves out {X.to_text(d.expr, name)}, which is not zero here")
            elif d.kind == "factor" and env.get(d.sym) != 1.0:
                reasons.append(f"the source leaves out the factor {name(d.sym)}")
            elif d.kind == "literal" and tax.concepts.get(d.sym) is not None:
                rec = tax.concepts[d.sym].canonical_value
                if rec is not None and abs(rec - d.value) > 1e-9:
                    reasons.append(f"the source uses {name(d.sym)} = {X._short(d.value)}")
        except X.ExprError:
            continue
    if variant.relation == "differs":
        reasons.append("the source formula is not the code expression")
    eff = effect(concept.sense, inst.value, b.got)
    b.detail = "; ".join(reasons) or "different result"
    if eff:
        b.detail += f": {eff}"
    return b


def bench_printed(inst: Instance, ctx: Context, tax: Taxonomy, formulas: dict, neutral: dict,
                  typical: dict, name, unmerged: set = frozenset()) -> Benchmark:
    b = Benchmark(inst.concept, inst.doc, "printed", inst.loc, inst.case, inst.name, inst.value)
    st = ctx.by_id[inst.stmt]
    assumed: dict = {}
    twin = ctx.twin.get(st.id)
    if twin is not None and id(twin) in unmerged:
        b.detail = "printed from a formula variant that was not merged into this object"
        return b

    def printed(pid: str, scope: str, near: Statement):
        r = ctx.find(pid, scope, near)
        if r is None:
            return None
        c = tax.concepts.get(pid)
        f = canonical_value(r, c)
        factor = (f / r.best_value()) if r.best_value() else 1.0
        return f, abs(r.precision * factor), r

    def value_of(cid: str, depth: int, near: Statement):
        """(value, tolerance, inputs) of an object evaluated from the printed inputs."""
        if depth > 12 or cid not in formulas:
            return None
        scope = tax.concepts[cid]
        env, tol = {}, {}
        for p in X.symbols(formulas[cid]):
            hit = printed(p, scope, near)
            shown = hit[:2] if hit else None
            sub = value_of(p, depth + 1, hit[2] if hit else near) if p in formulas else None
            if sub is not None and shown is not None:
                # use the object when it agrees with the print (it is more precise than the print)
                if abs(sub[0] - shown[0]) <= sub[1] + shown[1] + 1e-9 * abs(shown[0]):
                    env[p], tol[p] = sub[0], sub[1]
                else:
                    env[p], tol[p] = shown
            elif sub is not None:
                env[p], tol[p] = sub[0], sub[1]
            elif shown is not None:
                env[p], tol[p] = shown
            elif p in neutral.get(cid, {}):
                env[p], tol[p] = neutral[cid][p], 0.0
                assumed[p] = "not printed; no effect"
            elif typical.get(p) is not None and tax.concepts[p].kind == "coefficient":
                env[p], tol[p] = typical[p], 0.0
                assumed[p] = "not printed; recommended value"
            else:
                return None
        try:
            got = X.evaluate(formulas[cid], env)
            spread = 0.0
            for p, t in tol.items():
                if t:
                    lo = X.evaluate(formulas[cid], {**env, p: env[p] - t})
                    hi = X.evaluate(formulas[cid], {**env, p: env[p] + t})
                    spread += max(abs(lo - got), abs(hi - got))
        except (X.ExprError, TypeError):
            return None
        return got, spread, env

    res = value_of(inst.concept, 0, st)
    if res is None:
        b.detail = "the print does not show every input"
        return b
    b.got, spread, b.inputs = res
    b.assumed = assumed
    if isinstance(inst.value, str) or isinstance(b.got, str):
        b.status = "agree" if close(b.got, inst.value) else "deviation"
        return b
    b.tolerance = spread + inst.precision
    if abs(b.got - inst.value) <= b.tolerance + 1e-9 * abs(inst.value):
        b.status = "agree"
    else:
        b.status = "deviation"
        b.detail = "outside the rounding of the print"
    return b


def run(consolidations: dict[str, Consolidation], decs: list[Decomposition], tax: Taxonomy,
        observed: dict, name) -> dict[str, list[Benchmark]]:
    formulas = {c.id: c.tree for c in tax.concepts.values() if c.formula}
    formulas.update({cid: c.unified for cid, c in consolidations.items() if c.unified is not None})
    neutral = {cid: c.neutral for cid, c in consolidations.items()}
    typical = typical_values(observed, tax)
    ctx = {dec.doc.id: Context(dec, tax) for dec in decs}
    by_doc = {dec.doc.id: dec for dec in decs}
    for dec in decs:
        other = by_doc.get(dec.doc.meta.get("print_of", ""))
        if other is not None:
            link_print(dec, other, ctx[dec.doc.id])
    unmerged = {id(i) for c in consolidations.values() for v in c.conflicts for i in v.instances}
    out: dict[str, list[Benchmark]] = {}
    for cid, cons in consolidations.items():
        if cons.unified is None:
            continue
        rows = out.setdefault(cid, [])
        for v in cons.merged:
            for inst in v.instances:
                rows.append(bench_formula(inst, v, cons, ctx[inst.doc], tax, formulas, typical, name))
    for dec in decs:
        for inst in dec.instances:
            if inst.kind == "printed" and inst.concept in formulas:
                out.setdefault(inst.concept, []).append(
                    bench_printed(inst, ctx[dec.doc.id], tax, formulas, neutral, typical, name, unmerged))
    return out
