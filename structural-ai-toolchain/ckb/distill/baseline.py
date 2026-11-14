"""Stage 4 with a code baseline: how did each source apply the code?

When the registry holds the code's own expression for a quantity, that expression
*is* the calculation object.  The sources are then evidence: every formula found in
a source is compared with the code and put in one of five groups.

    as code           the same expression, however it was written
    alternative       an alternative the code itself permits (z = 0.9 d)
    simplified        a special case of the code expression: a recommended value
                      written in as a number, a factor or term left out, a bound
                      omitted.  Each difference is listed, and the benchmarks show
                      whether it changes the result in that case and in which direction.
    differs           not a special case of the code: a different method, another
                      code version or National Annex, or an error.  For an engineer.
    project-specific  uses quantities the registry does not know; not comparable.

Where the registry has no expression for a quantity, the sources are merged among
themselves instead (``consolidate.py``).
"""
from __future__ import annotations

from .. import expr as X
from .consolidate import Consolidation, Diff, Merger, Variant, equivalent, group_variants, is_special_case, zero_symbol
from .decompose import LOCAL, Instance
from .taxonomy import Concept, Taxonomy

RELATIONS = ("as code", "alternative", "simplified", "differs", "project-specific")


def comparable(base: X.Node, var: X.Node, tax: Taxonomy) -> tuple[X.Node, X.Node]:
    """Expand derived quantities on one side where the other side writes them out.

    One quantity at a time, always the one whose formula brings in the most symbols
    the other side has and this side lacks: f_cd and f_yd are expanded to meet a
    source that writes α_cc f_ck/γ_C and f_yk/γ_S, but η is left alone when the other
    side simply has no η.
    """
    for _ in range(12):
        sb, sv = set(X.symbols(base)), set(X.symbols(var))
        best = None
        for side, mine, other in (("b", sb, sv), ("v", sv, sb)):
            for s in mine - other:
                c = tax.concepts.get(s)
                if c is None or not c.formula:
                    continue
                gain = len(set(X.symbols(c.tree)) & (other - mine))
                if gain and (best is None or gain > best[0]):
                    best = (gain, side, s, c.tree)
        if best is None:
            break
        _, side, s, tree = best
        if side == "b":
            base = X.substitute(base, {s: tree})
        else:
            var = X.substitute(var, {s: tree})
    return base, var


def _relation(b: X.Node, v: X.Node, tax: Taxonomy, observed: dict):
    if X.same(b, v) or (set(X.symbols(b)) == set(X.symbols(v)) and equivalent(b, v, tax, observed)):
        return "as code", [], []
    d_code, d_src = [], []
    merged = Merger(tax).merge(b, v, d_code, d_src)
    if merged is not None and not d_code and d_src and is_special_case(b, Variant(v, [], d_src), tax, observed):
        return "simplified", d_src, []
    if merged is not None and d_code and not d_src:
        return "differs", [], d_code          # the source has something the code does not
    return "differs", [], []


def compare(base: X.Node, var: X.Node, tax: Taxonomy, observed: dict,
            renamed: dict | None = None) -> tuple[str, list[Diff], list[Diff]]:
    """(relation, what the source leaves out, what the source adds).

    If the source used a symbol that can also be read as another quantity (A_s for
    A_sl, b for b_w), the other reading is tried; ``renamed`` records it.
    """
    if any(s.startswith(LOCAL) for s in X.symbols(var)):
        return "project-specific", [], []
    b, v = comparable(base, var, tax)
    rel = _relation(b, v, tax, observed)
    if rel[0] != "differs":
        return rel
    only_v, only_b = set(X.symbols(v)) - set(X.symbols(b)), set(X.symbols(b)) - set(X.symbols(v))
    mapping = {}
    for s in only_v:
        cands = [t for t in only_b if tax.synonyms(s, t) and t not in mapping.values()]
        if len(cands) == 1:
            mapping[s] = cands[0]
    if mapping:
        b2, v2 = comparable(base, X.substitute(var, mapping), tax)
        rel2 = _relation(b2, v2, tax, observed)
        if rel2[0] != "differs":
            if renamed is not None:
                renamed.update(mapping)
            return rel2
    return rel


def reassign(by_concept: dict, tax: Taxonomy, observed: dict) -> int:
    """Move an instance to another reading of its symbol if only that one fits the code.

    A spreadsheet's "z = 0.9 d" written under no clause heading reads as the lever arm in
    bending, which it does not match; it is the code's lever arm for shear, which it does.
    """
    moved = 0
    for cid in list(by_concept):
        c = tax.concepts.get(cid)
        if c is None or not c.formula:
            continue
        keep = []
        for inst in by_concept[cid]:
            if inst.formula is None or compare(c.tree, inst.formula, tax, observed)[0] != "differs":
                keep.append(inst)
                continue
            target = None
            for other in tax.concepts.values():
                if other.id == cid or not other.formula or not (other.keys & c.keys) or other.dims != c.dims:
                    continue
                if compare(other.tree, inst.formula, tax, observed)[0] in ("as code", "simplified"):
                    target = other
                    break
            if target is None:
                keep.append(inst)
            else:
                inst.notes.append(f"read as {target.text} ({target.reference}): its formula matches that, not {c.text}")
                inst.concept = target.id
                by_concept.setdefault(target.id, []).append(inst)
                moved += 1
        by_concept[cid] = keep
    return moved


def classify(concept: Concept, instances: list[Instance], tax: Taxonomy, observed: dict) -> Consolidation:
    """Compare every source variant of a quantity with the code expression."""
    out = Consolidation(concept.id)
    out.variants = group_variants(instances, tax, observed)
    out.unified = concept.tree
    out.baseline = True
    alts = [(a, X.parse(a["formula"])) for a in concept.alternatives]
    for v in out.variants:
        renamed: dict = {}
        rel, missing, extra = compare(concept.tree, v.formula, tax, observed, renamed)
        if rel == "differs":
            for a, tree in alts:
                renamed = {}
                rel_a, miss_a, _ = compare(tree, v.formula, tax, observed, renamed)
                if rel_a in ("as code", "simplified"):
                    rel, missing, v.alternative = "alternative", miss_a, a
                    v.reference = tree
                    break
        v.renamed = renamed
        v.relation = rel
        v.diffs = missing
        v.extra = extra
        v.merged = rel in ("as code", "alternative", "simplified")
        if rel == "project-specific":
            v.reason = "uses quantities the registry does not know: " + ", ".join(
                s[1:] for s in X.symbols(v.formula) if s.startswith(LOCAL))
        elif rel == "differs":
            v.reason = ("adds " + "; ".join(d.describe(lambda s: s) for d in extra) if extra
                        else "not a special case of the code expression")
    for v in out.variants:
        own = set(X.symbols(v.formula))
        for d in v.diffs:
            if d.kind == "term":
                z = zero_symbol(d.expr, own, observed)
                if z:
                    out.neutral[z] = 0.0
    n_src = len({s for v in out.variants if v.merged for s in v.sources})
    out.status = ("code" if not out.variants else
                  "differs" if any(v.relation == "differs" for v in out.variants) else
                  "applied" if n_src else "code")
    return out


# --------------------------------------------------------------------------
# why a source might simplify, and what it does to the result
# --------------------------------------------------------------------------
def explain(d: Diff, tax: Taxonomy, env: dict, per_width: bool, name) -> str:
    """One sentence on a simplification, evaluated for one source case where possible."""
    c = tax.concepts.get(d.sym) if d.sym else None
    if d.kind == "literal" and c is not None:
        rec = c.canonical_value
        if rec is not None and abs(rec - d.value) <= 1e-9 * max(1.0, abs(rec)):
            return f"writes in the recommended value {name(d.sym)} = {X._short(d.value)}"
        if c.ndp and rec is not None:
            return (f"uses {name(d.sym)} = {X._short(d.value)} instead of the recommended {X._short(rec)}: "
                    "a National Annex or project value")
        return f"writes the value {name(d.sym)} = {X._short(d.value)} into the formula"
    if d.kind == "factor" and c is not None:
        if c.strip and per_width:
            return f"works per unit width, so {name(d.sym)} = 1"
        if c.formula:
            try:
                val = X.evaluate(c.tree, env)
                if abs(val - 1.0) < 1e-9:
                    return f"leaves out {name(d.sym)}, which is 1 for this case: no effect"
                return f"leaves out {name(d.sym)}, which is {X._short(round(val, 4))} for this case"
            except X.ExprError:
                pass
        if c.canonical_value == 1.0:
            return (f"leaves out {name(d.sym)}: the recommended value 1 is assumed"
                    + (" (a National Annex may set another value)" if c.ndp else ""))
        return f"leaves out the factor {name(d.sym)} (taken as 1)"
    if d.kind == "term":
        try:
            if X.evaluate(d.expr, env) == 0:
                return f"leaves out {X.to_text(d.expr, name)}, which is zero for this case: no effect"
            return f"leaves out {X.to_text(d.expr, name)}, which is not zero for this case"
        except X.ExprError:
            return f"leaves out {X.to_text(d.expr, name)}"
    if d.kind == "bound":
        word = "lower" if d.fn == "max" else "upper"
        return f"omits the {word} bound {', '.join(X.to_text(a, name) for a in d.args)}"
    return d.describe(name)


def effect(sense: str, source_value, code_value) -> str:
    """Direction of a difference, read from the quantity's role."""
    if not isinstance(source_value, (int, float)) or not isinstance(code_value, (int, float)):
        return ""
    if abs(source_value - code_value) <= 1e-9 * max(1.0, abs(code_value)):
        return ""
    lower = source_value < code_value
    if sense == "resistance":
        return "on the safe side (lower resistance than the code)" if lower else \
            "on the unsafe side (higher resistance than the code)"
    if sense == "effect":
        return "on the unsafe side (lower than the code)" if lower else "on the safe side (higher than the code)"
    return "lower than the code" if lower else "higher than the code"
