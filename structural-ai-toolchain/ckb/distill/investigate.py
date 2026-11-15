"""When a source and the code disagree: find out why before calling it a difference.

A benchmark that disagrees is only useful once it is understood.  Before a difference
is reported, these explanations are tried, cheapest first, each by recalculating:

    reading   an input was read from another calculation in the same file; the same
              quantity elsewhere in the file reproduces the source's value
    width     the two results differ by a width: one is per metre (or per unit width),
              the other for the full width
    unit      one input differs by a power of ten: a unit conversion
    value     one input with another value reproduces the source; the value is reported
              (often a project value, a National Annex value or a typing error)

What is explained is recorded as such, with a lesson where the explanation says
something general about how the logic is used (per-metre working, units).  What is
not explained becomes a question for an engineer, with everything that was tried.
When a language model is configured it is asked for its reading first; its answer
is attached to the question as a proposal, never accepted on its own.  An engineer's
answer (``ckb answer``) is applied in the next build, and a lesson they give becomes
design background of the object.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from .. import expr as X
from ..ir import close

WIDTH_FACTORS = (1000.0,)          # per metre against per millimetre
UNIT_FACTORS = (10.0, 100.0, 1000.0, 1e6, 1e9)
SCALE = 3.0                        # beyond this ratio a difference is investigated even if a reason was found


@dataclass
class Finding:
    cause: str                      # reading | width | unit | value | unexplained
    text: str
    status: str = ""                # new status of the benchmark, if it changes
    got: float | None = None
    inputs: dict | None = None
    lesson: str = ""                # general context worth keeping with the object
    question: dict | None = None


def question_id(concept: str, doc: str, loc: str) -> str:
    return "Q" + hashlib.sha1(f"{concept}|{doc}|{loc}".encode()).hexdigest()[:7]


def _eval(tree, env):
    try:
        v = X.evaluate(tree, env)
        return v if isinstance(v, (int, float)) and math.isfinite(v) else None
    except (X.ExprError, ZeroDivisionError, ValueError, OverflowError):
        return None


def _values_in_file(ctx, scope, p: str) -> list[tuple[float, object]]:
    """Every value the file gives to quantity p: [(canonical value, statement)]."""
    from .decompose import canonical_value
    out = []
    for i, _ in ctx.roles(scope).get(p, []):
        st = ctx.statements[i]
        if isinstance(st.best_value(), (int, float)):
            out.append((canonical_value(st, ctx.tax.concepts.get(p)), st))
    return out


def _solve_one(tree, env: dict, p: str, target: float):
    """A value of p that makes the tree give target (others unchanged), or None."""
    x0 = env[p]
    if not isinstance(x0, (int, float)) or x0 == 0:
        return None

    def f(m):
        v = _eval(tree, {**env, p: x0 * m})
        return None if v is None else v - target
    grid = [10 ** (k / 20) for k in range(-60, 61)]
    prev = None
    for m in grid:
        y = f(m)
        if y is None:
            prev = None
            continue
        if y == 0:
            return x0 * m
        if prev is not None and (prev[1] < 0) != (y < 0):
            lo, hi, ylo = prev[0], m, prev[1]
            for _ in range(80):
                mid = math.sqrt(lo * hi)
                ym = f(mid)
                if ym is None:
                    break
                if (ym < 0) == (ylo < 0):
                    lo, ylo = mid, ym
                else:
                    hi = mid
            v = x0 * math.sqrt(lo * hi)
            got = _eval(tree, {**env, p: v})
            if got is not None and close(got, target, rel=1e-6):
                return v
        prev = (m, y)
    return None


def investigate(b, reference, ctx, tax, concept, st, name, llm=None) -> Finding:
    """Explain why benchmark b (a source formula) and the code disagree."""
    env = dict(b.inputs)
    expected, got = b.expected, b.got
    tried = []
    numeric = [p for p in X.symbols(reference) if isinstance(env.get(p), (int, float))]

    # 1 reading: an input read from another calculation in the same file
    for p in numeric:
        origin = b.assumed.get(p, "")
        if not origin.startswith("from "):
            continue
        for v, other in _values_in_file(ctx, concept, p):
            if close(v, env[p], rel=1e-9):
                continue
            g = _eval(reference, {**env, p: v})
            if g is not None and close(g, expected, rel=1e-6):
                return Finding("reading", f"{name(p)} was first read from {origin[5:]}, which belongs to another "
                               f"calculation in the file; with {other.name} ({other.loc}) the source value is "
                               "reproduced", status="agree", got=g, inputs={**env, p: v})
    tried.append("inputs read from elsewhere in the file")

    ratio = got / expected if expected else float("inf")
    # 2 width: the results differ by a width of the same calculation, or by 1000 (per metre)
    widths = {}
    for c in tax.concepts.values():
        if c.strip:
            for v, other in _values_in_file(ctx, concept, c.id):
                if v > 1:
                    widths.setdefault(round(v, 6), f"{c.text} = {X._short(round(v, 3))} mm ({other.loc})")
    for w in WIDTH_FACTORS:
        widths.setdefault(w, "1 m = 1000 mm (per metre against per millimetre)")
    for w, what in widths.items():
        for r, side in ((w, "the code side"), (1 / w, "the source")):
            if close(ratio, r, rel=2e-3):
                return Finding("width", f"the results differ by the width {what}: one value is per unit width, the "
                               f"other for the full width ({side} has the full width); not comparable as it stands",
                               status="not comparable",
                               lesson=f"Check that every force in a per-metre calculation of {name(b.concept)} is per "
                                      "metre: a value for the full width taken into a per-metre calculation "
                                      "(or the reverse) is wrong by the width.")
    tried.append("a width between the two results")

    # 3 unit: one input off by a power of ten
    for p in numeric:
        for f in UNIT_FACTORS:
            for k in (f, 1 / f):
                g = _eval(reference, {**env, p: env[p] * k})
                if g is not None and close(g, expected, rel=1e-6):
                    return Finding("unit", f"{name(p)} differs by a factor of {X._short(k)}: the source probably "
                                   "uses it in another unit", status="not comparable", got=g,
                                   lesson=f"Check the unit of {name(p)}: sources have been found using it in a "
                                          f"unit {X._short(max(k, 1 / k))} times {'larger' if k < 1 else 'smaller'}.")
    tried.append("a unit factor on one input")

    # 4 value: one input with another value reproduces the source
    hints = []
    for p in numeric:
        v = _solve_one(reference, env, p, expected)
        if v is None:
            continue
        seen = [o for x, o in _values_in_file(ctx, concept, p) if close(x, v, rel=1e-5)]
        if seen:
            o = seen[0]
            return Finding("reading", f"the source value is reproduced with {name(p)} = {X._short(round(v, 6))} "
                           f"from {o.name} ({o.loc}) instead of {X._short(round(env[p], 6))}",
                           status="agree", got=_eval(reference, {**env, p: v}), inputs={**env, p: v})
        hints.append(f"{name(p)} = {X._short(round(v, 4))} instead of {X._short(round(env[p], 4))}")
    tried.append("one input with another value")

    q = {"id": question_id(b.concept, b.doc, b.loc), "object": b.concept, "source": b.doc, "where": b.loc,
         "case": b.case, "source_value": expected, "code_value": got,
         "inputs": {p: {"value": env[p], "from": b.assumed.get(p, "the source formula")} for p in numeric},
         "formula_in_source": getattr(st, "raw", "") or "", "label": getattr(st, "label", ""),
         "section": list(getattr(st, "section", []) or []), "tried": tried,
         "would_agree_if": hints[:3]}
    if llm is not None and getattr(llm, "available", lambda: False)():
        q["ai_proposal"] = _ask_model(llm, q, name)
    text = "not explained: " + ("; ".join(f"it would agree if {h}" for h in hints[:2]) if hints
                                 else "no single input or unit explains it")
    return Finding("unexplained", text + f" (question {q['id']} for an engineer)", question=q)


def _ask_model(llm, q: dict, name) -> dict:
    system = ("You review structural design calculations. A value in a source calculation does not match the "
              "design code expression evaluated with the same inputs. Explain the most likely cause in one or two "
              "sentences (for example per-metre against full-width working, a unit, a National Annex value, an "
              "input from another load case, a typing error). Answer as JSON: "
              '{"cause": "...", "explanation": "...", "confidence": "low|medium|high"}.')
    try:
        return llm.complete_json(system, str({k: q[k] for k in q if k != "id"}))
    except Exception as exc:                                      # noqa: BLE001
        return {"error": str(exc)}


def apply_answer(b, answer: dict) -> None:
    """An engineer's answer to a question about benchmark b."""
    verdict = answer.get("verdict", "explained")
    text = answer.get("answer", "").strip()
    b.detail = f"engineer: {text}" if text else f"engineer: {verdict}"
    if verdict in ("explained", "project-specific", "not comparable"):
        b.status = "not comparable"
    elif verdict in ("source error", "source-error"):
        b.status = "deviation"
        b.detail = f"an error in the source (engineer): {text}" if text else "an error in the source (engineer)"
