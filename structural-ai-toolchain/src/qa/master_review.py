"""The AI Master Reviewer — the final gate before a tool is trusted.

A converted calc can *look* right and be wrong: a force computed in N but
labelled kN, a formula that adds a length to a force, a value that no
longer matches the original sheet. The reviewer finds those, FIXES what it
can prove, and re-checks until nothing it can fix is left.

Layers ("deterministic catches what it can, AI judges the rest")

1. Deterministic review (always, offline)
   - dimensional analysis of every formula and check (``dimensions.py``):
     non-homogeneous sums, a stress labelled as a force, a comparison of
     unlike quantities; empirical code formulas are recognised as such;
   - scale consistency for unit-naive sheets (Excel with manual
     conversions): recompute in canonical N/mm and catch power-of-ten
     slips — including in pass/fail checks, where a slip flips a verdict;
   - one-to-one correspondence with the ORIGINAL's values when they are
     known (Excel cached values, or values read from a print of the
     original), with a tolerance taken from the printed precision;
   - unresolved / non-finite results.
2. AI review (when an LLM is configured): the rendered report pages,
   the machine-readable calc and — if given — the original document go to
   the model, which returns findings plus concrete corrections.

``review_to_convergence`` runs the loop: review -> plan fixes ->
apply each candidate to a replayed copy of the sheet -> keep it only if
the re-run deterministic review is strictly better -> repeat until clean,
until nothing more can be fixed, or until ``max_iter``. Every applied fix
is logged on the sheet (``review_log``, embedded in the PDF) and shown as
a note next to the corrected step.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

import sympy as sp

from src.models.calculation import (
    _COMPARATORS,
    CalcSheet,
    CalcSheetError,
    fmt_number,
)
from src.qa import units as U
from src.qa.dimensions import analyse, describe_dim, sheet_dims, unit_dim


@dataclass
class ReviewFinding:
    severity: str            # 'error' | 'warning' | 'info'
    code: str
    location: str
    message: str
    suggested_fix: str = ""
    source: str = "deterministic"
    data: dict = field(default_factory=dict)

    def __str__(self) -> str:
        icon = {"error": "⛔", "warning": "⚠️ ", "info": "ℹ️ "}[self.severity]
        fix = f"  →fix: {self.suggested_fix}" if self.suggested_fix else ""
        tag = "" if self.source == "deterministic" else f" ({self.source})"
        return f"{icon} [{self.code}]{tag} {self.location}: {self.message}{fix}"


@dataclass
class Fix:
    """One correction the reviewer applied (or proposes)."""

    name: str
    action: str           # relabel | convert | set-expression | set-unit | set-value
    before: str
    after: str
    reason: str
    source: str = "deterministic"
    expression: str = ""
    unit: str = ""
    value: Optional[float] = None

    def as_log(self) -> dict:
        return {"name": self.name, "action": self.action,
                "before": self.before, "after": self.after,
                "reason": self.reason, "source": self.source}

    def __str__(self) -> str:
        return (f"🔧 {self.name}: {self.before} → {self.after} "
                f"({self.reason}; {self.source})")


@dataclass
class ReviewReport:
    findings: list[ReviewFinding] = field(default_factory=list)
    ai_used: bool = False
    ai_model: str = ""
    verdict: str = ""
    corrections: list[dict] = field(default_factory=list)   # AI-proposed
    fixes: list[Fix] = field(default_factory=list)          # applied
    iterations: int = 1
    converged: bool = False
    history: list[dict] = field(default_factory=list)

    def errors(self) -> list[ReviewFinding]:
        return [f for f in self.findings if f.severity == "error"]

    def warnings(self) -> list[ReviewFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    def passed(self) -> bool:
        return not self.errors()

    def __str__(self) -> str:
        lines = []
        if self.fixes:
            lines.append(f"Applied {len(self.fixes)} correction(s) in "
                         f"{self.iterations} iteration(s):")
            lines += [f"  {f}" for f in self.fixes]
        shown = [f for f in self.findings if f.severity != "info"]
        if not shown:
            lines.insert(0, "✔ Master review: no issues found.")
        else:
            lines += [str(f) for f in shown]
        infos = [f for f in self.findings if f.severity == "info"]
        if infos:
            lines.append(f"({len(infos)} informational note(s) — "
                         "see the full report)")
        return "\n".join(lines)


OriginalValues = dict  # name -> number | (number, unit) | {"value","unit","shown"}


# ------------------------------------------------------------------ #
# Deterministic review
# ------------------------------------------------------------------ #
def deterministic_review(sheet: CalcSheet,
                         original_values: OriginalValues | None = None
                         ) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    findings += _dimension_check(sheet)
    findings += _units_scale_check(sheet)
    findings += _check_scale_check(sheet)
    findings += _resolved_check(sheet)
    if original_values:
        findings += _correspondence_check(sheet, original_values, findings)
    return findings


def _parse(sheet: CalcSheet, expression: str):
    from src.knowledge_graph.fingerprint import parse_locals
    from src.models.calculation import _ALLOWED_FUNCTIONS

    local = parse_locals(expression)
    local.update(_ALLOWED_FUNCTIONS)
    return sp.sympify(expression, locals=local)


def _dimension_check(sheet: CalcSheet) -> list[ReviewFinding]:
    dims = sheet_dims(sheet)
    out: list[ReviewFinding] = []
    for item in sheet.calcs():
        try:
            expr = _parse(sheet, item.expression)
        except Exception:
            continue
        res = analyse(expr, dims)
        if not res.homogeneous:
            off_canon = [
                n for n in _refs(item.expression)
                if U.scale_of(sheet.units.get(n, "")) not in (None, 1.0)]
            if sheet.unit_aware or not off_canon:
                out.append(ReviewFinding(
                    "info", "empirical-formula", item.name,
                    f"'{item.name}' is an empirical (dimensionally "
                    f"non-homogeneous) formula — {'; '.join(res.conflicts)}. "
                    "It holds only in the code's own units; it is evaluated "
                    "in N, mm, MPa, the Eurocode convention."))
            else:
                out.append(ReviewFinding(
                    "warning", "empirical-formula-units", item.name,
                    f"Empirical formula '{item.name}' is fed with "
                    f"{', '.join(f'{n} [{sheet.units[n]}]' for n in off_canon)}"
                    " — code formulas of this kind expect N, mm, MPa.",
                    suggested_fix="express those inputs in mm / MPa"))
            continue
        declared = unit_dim(item.unit)
        if res.dim is None or declared is None:
            continue
        if res.dim != declared:
            literals = _magic_literals(item.expression)
            if literals and not sheet.unit_aware:
                # unit-naive source: a bare number may carry a hidden unit
                # (45e6 = 45 kNm in Nmm). Not provably wrong — but a
                # magic number that should become a labelled input.
                missing = (declared[0] - res.dim[0], declared[1] - res.dim[1])
                out.append(ReviewFinding(
                    "warning", "hidden-unit-literal", item.name,
                    f"'{item.name}' [{item.unit}] only balances if the number"
                    f"{'s' if len(literals) > 1 else ''} "
                    f"{', '.join(literals)} carr"
                    f"{'y' if len(literals) > 1 else 'ies'} a "
                    f"{describe_dim(missing)}.",
                    suggested_fix="define that number as a labelled input "
                                  "with its unit"))
                continue
            out.append(ReviewFinding(
                "error", "dimension-mismatch", item.name,
                f"'{item.name}' is declared in {item.unit} "
                f"({describe_dim(declared)}) but its formula yields a "
                f"{describe_dim(res.dim)}.",
                suggested_fix="correct the formula or the declared unit",
                data={"formula_dim": res.dim, "declared_dim": declared}))
    for chk in sheet.checks():
        sides = _check_sides(chk.expression)
        if sides is None:
            continue
        try:
            lhs = analyse(_parse(sheet, sides[0]), dims)
            rhs = analyse(_parse(sheet, sides[1]), dims)
        except Exception:
            continue
        if None not in (lhs.dim, rhs.dim) and lhs.dim != rhs.dim \
                and lhs.homogeneous and rhs.homogeneous:
            out.append(ReviewFinding(
                "error", "check-dimension-mismatch", chk.expression,
                f"The check compares a {describe_dim(lhs.dim)} with a "
                f"{describe_dim(rhs.dim)}.",
                suggested_fix="compare like with like"))
    return out


def _units_scale_check(sheet: CalcSheet) -> list[ReviewFinding]:
    """Unit-NAIVE sheets: recompute each derived quantity in canonical
    (N, mm) units and compare the natural scale with the declared unit.
    Unit-aware sheets convert by construction, so they are skipped."""
    if getattr(sheet, "unit_aware", False):
        return []
    findings: list[ReviewFinding] = []
    canon_vals = _canonical_values(sheet)
    for item in sheet.calcs():
        out_unit = item.unit
        out_scale = U.scale_of(out_unit) if out_unit else None
        if out_scale is None:
            continue
        as_written = item.value
        if as_written in (None, 0) or not _finite(as_written):
            continue
        refs = _refs(item.expression)
        if not refs or any(n not in canon_vals for n in refs):
            continue
        canon_value = _safe_eval(item.expression, canon_vals)
        if canon_value is None or not _finite(canon_value) or canon_value == 0:
            continue
        natural_scale = canon_value / as_written
        ratio = natural_scale / out_scale
        p = U.nearest_power_of_ten(ratio)
        if p is None or abs(p - 1.0) <= 0.5:
            continue
        # a DELIBERATE manual conversion (M*1e6 for kNm -> Nmm, (L/1000)**2
        # for mm -> m) inflates the canonical recomputation by exactly its
        # own factor: correct engineering, not a slip.
        if _explained_by_conversion_literals(item.expression, canon_vals,
                                             as_written, out_scale):
            continue
        corrected = canon_value / out_scale
        findings.append(ReviewFinding(
            "error", "unit-scale-mismatch", item.name,
            f"'{item.name}' is shown as {_fmt(as_written)} {out_unit} but "
            f"the formula evaluates to {_fmt(corrected)} {out_unit} "
            f"(off by ×{_fmt(p)} — a units slip).",
            suggested_fix=f"display {_fmt(corrected)} {out_unit}, or "
                          "reconcile the input units",
            data={"ratio": p, "natural_scale": natural_scale,
                  "corrected": corrected}))
    return findings


def _check_scale_check(sheet: CalcSheet) -> list[ReviewFinding]:
    """Unit-naive sheets: a check comparing e.g. kN with N gives the wrong
    verdict even when every number is 'right'. Re-evaluate both sides in
    canonical units; flag when the verdict flips."""
    if getattr(sheet, "unit_aware", False):
        return []
    canon_vals = _canonical_values(sheet)
    out: list[ReviewFinding] = []
    for chk in sheet.checks():
        sides = _check_sides(chk.expression)
        if sides is None:
            continue
        lhs_s, rhs_s = sides
        if _has_conversion_literal(lhs_s) or _has_conversion_literal(rhs_s):
            continue
        refs = _refs(lhs_s) | _refs(rhs_s)
        if not refs or any(n not in canon_vals for n in refs):
            continue
        lhs, rhs = _safe_eval(lhs_s, canon_vals), _safe_eval(rhs_s, canon_vals)
        if lhs is None or rhs is None:
            continue
        canonical_pass = _compare(chk.expression, lhs, rhs)
        if canonical_pass is not None and canonical_pass != chk.passed:
            out.append(ReviewFinding(
                "error", "check-verdict-units", chk.expression,
                f"Verdict is {'OK' if chk.passed else 'NOT OK'} as written, "
                f"but {'OK' if canonical_pass else 'NOT OK'} once units are "
                f"honoured ({_fmt(lhs)} vs {_fmt(rhs)} in N, mm).",
                suggested_fix="bring both sides of the check to one unit"))
    return out


def _resolved_check(sheet: CalcSheet) -> list[ReviewFinding]:
    findings = []
    for item in sheet.calcs():
        if item.value is None or not _finite(item.value):
            findings.append(ReviewFinding(
                "error", "unresolved-result", item.name,
                f"'{item.name}' did not resolve to a finite value — an "
                "upstream quantity is missing.",
                suggested_fix="resolve the referenced inputs, then re-grind"))
    return findings


def _correspondence_check(sheet: CalcSheet, original: OriginalValues,
                          prior: list[ReviewFinding]) -> list[ReviewFinding]:
    """Every value the original shows must be reproduced (one-to-one)."""
    results = sheet.results()
    slipped = {f.location for f in prior
               if f.code in ("unit-scale-mismatch", "dimension-mismatch")}
    out: list[ReviewFinding] = []
    for name, spec in original.items():
        v_orig, u_orig, shown = _normalise_original(spec)
        if v_orig is None:
            continue
        if name not in results:
            out.append(ReviewFinding(
                "warning", "missing-quantity", name,
                f"The original shows {name} = {shown or _fmt(v_orig)} "
                f"{u_orig}".rstrip() + " but the converted tool has no such "
                "quantity.", suggested_fix="add it or confirm it is noise"))
            continue
        produced = results[name]
        unit = sheet.units.get(name, "")
        if u_orig and unit and u_orig != unit:
            s_o, s_p = U.scale_of(u_orig), U.scale_of(unit)
            if s_o and s_p and U.dim_of(u_orig) == U.dim_of(unit):
                v_orig = v_orig * s_o / s_p
        if _agrees(produced, v_orig, shown):
            continue
        ratio = produced / v_orig if v_orig else None
        p = U.nearest_power_of_ten(abs(ratio)) if ratio else None
        if p is not None and abs(p - 1) > 0.5 and name not in slipped:
            out.append(ReviewFinding(
                "warning", "original-units-slip", name,
                f"The original shows {shown or _fmt(v_orig)} {u_orig or unit}"
                f" but the dimensionally verified value is {_fmt(produced)} "
                f"{unit} (×{_fmt(p)}): the ORIGINAL carries a units slip; "
                "the converted tool keeps the correct value.",
                data={"ratio": p}))
            continue
        out.append(ReviewFinding(
            "error", "correspondence-mismatch", name,
            f"Original shows {name} = {shown or _fmt(v_orig)} "
            f"{u_orig or unit}; converted tool gives {_fmt(produced)} {unit}.",
            suggested_fix="re-check the translated formula and its inputs",
            data={"original": v_orig, "produced": produced}))
    return out


# ------------------------------------------------------------------ #
# AI review
# ------------------------------------------------------------------ #
_AI_SYSTEM = """\
You are a chartered structural engineer doing the final independent check
of a calculation report before issue. You receive the rendered report
pages as images, the calculation as machine-readable JSON (inputs,
formulas, values in their display units, checks, code clauses), the
deterministic reviewer's findings, and — when available — the ORIGINAL
calculation the report was converted from.

Check, ruthlessly:
- every value, formula and verdict in the report against the ORIGINAL:
  the conversion must reproduce it one-to-one (values, units, conclusion);
- units are consistent and each result is shown in its stated unit;
- each formula is the one the cited code clause gives, with the right
  coefficients, and its validity limits are respected;
- nothing load-bearing from the original is missing or mislabelled.

Report only problems (silence means correct). For every problem you can
correct precisely, add an entry to "corrections": name the quantity, say
what the original shows and what the report shows, and give the corrected
formula (in the JSON's own expression syntax and variable names), unit or
input value. Leave a correction field empty when it does not apply. Do not
propose corrections you are not sure of; describe them as findings
instead."""


def ai_review(sheet: CalcSheet, client, page_images: list | None = None,
              original_document: Union[str, Path, bytes, None] = None,
              original_images: list | None = None,
              deterministic: list[ReviewFinding] | None = None,
              original_values: OriginalValues | None = None,
              ) -> tuple[list[ReviewFinding], list[dict], str]:
    """Ask the model to review the rendered report. Returns
    (findings, corrections, verdict); empty when no AI is available."""
    from src.llm import LLMError, schemas

    if client is None or not client.available():
        return [], [], ""
    import json

    det = "\n".join(f"- {f}" for f in (deterministic or [])) or "- none"
    orig = (json.dumps(original_values, default=str, indent=1)
            if original_values else "not provided")
    user = (f"Calculation JSON:\n{sheet.to_json()}\n\n"
            f"Deterministic findings:\n{det}\n\n"
            f"Values shown by the original (when known):\n{orig}\n\n"
            + ("The first document is the ORIGINAL calculation. "
               if original_document is not None else "")
            + ("The images are the rendered report pages"
               + (", followed by images of the original." if original_images
                  else ".")))
    images = list(page_images or []) + list(original_images or [])
    try:
        data = client.complete_json(
            _AI_SYSTEM, user, schema=schemas.REVIEW, images=images,
            documents=[original_document] if original_document is not None
            else [], task="review")
    except LLMError as exc:
        return [ReviewFinding("info", "ai-review-unavailable", "-",
                              f"AI review skipped: {exc}", source="ai")], [], ""
    findings = [ReviewFinding(
        f.get("severity", "warning"), f.get("code", "ai") or "ai",
        f.get("location", "-") or "-", f.get("message", ""),
        f.get("suggested_fix", ""), source="ai")
        for f in data.get("findings", [])]
    return findings, list(data.get("corrections", [])), data.get("verdict", "")


def extract_original_values(client, original_document, names: list[str]
                            ) -> OriginalValues:
    """Read the values the ORIGINAL shows (e.g. a PDF print of the Mathcad
    sheet) so the deterministic correspondence check can compare them."""
    from src.llm import LLMError, schemas

    if client is None or not client.available() or original_document is None:
        return {}
    system = ("You transcribe a structural calculation. For each requested "
              "quantity give the number exactly as printed, its unit, and "
              "the printed text; null when the quantity is not shown. Never "
              "compute anything yourself.")
    user = "Quantities: " + ", ".join(names)
    try:
        data = client.complete_json(
            system, user, schema=schemas.ORIGINAL_VALUES,
            documents=[original_document], task="original-values",
            effort="medium")
    except LLMError:
        return {}
    return {v["name"]: {"value": v["value"], "unit": v["unit"],
                        "shown": v["shown"]}
            for v in data.get("values", []) if v.get("value") is not None}


def review(sheet: CalcSheet, render_dir=None, client=None,
           original_image=None, original_document=None,
           original_values: OriginalValues | None = None) -> ReviewReport:
    """One full pass: deterministic + (when available) AI review."""
    from src.llm import describe

    report = ReviewReport()
    report.findings += deterministic_review(sheet, original_values)
    if client is not None and client.available():
        images = _render_pages(sheet, render_dir) if render_dir else []
        originals = [original_image] if original_image is not None else []
        ai_findings, corrections, verdict = ai_review(
            sheet, client, images, original_document, originals,
            report.findings, original_values)
        report.findings += ai_findings
        report.corrections = corrections
        report.verdict = verdict
        report.ai_used = True
        report.ai_model = describe(client)
    return report


# ------------------------------------------------------------------ #
# Convergence loop
# ------------------------------------------------------------------ #
def review_to_convergence(
    sheet: Union[CalcSheet, Callable[[], CalcSheet]],
    render_dir=None,
    client=None,
    max_iter: int = 8,
    original_values: OriginalValues | None = None,
    original_document=None,
    original_image=None,
) -> tuple[CalcSheet, ReviewReport]:
    """Review -> fix -> re-review until clean or no further progress.

    A fix is only kept when the re-run deterministic review of the patched
    sheet is strictly better (fewer errors, none new) — so a wrong AI
    suggestion cannot make the calculation worse, and a deterministic fix
    that would flip a downstream check is rejected in favour of the
    alternative that keeps the whole sheet consistent.
    """
    if callable(sheet) and not isinstance(sheet, CalcSheet):
        sheet = sheet()
    applied: list[Fix] = []
    history: list[dict] = []
    seen: set = set()
    report = ReviewReport()
    progressed = False
    for iteration in range(1, max_iter + 1):
        rdir = (Path(render_dir) / f"iter{iteration}") if render_dir else None
        report = review(sheet, rdir, client, original_image,
                        original_document, original_values)
        history.append({"iteration": iteration,
                        "errors": len(report.errors()),
                        "warnings": len(report.warnings()),
                        "verdict": report.verdict})
        state = _state(sheet, report)
        if state in seen:
            break
        seen.add(state)
        candidates = _plan_fixes(sheet, report)
        candidates += _ai_fixes(sheet, report.corrections)
        progressed = False
        for options in candidates:
            best = _best_option(sheet, options, original_values)
            if best is None:
                continue
            fix, patched = best
            sheet = patched
            sheet.review_log.append(fix.as_log())
            applied.append(fix)
            progressed = True
        if not progressed:
            break
    if progressed:
        # the last iteration changed the sheet: review the final state
        report = review(sheet, None, client, original_image,
                        original_document, original_values)
        history.append({"iteration": len(history) + 1,
                        "errors": len(report.errors()),
                        "warnings": len(report.warnings()),
                        "verdict": report.verdict})
    report.fixes = applied
    report.iterations = len(history)
    report.history = history
    ai_ok = (not report.ai_used) or report.verdict in ("APPROVE",
                                                       "APPROVE_WITH_COMMENTS")
    report.converged = report.passed() and ai_ok
    return sheet, report


def _plan_fixes(sheet: CalcSheet, report: ReviewReport) -> list[list[Fix]]:
    """Deterministic fixes. Each entry is a list of ALTERNATIVE fixes for
    one problem; ``_best_option`` keeps the one that leaves the sheet most
    consistent (or none, if every alternative makes it worse)."""
    plans: list[list[Fix]] = []
    items = {i.name: i for i in sheet.calcs()}
    for f in report.findings:
        if f.code != "unit-scale-mismatch" or f.location not in items:
            continue
        item = items[f.location]
        ratio = f.data.get("ratio")
        natural = f.data.get("natural_scale")
        options: list[Fix] = []
        conv = _conversion_suffix(ratio)
        if conv:
            options.append(Fix(
                item.name, "convert",
                f"{_fmt(item.value)} {item.unit}",
                f"{_fmt(f.data.get('corrected'))} {item.unit}",
                f"formula yields {U.unit_for(U.dim_of(item.unit), natural) or 'base units'}"
                f"; explicit conversion to {item.unit} added",
                expression=f"({item.expression}){conv}", unit=item.unit))
        relabel = U.unit_for(U.dim_of(item.unit) or (0, 0), natural or 1.0)
        if relabel and relabel != item.unit:
            options.append(Fix(
                item.name, "relabel",
                f"{_fmt(item.value)} {item.unit}",
                f"{_fmt(item.value)} {relabel}",
                f"the number is in {relabel}, the label said {item.unit}",
                expression=item.expression, unit=relabel))
        if options:
            plans.append(options)
    return plans


def _ai_fixes(sheet: CalcSheet, corrections: list[dict]) -> list[list[Fix]]:
    plans: list[list[Fix]] = []
    known = {i.name: i for i in sheet.items if i.kind in ("input", "calc")}
    for c in corrections or []:
        name = c.get("name", "")
        item = known.get(name)
        if item is None:
            continue
        expr = (c.get("proposed_expression") or "").strip()
        unit = (c.get("proposed_unit") or "").strip()
        value = c.get("proposed_value")
        reason = (f"AI: original shows {c.get('original', '?')}, report "
                  f"showed {c.get('produced', '?')}")
        if item.kind == "calc" and (expr or unit):
            plans.append([Fix(name, "set-expression" if expr else "set-unit",
                              f"{item.expression} [{item.unit}]",
                              f"{expr or item.expression} [{unit or item.unit}]",
                              reason, source="ai",
                              expression=expr or item.expression,
                              unit=unit or item.unit)])
        elif item.kind == "input" and (value is not None or unit):
            plans.append([Fix(name, "set-value",
                              f"{_fmt(item.value)} {item.unit}",
                              f"{_fmt(value if value is not None else item.value)}"
                              f" {unit or item.unit}", reason, source="ai",
                              value=value if value is not None else item.value,
                              unit=unit or item.unit)])
    return plans


def _apply(sheet: CalcSheet, fix: Fix) -> CalcSheet:
    def edit(item):
        if item.name != fix.name or item.kind not in ("calc", "input"):
            return item
        if item.kind == "calc":
            item.expression = fix.expression or item.expression
            item.unit = fix.unit or item.unit
        else:
            if fix.value is not None:
                item.value = float(fix.value)
            item.unit = fix.unit or item.unit
        item.note = (f"Reviewer correction — {fix.reason} "
                     f"({fix.before} → {fix.after}).")
        return item

    return sheet.replay(edit)


def _best_option(sheet: CalcSheet, options: list[Fix],
                 original_values: OriginalValues | None):
    base = _score(deterministic_review(sheet, original_values))
    best = None
    for fix in options:
        try:
            patched = _apply(sheet, fix)
        except CalcSheetError:
            continue
        score = _score(deterministic_review(patched, original_values))
        if score < base and (best is None or score < best[0]):
            # recompute 'after' text from the patched sheet (exact numbers)
            new_val = patched.results().get(fix.name)
            if new_val is not None:
                unit = fix.unit or sheet.units.get(fix.name, "")
                fix.after = f"{_fmt(new_val)} {unit}".strip()
            best = (score, fix, patched)
    if best is None:
        return None
    return best[1], best[2]


def _score(findings: list[ReviewFinding]) -> tuple:
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    return (errors, warnings)


def _state(sheet: CalcSheet, report: ReviewReport) -> tuple:
    vals = tuple(sorted((k, round(v, 9)) for k, v in sheet.results().items()
                        if _finite(v)))
    codes = tuple(sorted((f.code, f.location) for f in report.findings))
    return vals, codes


def _conversion_suffix(ratio: float | None) -> str:
    if not ratio:
        return ""
    k = round(math.log10(ratio))
    if k == 0:
        return ""
    factor = "1000" if abs(k) == 3 else f"10**{abs(k)}"
    return f"/{factor}" if k < 0 else f"*{factor}"


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #
def _render_pages(sheet: CalcSheet, render_dir) -> list:
    """Render the report to PNG page images for visual review (best-effort)."""
    import shutil
    import subprocess

    from src.output_engine import find_chromium, render_pdf_browser

    if render_dir is None or find_chromium() is None \
            or not shutil.which("pdftoppm"):
        return []
    render_dir = Path(render_dir)
    render_dir.mkdir(parents=True, exist_ok=True)
    pdf = render_pdf_browser(sheet, render_dir / "review.pdf")
    subprocess.run(["pdftoppm", "-png", "-r", "110", str(pdf),
                    str(render_dir / "page")], capture_output=True)
    return sorted(render_dir.glob("page*.png"))


def _check_sides(expression: str):
    comparator = next((c for c in _COMPARATORS if c in expression), None)
    if comparator is None:
        return None
    lhs, rhs = (s.strip() for s in expression.split(comparator, 1))
    return lhs, rhs


def _compare(expression: str, lhs: float, rhs: float):
    comparator = next((c for c in _COMPARATORS if c in expression), None)
    return {"<=": lhs <= rhs, ">=": lhs >= rhs, "==": lhs == rhs,
            "<": lhs < rhs, ">": lhs > rhs}.get(comparator)


def _canonical_values(sheet: CalcSheet) -> dict:
    out = {}
    for name, value in sheet.values.items():
        s = U.scale_of(sheet.units.get(name, ""))
        if s is not None:
            out[name] = value * s
    return out


def _explained_by_conversion_literals(expression: str, canon_vals: dict,
                                     as_written: float,
                                     out_scale: float) -> bool:
    """True when the scale mismatch is exactly the work of the formula's
    own power-of-ten conversion literals: with every such literal set to
    1, the canonical recomputation lands on the declared unit."""
    if not _conversion_literals(expression):
        return False
    stripped = _CONV_LITERAL.sub(
        lambda m: "1" if _is_conversion_literal(m.group(0)) else m.group(0),
        expression)
    value = _safe_eval(stripped, canon_vals)
    if value is None or not _finite(value) or value == 0:
        return False
    ratio = value / (as_written * out_scale)
    return abs(ratio - 1.0) < 0.02


_CONV_LITERAL = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?:\*\*\d+)?(?![\w.])")


def _is_conversion_literal(tok: str) -> bool:
    base, _, exp = tok.partition("**")
    try:
        val = float(base) ** (int(exp) if exp else 1)
    except (ValueError, OverflowError):
        return False
    return (val >= 1000 or 0 < val <= 1e-3) and \
        U.nearest_power_of_ten(val) is not None


def _conversion_literals(expression: str) -> list[str]:
    return [m.group(0) for m in _CONV_LITERAL.finditer(expression)
            if _is_conversion_literal(m.group(0))]


def _magic_literals(expression: str) -> list[str]:
    """Numbers in a formula other than small exact coefficients."""
    out = []
    for tok in re.findall(r"(?<![A-Za-z_])\d+(?:\.\d+)?(?:[eE][+-]?\d+)?",
                          expression):
        try:
            val = float(tok)
        except ValueError:
            continue
        if val in (0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 0.5):
            continue
        out.append(tok)
    return out


def _has_conversion_literal(expression: str) -> bool:
    return bool(_conversion_literals(expression))


def _normalise_original(spec):
    if isinstance(spec, dict):
        return (_num(spec.get("value")), spec.get("unit", "") or "",
                str(spec.get("shown", "") or ""))
    if isinstance(spec, (tuple, list)):
        value = spec[0]
        unit = spec[1] if len(spec) > 1 else ""
        return _num(value), unit or "", str(value) if isinstance(value, str) else ""
    if isinstance(spec, str):
        return _num(spec), "", spec
    return _num(spec), "", ""


def _num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"-?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?", str(x))
    return float(m.group(0).replace(",", ".")) if m else None


def _agrees(produced: float, original: float, shown: str) -> bool:
    """Equal within the precision the original was printed with."""
    if not _finite(produced):
        return False
    tol = max(abs(original) * 5e-4, 1e-12)
    m = re.search(r"\d+[.,](\d+)", shown or "")
    if m:
        tol = max(tol, 0.5 * 10 ** (-len(m.group(1))) * 1.0001)
    elif shown and re.fullmatch(r"\s*-?\d+\s*", shown):
        tol = max(tol, 0.5)
    return abs(produced - original) <= tol


def _refs(expression: str) -> set[str]:
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression))
    funcs = {"sqrt", "min", "max", "abs", "exp", "log", "ln", "pi", "sin",
             "cos", "tan", "cot", "sec", "csc", "asin", "acos", "atan",
             "floor", "ceiling", "sign", "Piecewise", "True", "False",
             "Eq", "Ne"}
    return {t for t in toks - funcs if not t.startswith("u__")}


def _safe_eval(expression: str, values: dict):
    from src.knowledge_graph.fingerprint import parse_locals
    from src.models.calculation import _ALLOWED_FUNCTIONS

    try:
        local = parse_locals(expression)
        local.update(_ALLOWED_FUNCTIONS)
        expr = sp.sympify(expression, locals=local)
        subs = {sp.Symbol(k): sp.Float(v) for k, v in values.items()}
        out = sp.N(expr.xreplace(subs))
        return float(out) if out.is_number else None
    except Exception:
        return None


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def _fmt(x) -> str:
    return fmt_number(x) if isinstance(x, (int, float)) else str(x)
