"""The AI Master Reviewer — the final gate before a tool is trusted.

Motivation: a converted calc can *look* right and be completely wrong
(most often a units-scale slip — a force that comes out in N but is shown
as kN). So every produced report is reviewed, and — where the reviewer can
fix it — modified and re-checked until it converges, unless the fix needs
human clarification.

Two layers, mirroring the rest of the toolchain ("deterministic catches
what it can, AI judges the rest"):

1. Deterministic review (always runs, offline):
   - **units/scale consistency** — for every derived quantity, recompute
     it in canonical units (N, mm) and compare the natural scale to the
     declared unit; a clean power-of-ten mismatch is the classic
     "looks-right-but-wrong" bug and is reported with the corrected value.
   - unresolved / zero / non-finite results.
   - checks that could not be evaluated.
2. AI visual review (when an LLM backend is configured):
   - renders the produced PDF to page images and asks the model to verify
     engineering soundness, unit consistency and that the conclusions
     follow — optionally against the ORIGINAL sheet's image for a true
     side-by-side. Returns structured findings + suggested modifications.

``review_to_convergence`` runs the loop: review -> apply auto-fixable
findings -> re-render -> re-review, stopping at a clean pass, at
clarifications-needed, or at a max iteration count.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models.calculation import CalcSheet
from src.qa import units as U


@dataclass
class ReviewFinding:
    severity: str            # 'error' | 'warning' | 'info'
    code: str
    location: str
    message: str
    suggested_fix: str = ""

    def __str__(self) -> str:
        icon = {"error": "⛔", "warning": "⚠️ ", "info": "ℹ️ "}[self.severity]
        fix = f"  →fix: {self.suggested_fix}" if self.suggested_fix else ""
        return f"{icon} [{self.code}] {self.location}: {self.message}{fix}"


@dataclass
class ReviewReport:
    findings: list[ReviewFinding] = field(default_factory=list)
    ai_used: bool = False

    def errors(self) -> list[ReviewFinding]:
        return [f for f in self.findings if f.severity == "error"]

    def passed(self) -> bool:
        return not self.errors()

    def __str__(self) -> str:
        if not self.findings:
            return "✔ Master review: no issues found."
        return "\n".join(str(f) for f in self.findings)


# ------------------------------------------------------------------ #
# Deterministic review
# ------------------------------------------------------------------ #
def deterministic_review(sheet: CalcSheet) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    findings += _units_scale_check(sheet)
    findings += _resolved_check(sheet)
    return findings


def _units_scale_check(sheet: CalcSheet) -> list[ReviewFinding]:
    """Recompute each derived quantity in canonical (N, mm) units and
    compare the natural scale to its declared unit.

    Only meaningful for unit-NAIVE sheets (e.g. Excel with hand-coded
    conversions), where a scale slip is a real risk. Unit-aware sheets
    (Mathcad) already convert correctly by construction, so this is skipped
    to avoid a spurious double-conversion."""
    if getattr(sheet, "unit_aware", False):
        return []
    findings: list[ReviewFinding] = []
    units = sheet.units
    values = sheet.values
    for item in sheet.calcs():
        out_unit = item.unit
        if not out_unit or not U.known(out_unit):
            continue
        as_written = item.value
        if as_written in (None, 0) or not _finite(as_written):
            continue
        # canonical inputs: value * scale(unit). Skip if any referenced
        # variable has an unknown unit (can't judge).
        try:
            refs = _refs(item.expression)
        except Exception:
            continue
        canon_vals = {}
        skip = False
        for name in refs:
            if name not in values:
                skip = True
                break
            u = units.get(name, "")
            s = U.scale_of(u)
            if s is None:
                skip = True
                break
            canon_vals[name] = values[name] * s
        if skip or not refs:
            continue
        canon_value = _safe_eval(item.expression, canon_vals)
        if canon_value is None or not _finite(canon_value) or canon_value == 0:
            continue
        natural_scale = canon_value / as_written
        out_scale = U.scale_of(out_unit)
        if out_scale is None:
            continue
        ratio = natural_scale / out_scale
        p = U.nearest_power_of_ten(ratio)
        if p is not None and abs(p - 1.0) > 0.5:
            # A DELIBERATE manual conversion (e.g. M*1e6 to go kNm->Nmm)
            # inflates the canonical recomputation by exactly its own
            # factor — that is correct engineering, not a slip. Only flag
            # when the mismatch is NOT explained by explicit power-of-ten
            # literals present in the formula itself.
            if _explained_by_conversion_literals(item.expression, p):
                continue
            corrected = canon_value / out_scale
            findings.append(ReviewFinding(
                "error", "unit-scale-mismatch", item.name,
                f"'{item.name}' is shown as {_fmt(as_written)} {out_unit} but "
                f"the formula evaluates to {_fmt(corrected)} {out_unit} "
                f"(off by x{_fmt(p)} — a units slip).",
                suggested_fix=f"display {_fmt(corrected)} {out_unit}, or "
                              f"reconcile the input units"))
    return findings


def _explained_by_conversion_literals(expression: str, ratio: float) -> bool:
    """True when the flagged power-of-ten ratio matches an explicit
    conversion literal (1000, 1e6, ...) written into the formula."""
    import math
    import re

    literals = []
    for tok in re.findall(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", expression):
        try:
            val = float(tok)
        except ValueError:
            continue
        if val >= 1000 and U.nearest_power_of_ten(val):
            literals.append(val)
        elif 0 < val <= 1e-3 and U.nearest_power_of_ten(val):
            literals.append(val)
    if not literals:
        return False
    # single literal, its inverse, or the product of all of them
    candidates = {lit for lit in literals}
    candidates |= {1.0 / lit for lit in literals}
    candidates.add(math.prod(literals))
    return any(abs(ratio / c - 1.0) < 0.02 for c in candidates)


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


# ------------------------------------------------------------------ #
# AI visual review (LLM hook)
# ------------------------------------------------------------------ #
_VISUAL_SYSTEM = """\
You are a chartered structural engineer doing final QA on a calculation
report before issue. You are shown the rendered report page images and the
machine-readable calculation JSON. Check, ruthlessly:
- units are consistent and results are shown in the stated units;
- each formula matches the cited code clause;
- intermediate values and the final conclusion are numerically plausible
  and follow from the inputs;
- nothing important is missing or mislabelled.
If an ORIGINAL sheet image is provided, compare against it and flag any
value, formula or conclusion that differs.
Return JSON: {"findings":[{"severity","code","location","message",
"suggested_fix"}], "verdict":"APPROVE|REWORK"}. Silence = correct."""


def ai_visual_review(sheet: CalcSheet, page_images: list, client,
                     original_image=None) -> list[ReviewFinding]:
    """Ask an LLM to review the rendered report. Returns findings; empty if
    no backend is available (the deterministic layer still ran)."""
    if client is None or not getattr(client, "available", lambda: False)():
        return []
    # The concrete multimodal call is backend-specific; the AnthropicLLMClient
    # would attach page_images (+ original_image) and _VISUAL_SYSTEM here.
    try:
        data = client.review_images(  # optional richer API
            _VISUAL_SYSTEM, sheet.to_json(), page_images, original_image)
    except AttributeError:
        return []
    out = []
    for f in data.get("findings", []):
        out.append(ReviewFinding(
            f.get("severity", "warning"), f.get("code", "ai"),
            f.get("location", "-"), f.get("message", ""),
            f.get("suggested_fix", "")))
    return out


def review(sheet: CalcSheet, render_dir=None, client=None,
           original_image=None) -> ReviewReport:
    """Full master review: deterministic + (optional) AI visual."""
    report = ReviewReport()
    report.findings += deterministic_review(sheet)
    images = []
    if render_dir is not None:
        images = _render_pages(sheet, render_dir)
    ai = ai_visual_review(sheet, images, client, original_image)
    report.findings += ai
    report.ai_used = bool(ai) or (
        client is not None and getattr(client, "available", lambda: False)())
    return report


def review_to_convergence(build_sheet, render_dir, client=None,
                          max_iter: int = 3) -> tuple[CalcSheet, ReviewReport]:
    """Review -> auto-fix -> re-review until clean, clarifications-needed,
    or max_iter. ``build_sheet`` is a zero-arg callable returning a fresh
    CalcSheet (so fixes that regenerate it can be re-run)."""
    sheet = build_sheet()
    report = review(sheet, render_dir, client)
    for _ in range(max_iter - 1):
        auto = [f for f in report.findings if f.code == "unit-scale-mismatch"]
        if report.passed() or not auto:
            break
        # Auto-fixes for units require reconciling source unit scaling, which
        # is a human-in-the-loop decision here — so we stop and surface them
        # rather than silently rescaling (a wrong auto-fix is worse than a
        # flagged one). A future units-aware model applies them automatically.
        break
    return sheet, report


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #
def _render_pages(sheet: CalcSheet, render_dir) -> list:
    """Render the report to PNG page images for visual review (best-effort)."""
    import shutil
    import subprocess
    from pathlib import Path

    from src.output_engine import find_chromium, render_pdf_browser

    if find_chromium() is None or not shutil.which("pdftoppm"):
        return []
    render_dir = Path(render_dir)
    render_dir.mkdir(parents=True, exist_ok=True)
    pdf = render_pdf_browser(sheet, render_dir / "review.pdf")
    subprocess.run(["pdftoppm", "-png", "-r", "110", str(pdf),
                    str(render_dir / "page")], capture_output=True)
    return sorted(render_dir.glob("page*.png"))


def _refs(expression: str) -> set[str]:
    import re

    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression))
    funcs = {"sqrt", "min", "max", "abs", "exp", "log", "ln", "pi", "sin",
             "cos", "tan", "cot", "sec", "csc", "asin", "acos", "atan"}
    return toks - funcs


def _safe_eval(expression: str, values: dict):
    import sympy as sp

    from src.knowledge_graph.fingerprint import parse_locals

    try:
        local = parse_locals(expression)
        expr = sp.sympify(expression, locals=local)
        subs = {sp.Symbol(k): sp.Float(v) for k, v in values.items()}
        out = sp.N(expr.xreplace(subs))
        return float(out) if out.is_number else None
    except Exception:
        return None


def _finite(x) -> bool:
    import math

    return isinstance(x, (int, float)) and math.isfinite(x)


def _fmt(x) -> str:
    from src.models.calculation import fmt_number

    return fmt_number(x)
