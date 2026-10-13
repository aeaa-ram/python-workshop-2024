"""Core calculation model — the Mathcad-style heart of the toolchain.

Design principle: **the calculation IS the visualization**. An engineer (or
The Grinder) declares a ``CalcSheet`` once; every step stores three parallel
representations that are guaranteed to stay in sync because they are derived
from the same symbolic expression:

1. the symbolic form            w_k = s_rmax * (eps_sm - eps_cm)
2. the substituted form         w_k = 199.6 * (0.00104)
3. the evaluated result         w_k = 0.207 mm

Renderers in ``src/output_engine`` walk the sheet and emit Markdown, LaTeX or
print-ready HTML without ever re-implementing the math, so the rendered report
always shows *live* values, never a stale hand-written print statement.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import sympy as sp

# Functions engineers may use inside formula strings.
_ALLOWED_FUNCTIONS = {
    "sqrt": sp.sqrt,
    "min": sp.Min,
    "max": sp.Max,
    "Min": sp.Min,
    "Max": sp.Max,
    "abs": sp.Abs,
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "cot": sp.cot,
    "sec": sp.sec,
    "csc": sp.csc,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "acot": sp.acot,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "log": sp.log,
    "ln": sp.log,
    "exp": sp.exp,
    "floor": sp.floor,
    "ceiling": sp.ceiling,
    "pi": sp.pi,
    "sign": sp.sign,
    "Eq": sp.Eq,
    "Ne": sp.Ne,
    "Piecewise": sp.Piecewise,
    "True": sp.true,
    "False": sp.false,
}

_COMPARATORS = ("<=", ">=", "==", "<", ">")

# A unit written inside a formula (Mathcad: ``h - 30 mm``) becomes a
# symbol ``u__mm`` whose value is the unit's canonical scale, so the
# arithmetic stays correct and the report still prints "30 mm".
UNIT_PREFIX = "u__"
_UNIT_TOKEN = re.compile(r"\bu__([A-Za-z0-9]+)\b")


def unit_symbol(unit: str) -> str:
    """Identifier that stands for ``unit`` inside a formula string."""
    return UNIT_PREFIX + re.sub(r"[^A-Za-z0-9]", "", unit)


def _is_numeric_literal(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _make_printer():
    from sympy.printing.latex import LatexPrinter

    class _ReportLatex(LatexPrinter):
        """sympy's LaTeX, restricted to what the offline renderer draws:
        conditionals print on one line instead of a ``cases`` block."""

        def _print_Piecewise(self, expr):
            parts = []
            for value, cond in expr.args:
                v = self._print(value)
                if cond is sp.true or cond == True:  # noqa: E712
                    parts.append(f"{v} \\;\\mathrm{{otherwise}}")
                else:
                    parts.append(f"{v} \\;\\mathrm{{if}}\\; {self._print(cond)}")
            return ",\\;\\; ".join(parts)

        def _print_And(self, expr):
            return " \\;\\mathrm{and}\\; ".join(self._print(a) for a in expr.args)

        def _print_Or(self, expr):
            return " \\;\\mathrm{or}\\; ".join(self._print(a) for a in expr.args)

    return _ReportLatex


_PRINTER_CLASS = None


def report_latex(expr, symbol_names: dict) -> str:
    global _PRINTER_CLASS
    if _PRINTER_CLASS is None:
        _PRINTER_CLASS = _make_printer()
    out = _PRINTER_CLASS(
        {"mul_symbol": "dot", "symbol_names": symbol_names}).doprint(expr)
    # a number times a unit symbol reads "30 mm", not "30 · mm"
    return re.sub(r"(\d)\s*\\cdot\s*(\\mathrm\{)", r"\1\\ \2", out)


_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def fmt_number(value: float, sig: int = 4, style: str = "plain") -> str:
    """Format a number with sensible significant digits for reports.

    Very large/small magnitudes use scientific notation, written the way
    the chosen medium expects: ``plain`` -> ``1.583e+06`` (machine text),
    ``latex`` -> ``1.583 \\cdot 10^{6}``, ``unicode`` -> ``1.583·10⁶``.
    """
    import math

    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    if value == 0:
        return "0"
    if abs(value) >= 1e6 or abs(value) < 1e-4:
        mantissa, exp = f"{value:.{sig - 1}e}".split("e")
        if style == "plain":
            return f"{mantissa}e{exp}"
        if "." in mantissa:
            mantissa = mantissa.rstrip("0").rstrip(".")
        n = int(exp)
        if style == "latex":
            return f"{mantissa} \\cdot 10^{{{n}}}"
        return f"{mantissa}·10{str(n).translate(_SUPERSCRIPT)}"
    from math import floor, log10

    digits = sig - 1 - floor(log10(abs(value)))
    digits = max(digits, 0)
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def is_dimensionless(unit: str) -> bool:
    return not unit or unit.strip() in ("-", "–", "—", "1")


def unit_latex(unit: str) -> str:
    """Render a plain unit string ('mm^2', 'kN/m') as LaTeX.

    Dash-only units mean 'dimensionless' and render as nothing.
    """
    if is_dimensionless(unit):
        return ""
    out = unit
    # a trailing digit right after a letter is an exponent: mm2 -> mm^2
    out = re.sub(r"([A-Za-z])(\d+)", r"\1^\2", out)
    out = re.sub(r"\^(\d+)", r"^{\1}", out)
    out = out.replace("%", r"\%")
    # Wrap the alphabetic parts in \mathrm so they are upright.
    out = re.sub(r"([A-Za-z]+)", r"\\mathrm{\1}", out)
    return out


@dataclass
class CalcItem:
    """One entry of a CalcSheet. ``kind`` is one of:
    'section', 'text', 'input', 'calc', 'check'.
    """

    kind: str
    name: str = ""
    description: str = ""
    unit: str = ""
    value: Optional[float] = None
    expression: str = ""            # source expression string (calc/check)
    latex_lhs: str = ""             # pretty symbol for the assigned variable
    latex_symbolic: str = ""        # right-hand side, symbolic
    latex_substituted: str = ""     # right-hand side, values substituted
    passed: Optional[bool] = None   # only for checks
    text: str = ""                  # only for 'text' items
    atom_id: str = ""               # library atom this step reuses, if any
    reference: str = ""             # code clause, shown right-aligned italic
    intro: str = ""                 # narrative shown under a section heading
    image_b64: str = ""             # 'image' items: base64 payload
    image_mime: str = "image/png"
    image_width_mm: int = 120
    note: str = ""                  # reviewer correction shown with the step


class CalcSheetError(Exception):
    pass


class CalcSheet:
    """An ordered, self-evaluating, self-documenting calculation.

    Example
    -------
    >>> sheet = CalcSheet(title="Demo")
    >>> sheet.define("b", 300, unit="mm", description="Width")
    >>> sheet.define("h", 500, unit="mm", description="Height")
    >>> step = sheet.calc("A", "b * h", unit="mm^2", description="Area")
    >>> step.value
    150000.0
    """

    def __init__(
        self,
        title: str,
        description: str = "",
        reference: str = "",
        author: str = "",
        project: str = "",
        revision: str = "0.1",
        tool_id: str = "",
        unit_aware: bool = False,
    ):
        self.title = title
        self.description = description
        self.reference = reference
        self.author = author
        self.project = project
        self.revision = revision
        self.tool_id = tool_id
        self.created = _dt.date.today().isoformat()
        self.items: list[CalcItem] = []
        # In unit-aware mode (e.g. Mathcad sheets, where formulas carry
        # units and contain NO manual unit conversions), ``values`` holds
        # each quantity in canonical units (N, mm), so the arithmetic is
        # dimensionally correct, and each result is converted back to its
        # declared unit for display. ``display_values`` holds the number as
        # shown. In the default (unit-naive) mode both are identical and the
        # behaviour is unchanged — for legacy Excel sheets that bake in
        # manual conversions like ``*1e6``.
        self.unit_aware = unit_aware
        self.values: dict[str, float] = {}
        self.display_values: dict[str, float] = {}
        self.units: dict[str, str] = {}
        self.latex_names: dict[str, str] = {}
        self.descriptions: dict[str, str] = {}
        self.unit_symbols: dict[str, str] = {}    # u__kN -> "kN"
        # what the master reviewer changed and why (machine-readable audit)
        self.review_log: list[dict] = []

    # ------------------------------------------------------------------ #
    def _register_unit_symbols(self, expression: str) -> None:
        from src.qa.units import scale_of

        for token in _UNIT_TOKEN.findall(expression):
            name = UNIT_PREFIX + token
            if name in self.unit_symbols:
                continue
            scale = scale_of(token)
            if scale is None:
                raise CalcSheetError(
                    f"Unknown unit {token!r} inside formula {expression!r}")
            self.unit_symbols[name] = token
            self.values[name] = scale if self.unit_aware else 1.0
            self.units[name] = token
            self.latex_names[name] = unit_latex(token)

    def _infer_unit(self, expr) -> str:
        """Unit of an unlabelled result in a unit-aware sheet: '-' when
        dimensionless, else the canonical unit of its dimension (N, mm,
        MPa, Nmm...). Empty when the dimension can't be established."""
        from src.qa.dimensions import DIMENSIONLESS, analyse, sheet_dims
        from src.qa.units import unit_for

        res = analyse(expr, sheet_dims(self))
        if not res.homogeneous or res.dim is None:
            return ""
        if res.dim == DIMENSIONLESS:
            return "-"
        if any(x.denominator != 1 for x in res.dim):
            return ""
        return unit_for((int(res.dim[0]), int(res.dim[1])), 1.0) or ""

    def _to_canonical(self, value: float, unit: str) -> float:
        if not self.unit_aware:
            return value
        from src.qa.units import scale_of

        s = scale_of(unit)
        return value * s if s is not None else value

    def _from_canonical(self, canonical: float, unit: str) -> float:
        if not self.unit_aware:
            return canonical
        from src.qa.units import scale_of

        s = scale_of(unit)
        return canonical / s if s not in (None, 0) else canonical

    # ------------------------------------------------------------------ #
    # Authoring API
    # ------------------------------------------------------------------ #
    def section(self, heading: str, intro: str = "") -> CalcItem:
        """A numbered section heading, with optional narrative intro that
        explains what the section does (the report 'tells a story')."""
        item = CalcItem(kind="section", name=heading, intro=intro)
        self.items.append(item)
        return item

    def text(self, paragraph: str) -> CalcItem:
        item = CalcItem(kind="text", text=paragraph)
        self.items.append(item)
        return item

    def image(
        self,
        data,
        caption: str = "",
        width_mm: int = 120,
        mime: str = "image/png",
    ) -> CalcItem:
        """Embed a sketch/figure (bytes, base64 str, or a file path).

        Rendered inline in the report at the position it is declared —
        so drawings sit exactly where the engineer wants them.
        """
        import base64 as _b64
        from pathlib import Path as _Path

        def _is_path(s) -> bool:
            if not isinstance(s, str) or len(s) > 400 or "\n" in s:
                return False
            try:
                return _Path(s).exists()
            except OSError:
                return False

        if isinstance(data, bytes):
            payload = _b64.b64encode(data).decode("ascii")
        elif _is_path(data):
            raw = _Path(data).read_bytes()
            payload = _b64.b64encode(raw).decode("ascii")
            suffix = _Path(data).suffix.lower().lstrip(".")
            mime = f"image/{'jpeg' if suffix in ('jpg', 'jpeg') else suffix}"
        else:
            payload = str(data)  # already base64
        item = CalcItem(
            kind="image", text=caption, image_b64=payload,
            image_mime=mime, image_width_mm=width_mm,
        )
        self.items.append(item)
        return item

    def define(
        self,
        name: str,
        value: float,
        unit: str = "",
        description: str = "",
        latex: Optional[str] = None,
        reference: str = "",
        note: str = "",
    ) -> CalcItem:
        """Declare an input parameter. ``note`` records a reviewer
        correction and is printed with the value."""
        canonical = self._to_canonical(float(value), unit)
        self._register(name, canonical, unit, description, latex)
        self.display_values[name] = float(value)
        item = CalcItem(
            kind="input",
            name=name,
            value=float(value),          # shown as-written in its own unit
            unit=unit,
            description=description,
            latex_lhs=self._latex_symbol(name),
            reference=reference,
            note=note,
        )
        self.items.append(item)
        return item

    def calc(
        self,
        name: str,
        expression: str,
        unit: str = "",
        description: str = "",
        latex: Optional[str] = None,
        reference: str = "",
        note: str = "",
    ) -> CalcItem:
        """Declare a derived quantity from a formula string.

        The formula may reference any previously defined variable and the
        functions sqrt/min/max/abs/sin/cos/tan/log/exp and the constant pi.
        ``reference`` is the code clause, shown right-aligned in italic
        next to the equation (Mathcad-style margin reference).
        """
        expr = self._parse(expression)
        canonical = self._evaluate(expr, expression)   # in canonical units
        if self.unit_aware and not unit:
            unit = self._infer_unit(expr)
        display_value = self._from_canonical(canonical, unit)
        if latex is not None:
            self.latex_names[name] = latex
        # Display uses a non-evaluated parse so the rendered formula
        # stays faithful to how it was written (e.g. sqrt(28/t) is NOT
        # rewritten to 2*sqrt(7)*sqrt(1/t) the way sympy's auto-eval
        # would). Numbers still come from the evaluated ``expr`` above.
        display = self._parse_display(expression)
        symbolic = self._latex_expr(display)
        substituted = self._latex_substituted(display)
        # downstream calcs use the canonical value; the report shows the
        # value converted to this quantity's declared unit.
        self._register(name, canonical, unit, description, latex)
        self.display_values[name] = display_value
        # a trailing "[clause]" in the description doubles as the reference
        if not reference:
            import re as _re
            m = _re.search(r"\[([^\]]+)\]\s*$", description)
            if m:
                reference = m.group(1).strip()
                description = description[: m.start()].strip()
        item = CalcItem(
            kind="calc",
            name=name,
            value=display_value,
            unit=unit,
            description=description,
            expression=expression,
            latex_lhs=self._latex_symbol(name),
            latex_symbolic=symbolic,
            latex_substituted=substituted,
            reference=reference,
            note=note,
        )
        self.items.append(item)
        return item

    def check(self, expression: str, description: str = "",
              reference: str = "") -> CalcItem:
        """Declare a pass/fail verification, e.g. ``"w_k <= w_max"``."""
        comparator = next((c for c in _COMPARATORS if c in expression), None)
        if comparator is None:
            raise CalcSheetError(
                f"Check '{expression}' needs one of {_COMPARATORS}"
            )
        lhs_str, rhs_str = (s.strip() for s in expression.split(comparator, 1))
        lhs = self._evaluate(self._parse(lhs_str), lhs_str)
        rhs = self._evaluate(self._parse(rhs_str), rhs_str)
        passed = {
            "<=": lhs <= rhs,
            ">=": lhs >= rhs,
            "==": lhs == rhs,
            "<": lhs < rhs,
            ">": lhs > rhs,
        }[comparator]
        comp_latex = {"<=": r"\le", ">=": r"\ge", "==": "=", "<": "<", ">": ">"}
        # an expression side (e.g. 0.8*P_Rd) is shown in the unit of the
        # variable it is compared with — a valid comparison shares dimension
        lhs_unit = self.units.get(lhs_str, "")
        rhs_unit = self.units.get(rhs_str, "")
        if lhs_str not in self.units and not _is_numeric_literal(lhs_str):
            lhs_unit = rhs_unit
        if rhs_str not in self.units and not _is_numeric_literal(rhs_str):
            rhs_unit = lhs_unit
        # display numbers in their declared units (converted from canonical)
        lhs_disp = self._from_canonical(lhs, lhs_unit)
        rhs_disp = self._from_canonical(rhs, rhs_unit)
        def side(text: str, value: float, unit: str) -> str:
            # a bare number needs no "= number" echo (e.g. "UR <= 1.0")
            shown = self._latex_expr(self._parse_display(text))
            num = fmt_number(value, style="latex")
            if _is_numeric_literal(text):
                return f"{num}{self._unit_suffix(unit)}"
            return f"{shown} = {num}{self._unit_suffix(unit)}"

        sym = (f"{side(lhs_str, lhs_disp, lhs_unit)} \\; "
               f"{comp_latex[comparator]} \\; "
               f"{side(rhs_str, rhs_disp, rhs_unit)}")
        item = CalcItem(
            kind="check",
            name=expression,
            description=description,
            expression=expression,
            latex_symbolic=sym,
            passed=bool(passed),
            reference=reference,
        )
        self.items.append(item)
        return item

    def apply(
        self,
        name: str,
        atom,
        unit: str = "",
        description: str = "",
        subs: Optional[dict[str, str]] = None,
        latex: Optional[str] = None,
        jurisdiction: str = "EN",
        define_params: bool = True,
    ) -> CalcItem:
        """Reuse a library atom (single source of truth) as a calc step.

        ``atom`` is an Atom instance or its id/concept string.
        ``jurisdiction`` selects the national-annex variant: a parameter
        override (same formula, different coefficient) or a full
        alternative atom sharing the concept. Code coefficients (params)
        are auto-defined as inputs with their effective values so they
        show in the report and drive the calc symbolically.
        ``subs`` maps the atom's canonical symbols to this sheet's names.
        """
        from src.library import get_atom, resolve

        if not isinstance(atom, str):
            concept = atom.concept
        else:
            try:
                concept = get_atom(atom).concept
            except Exception:
                concept = atom
        resolved = resolve(concept, jurisdiction)
        atom_obj = resolved.atom
        subs = dict(subs or {})

        if define_params:
            for pname, pval in resolved.params.items():
                target = subs.get(pname, pname)
                if target not in self.values:
                    juris_note = (
                        f" [{jurisdiction} coefficient]"
                        if jurisdiction != "EN" else " [code coefficient]"
                    )
                    self.define(
                        target, pval,
                        unit=atom_obj.units.get(pname, "-"),
                        description=f"{atom_obj.result} coefficient"
                                    f"{juris_note}",
                    )

        expression = atom_obj.expression_for(subs)
        provenance = " / ".join(p for p in resolved.provenance if p)
        item = self.calc(
            name,
            expression,
            unit=unit or atom_obj.units.get(atom_obj.result, ""),
            description=description
            or (f"{atom_obj.description} [{provenance}]" if provenance
                else atom_obj.description),
            latex=latex,
        )
        item.atom_id = atom_obj.atom_id
        return item

    # ------------------------------------------------------------------ #
    # Introspection (used by renderers and the knowledge graph)
    # ------------------------------------------------------------------ #
    def inputs(self) -> list[CalcItem]:
        return [i for i in self.items if i.kind == "input"]

    def calcs(self) -> list[CalcItem]:
        return [i for i in self.items if i.kind == "calc"]

    def checks(self) -> list[CalcItem]:
        return [i for i in self.items if i.kind == "check"]

    def checks_result_vars(self) -> list[CalcItem]:
        """The LHS quantity of each check (e.g. 'w_k' from 'w_k <= w_max'),
        used as the default columns of a parametric summary table."""
        out: list[CalcItem] = []
        seen: set[str] = set()
        calc_by_name = {c.name: c for c in self.calcs()}
        for chk in self.checks():
            comparator = next((c for c in _COMPARATORS if c in chk.expression), None)
            if not comparator:
                continue
            lhs = chk.expression.split(comparator, 1)[0].strip()
            if lhs in calc_by_name and lhs not in seen:
                out.append(calc_by_name[lhs])
                seen.add(lhs)
        return out or self.calcs()[-1:]  # fallback: last computed quantity

    def results(self) -> dict[str, float]:
        """Results in each quantity's DISPLAY unit (what the report shows).
        In unit-aware mode this differs from the internal canonical values;
        in the default mode the two are identical."""
        out = {k: v for k, v in self.values.items()
               if k not in self.unit_symbols}
        if self.unit_aware:
            out.update(self.display_values)
        return out

    def canonical_results(self) -> dict[str, float]:
        return {k: v for k, v in self.values.items()
                if k not in self.unit_symbols}

    def all_passed(self) -> bool:
        return all(i.passed for i in self.checks())

    def input_names(self) -> list[str]:
        return [i.name for i in self.inputs()]

    def recompute(self, overrides: dict[str, float]) -> dict:
        """Re-run the SAME calculation with different input values.

        Reuses the stored formulas (no rebuild) — this powers parametric
        studies: run one tool over many load cases and tabulate. Returns
        ``{"values", "results", "checks":[(expr, passed)], "passed"}``.
        Overrides and returned numbers are in each quantity's DISPLAY unit
        (what the engineer reads in the report), in both unit modes.
        Unknown override names raise, so typos can't silently pass.
        """
        names = set(self.input_names())
        unknown = [k for k in overrides if k not in names]
        if unknown:
            raise CalcSheetError(
                f"recompute got unknown inputs {unknown}; "
                f"inputs are {self.input_names()}"
            )
        vals = {n: self.values[n] for n in self.input_names()}
        vals.update({n: self.values[n] for n in self.unit_symbols})
        for k, v in overrides.items():
            vals[k] = self._to_canonical(float(v), self.units.get(k, ""))
        results: dict[str, float] = {}
        for item in self.items:
            if item.kind == "calc":
                vals[item.name] = self._eval_with(item.expression, vals)
                results[item.name] = self._from_canonical(
                    vals[item.name], item.unit)
        checks: list[tuple[str, bool]] = []
        for item in self.checks():
            checks.append((item.expression, self._eval_check(item.expression, vals)))
        shown = {k: self._from_canonical(v, self.units.get(k, ""))
                 for k, v in vals.items() if k not in self.unit_symbols}
        return {
            "values": shown,
            "results": results,
            "checks": checks,
            "passed": all(p for _, p in checks) if checks else None,
        }

    def replay(self, edit=None) -> "CalcSheet":
        """Rebuild the sheet from its own items, optionally editing them.

        ``edit(item) -> CalcItem | None`` may return a modified copy of an
        item (new expression, unit, value...) or ``None`` to drop it. Every
        downstream value, substituted line and check verdict is re-derived,
        so a correction can never leave a stale number in the report. Used
        by the master reviewer to apply and re-verify its fixes.
        """
        import copy

        new = CalcSheet(self.title, self.description, self.reference,
                        self.author, self.project, self.revision,
                        self.tool_id, self.unit_aware)
        new.created = self.created
        new.review_log = list(self.review_log)
        for original in self.items:
            item = copy.copy(original)
            if edit is not None:
                item = edit(item)
                if item is None:
                    continue
            latex = self.latex_names.get(item.name) \
                if item.name in self.latex_names else None
            if item.kind == "section":
                new.section(item.name, intro=item.intro)
            elif item.kind == "text":
                new.text(item.text)
            elif item.kind == "image":
                new.image(item.image_b64, caption=item.text,
                          width_mm=item.image_width_mm, mime=item.image_mime)
            elif item.kind == "input":
                new.define(item.name, item.value, unit=item.unit,
                           description=item.description, latex=latex,
                           reference=item.reference).note = item.note
            elif item.kind == "calc":
                step = new.calc(item.name, item.expression, unit=item.unit,
                                description=item.description, latex=latex,
                                reference=item.reference)
                step.atom_id = item.atom_id
                step.note = item.note
            elif item.kind == "check":
                new.check(item.expression, description=item.description,
                          reference=item.reference)
        return new

    def _eval_with(self, expression: str, vals: dict[str, float]) -> float:
        from src.knowledge_graph.fingerprint import parse_locals

        local = parse_locals(expression)
        local.update(_ALLOWED_FUNCTIONS)
        expr = sp.sympify(expression, locals=local)
        subs = {sp.Symbol(k): sp.Float(v) for k, v in vals.items()}
        out = sp.N(expr.xreplace(subs))
        if not out.is_number:
            raise CalcSheetError(f"{expression!r} did not evaluate")
        return float(out)

    def _eval_check(self, expression: str, vals: dict[str, float]) -> bool:
        comparator = next((c for c in _COMPARATORS if c in expression), None)
        lhs_s, rhs_s = (s.strip() for s in expression.split(comparator, 1))
        lhs, rhs = self._eval_with(lhs_s, vals), self._eval_with(rhs_s, vals)
        return {
            "<=": lhs <= rhs, ">=": lhs >= rhs, "==": lhs == rhs,
            "<": lhs < rhs, ">": lhs > rhs,
        }[comparator]

    # ------------------------------------------------------------------ #
    # Machine-readable serialization (embedded in every generated PDF so
    # future AI/tooling can read the calculation without OCR)
    # ------------------------------------------------------------------ #
    SCHEMA = "structural-ai-toolchain/calcsheet@1"

    def to_dict(self) -> dict:
        return {
            "schema": self.SCHEMA,
            "tool_id": self.tool_id,
            "title": self.title,
            "description": self.description,
            "reference": self.reference,
            "author": self.author,
            "project": self.project,
            "revision": self.revision,
            "created": self.created,
            "items": [
                {
                    "kind": i.kind,
                    "name": i.name,
                    "description": i.description,
                    "unit": i.unit,
                    "value": i.value,
                    "expression": i.expression,
                    "passed": i.passed,
                    "text": i.text,
                    "atom_id": i.atom_id,
                    "reference": i.reference,
                    "intro": i.intro,
                    **({"note": i.note} if i.note else {}),
                    # images: fingerprint only, so the in-PDF machine-readable
                    # layer stays compact (payload lives in the HTML itself)
                    **({"image_sha1": __import__("hashlib").sha1(
                            i.image_b64.encode()).hexdigest()[:12],
                        "image_bytes": len(i.image_b64) * 3 // 4}
                       if i.kind == "image" and i.image_b64 else {}),
                }
                for i in self.items
            ],
            "results": self.results(),
            "units": {k: v for k, v in self.units.items()
                      if k not in self.unit_symbols},
            "unit_aware": self.unit_aware,
            "checks_passed": self.all_passed() if self.checks() else None,
            **({"review_log": self.review_log} if self.review_log else {}),
        }

    def to_json(self, indent: int = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _register(
        self,
        name: str,
        value: float,
        unit: str,
        description: str,
        latex: Optional[str],
    ) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise CalcSheetError(f"Invalid variable name: {name!r}")
        if name in _ALLOWED_FUNCTIONS:
            raise CalcSheetError(f"{name!r} shadows a built-in function")
        self.values[name] = value
        self.units[name] = unit
        self.descriptions[name] = description
        if latex is not None:
            self.latex_names[name] = latex

    def _parse(self, expression: str) -> sp.Expr:
        # Map every identifier in the expression to a Symbol FIRST, so
        # sympy cannot hijack names (bare 'E' would otherwise parse as
        # Euler's number and silently evaluate instead of raising
        # "undefined variable"). Defined variables and functions then
        # override on top.
        from src.knowledge_graph.fingerprint import parse_locals

        self._register_unit_symbols(expression)
        local = parse_locals(expression)
        local.update({n: sp.Symbol(n) for n in self.values})
        local.update(_ALLOWED_FUNCTIONS)
        try:
            expr = sp.sympify(expression, locals=local)
        except (sp.SympifyError, SyntaxError, TypeError) as exc:
            raise CalcSheetError(
                f"Cannot parse expression {expression!r}: {exc}"
            ) from exc
        unknown = {
            s.name for s in expr.free_symbols if s.name not in self.values
        }
        if unknown:
            raise CalcSheetError(
                f"Expression {expression!r} uses undefined variables: "
                f"{sorted(unknown)}"
            )
        return expr

    def _parse_display(self, expression: str) -> sp.Expr:
        """Parse WITHOUT auto-simplification, for faithful rendering.

        Falls back to the normal evaluated parse if the non-evaluated
        parse fails for any reason (display should never crash a sheet
        that evaluates fine).
        """
        from src.knowledge_graph.fingerprint import parse_locals

        local = parse_locals(expression)
        local.update({n: sp.Symbol(n) for n in self.values})
        local.update(_ALLOWED_FUNCTIONS)
        try:
            with sp.evaluate(False):
                return sp.sympify(expression, locals=local, evaluate=False)
        except (sp.SympifyError, SyntaxError, TypeError, AttributeError):
            return self._parse(expression)

    def _evaluate(self, expr: sp.Expr, source: str) -> float:
        import math

        subs = {sp.Symbol(n): sp.Float(v) for n, v in self.values.items()}
        result = expr.xreplace(subs)
        result = sp.N(result)
        if not result.is_number:
            raise CalcSheetError(f"Expression {source!r} did not evaluate")
        try:
            out = float(result)
        except TypeError as exc:
            # zoo (division by zero) / complex results
            raise CalcSheetError(
                f"Expression {source!r} is undefined ({exc})") from exc
        if not math.isfinite(out):
            # a division by an unresolved (0) upstream value, etc. — treat
            # as unevaluable so it is flagged, not silently propagated.
            raise CalcSheetError(
                f"Expression {source!r} is non-finite ({out}); an upstream "
                "value is unresolved")
        return out

    def _pretty(self, name: str) -> str:
        """LaTeX for a symbol: explicit override, else naming convention."""
        from src.models.naming import symbol_to_latex

        return self.latex_names.get(name) or symbol_to_latex(name)

    def _latex_symbol(self, name: str) -> str:
        return self._pretty(name)

    def _symbol_names(self, expr: sp.Expr) -> dict:
        """Map every free symbol to its pretty LaTeX for sympy's printer.

        Using sympy's ``symbol_names`` is robust (no fragile string
        replacement) and applies the naming convention to every variable.
        """
        return {s: self._pretty(s.name) for s in expr.free_symbols}

    def _latex_expr(self, expr: sp.Expr) -> str:
        return report_latex(expr, self._symbol_names(expr))

    def _value_latex(self, name: str, as_base: bool) -> str:
        """One substituted operand. Unit-aware sheets show each value with
        its own unit (Mathcad style: ``0.8·450 MPa·π·(19 mm)²``), which is
        dimensionally honest whatever unit the result is shown in."""
        if self.unit_aware:
            value = self.display_values.get(name, self.values[name])
            unit = unit_latex(self.units.get(name, ""))
        else:
            value, unit = self.values[name], ""
        text = fmt_number(value, style="latex")
        body = f"{text}\\ {unit}" if unit else text
        if value < 0 or (as_base and (unit or "10^" in text)):
            body = f"\\left({body}\\right)"
        return body

    def _latex_substituted(self, expr: sp.Expr) -> str:
        half = sp.Rational(1, 2)
        no_paren_exps = (half, -half, sp.Integer(-1))
        names: dict = {}
        base_subs: dict = {}
        with sp.evaluate(False):
            for p in expr.atoms(sp.Pow):
                b = p.base
                if (isinstance(b, sp.Symbol) and b.name in self.values
                        and b.name not in self.unit_symbols
                        and p.exp not in no_paren_exps):
                    ph = sp.Symbol(f"{b.name}__pbase")
                    names[ph] = self._value_latex(b.name, as_base=True)
                    base_subs[p] = sp.Pow(ph, p.exp, evaluate=False)
            replaced = expr.xreplace(base_subs) if base_subs else expr
            for s in replaced.free_symbols:
                if s in names:
                    continue
                if s.name in self.unit_symbols:
                    names[s] = self.latex_names[s.name]
                elif s.name in self.values:
                    names[s] = self._value_latex(s.name, as_base=False)
            # evaluate(False) so injecting the numbers does not re-trigger
            # simplification and undo the faithful display structure.
            return report_latex(replaced, names)

    def _unit_suffix(self, unit: str) -> str:
        rendered = unit_latex(unit)
        return f"\\ {rendered}" if rendered else ""


@dataclass
class ParsedVariable:
    """A variable extracted by an ingestion parser (pre-standardization)."""

    name: str
    value: Optional[float] = None
    unit: str = ""
    description: str = ""
    role: str = "input"  # 'input' | 'derived'
    expression: str = ""  # only for derived variables
    source_cell: str = ""     # provenance, e.g. "Sheet1!C7" (AI grinder)
    source_formula: str = ""  # original Excel formula, if any
    note: str = ""            # reviewer correction, printed with the step
    reference: str = ""       # code clause (e.g. from a matched atom)
    atom_id: str = ""         # library atom this formula is


@dataclass
class Clarification:
    """A specific human-in-the-loop question the parser could not resolve.

    Emitted instead of silently guessing or failing — points at the exact
    cell/logic and, where possible, offers options.
    """

    location: str          # e.g. "Sheet2!D14" or a variable name
    issue: str             # short machine tag, e.g. "magic-number"
    question: str          # human-readable question
    options: list[str] = field(default_factory=list)
    context: str = ""      # the raw formula / value for reference

    def __str__(self) -> str:
        opts = f"  options: {self.options}" if self.options else ""
        return f"❓ [{self.issue}] {self.location}: {self.question}{opts}"


@dataclass
class ParsedTool:
    """Neutral in-memory form of an ingested legacy file.

    Every parser in ``src/ingestion`` produces this; the Grinder turns it
    into a standardized Python + Markdown tool in ``/repository``.
    """

    title: str
    source_path: str
    source_format: str  # 'xlsx' | 'ipynb' | 'py' | 'mcdx'
    description: str = ""
    reference: str = ""
    variables: list[ParsedVariable] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    clarifications: list[Clarification] = field(default_factory=list)
    interpreter: str = ""   # which interpreter produced this (llm/heuristic)
    unit_aware: bool = False  # source carries units (e.g. Mathcad)
    review_log: list = field(default_factory=list)  # reviewer corrections

    def needs_clarification(self) -> bool:
        return bool(self.clarifications)

    def to_sheet(self) -> CalcSheet:
        """Build an executable CalcSheet from the parsed content.

        Resilient: a derived formula that will not evaluate (e.g. an
        unresolved lookup from a messy sheet) is downgraded to a warning
        and, if it has a cached value, kept as an input — so one bad cell
        never sinks the whole conversion.
        """
        sheet = CalcSheet(
            title=self.title,
            description=self.description,
            reference=self.reference,
            unit_aware=self.unit_aware,
        )
        sheet.review_log = list(self.review_log)
        inputs = [v for v in self.variables if v.role == "input"]
        derived = [v for v in self.variables if v.role == "derived"]
        if inputs:
            sheet.section("Input Parameters")
            for var in inputs:
                try:
                    sheet.define(
                        var.name, var.value if var.value is not None else 0.0,
                        unit=var.unit, description=var.description,
                        note=var.note,
                    )
                except CalcSheetError as exc:
                    self.warnings.append(f"Input '{var.name}' skipped: {exc}")
        if derived:
            sheet.section("Calculation")
            for var in derived:
                try:
                    sheet.calc(
                        var.name, var.expression, unit=var.unit,
                        description=var.description, note=var.note,
                        reference=var.reference,
                    ).atom_id = var.atom_id
                except CalcSheetError as exc:
                    self.warnings.append(
                        f"Formula '{var.name}' ({var.source_cell or '?'}) "
                        f"could not be converted and was kept as an input: "
                        f"{exc}"
                    )
                    if var.name not in sheet.values:
                        sheet.define(
                            var.name,
                            var.value if var.value is not None else 0.0,
                            unit=var.unit,
                            description=(var.description
                                         + " [unresolved formula]").strip(),
                        )
        if self.checks:
            sheet.section("Verification")
            for chk in self.checks:
                try:
                    sheet.check(chk)
                except CalcSheetError as exc:
                    self.warnings.append(f"Check '{chk}' skipped: {exc}")
        return sheet
