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
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "log": sp.log,
    "ln": sp.log,
    "exp": sp.exp,
    "pi": sp.pi,
}

_COMPARATORS = ("<=", ">=", "==", "<", ">")


def fmt_number(value: float, sig: int = 4) -> str:
    """Format a number with sensible significant digits for reports."""
    if value == 0:
        return "0"
    if abs(value) >= 1e6 or abs(value) < 1e-4:
        return f"{value:.{sig - 1}e}"
    from math import floor, log10

    digits = sig - 1 - floor(log10(abs(value)))
    digits = max(digits, 0)
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def unit_latex(unit: str) -> str:
    """Render a plain unit string ('mm^2', 'kN/m') as LaTeX.

    Dash-only units mean 'dimensionless' and render as nothing.
    """
    if not unit or unit.strip() in ("-", "–", "—"):
        return ""
    out = unit
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
        self.values: dict[str, float] = {}
        self.units: dict[str, str] = {}
        self.latex_names: dict[str, str] = {}
        self.descriptions: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Authoring API
    # ------------------------------------------------------------------ #
    def section(self, heading: str) -> CalcItem:
        item = CalcItem(kind="section", name=heading)
        self.items.append(item)
        return item

    def text(self, paragraph: str) -> CalcItem:
        item = CalcItem(kind="text", text=paragraph)
        self.items.append(item)
        return item

    def define(
        self,
        name: str,
        value: float,
        unit: str = "",
        description: str = "",
        latex: Optional[str] = None,
    ) -> CalcItem:
        """Declare an input parameter."""
        self._register(name, float(value), unit, description, latex)
        item = CalcItem(
            kind="input",
            name=name,
            value=float(value),
            unit=unit,
            description=description,
            latex_lhs=self._latex_symbol(name),
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
    ) -> CalcItem:
        """Declare a derived quantity from a formula string.

        The formula may reference any previously defined variable and the
        functions sqrt/min/max/abs/sin/cos/tan/log/exp and the constant pi.
        """
        expr = self._parse(expression)
        value = self._evaluate(expr, expression)
        if latex is not None:
            self.latex_names[name] = latex
        # Display uses a non-evaluated parse so the rendered formula
        # stays faithful to how it was written (e.g. sqrt(28/t) is NOT
        # rewritten to 2*sqrt(7)*sqrt(1/t) the way sympy's auto-eval
        # would). Numbers still come from the evaluated ``expr`` above.
        display = self._parse_display(expression)
        symbolic = self._latex_expr(display)
        substituted = self._latex_substituted(display)
        self._register(name, value, unit, description, latex)
        item = CalcItem(
            kind="calc",
            name=name,
            value=value,
            unit=unit,
            description=description,
            expression=expression,
            latex_lhs=self._latex_symbol(name),
            latex_symbolic=symbolic,
            latex_substituted=substituted,
        )
        self.items.append(item)
        return item

    def check(self, expression: str, description: str = "") -> CalcItem:
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
        lhs_unit = self.units.get(lhs_str, "")
        rhs_unit = self.units.get(rhs_str, "")
        sym = (
            f"{self._latex_expr(self._parse_display(lhs_str))} = "
            f"{fmt_number(lhs)}"
            f"{self._unit_suffix(lhs_unit)} \\; {comp_latex[comparator]} \\; "
            f"{self._latex_expr(self._parse_display(rhs_str))} = "
            f"{fmt_number(rhs)}{self._unit_suffix(rhs_unit)}"
        )
        item = CalcItem(
            kind="check",
            name=expression,
            description=description,
            expression=expression,
            latex_symbolic=sym,
            passed=bool(passed),
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
        return dict(self.values)

    def all_passed(self) -> bool:
        return all(i.passed for i in self.checks())

    def input_names(self) -> list[str]:
        return [i.name for i in self.inputs()]

    def recompute(self, overrides: dict[str, float]) -> dict:
        """Re-run the SAME calculation with different input values.

        Reuses the stored formulas (no rebuild) — this powers parametric
        studies: run one tool over many load cases and tabulate. Returns
        ``{"values", "results", "checks":[(expr, passed)], "passed"}``.
        Unknown override names raise, so typos can't silently pass.
        """
        unknown = [k for k in overrides if k not in self.values]
        if unknown:
            raise CalcSheetError(
                f"recompute got unknown inputs {unknown}; "
                f"inputs are {self.input_names()}"
            )
        vals = {n: self.values[n] for n in self.input_names()}
        vals.update(overrides)
        results: dict[str, float] = {}
        for item in self.items:
            if item.kind == "calc":
                vals[item.name] = self._eval_with(item.expression, vals)
                results[item.name] = vals[item.name]
        checks: list[tuple[str, bool]] = []
        for item in self.checks():
            checks.append((item.expression, self._eval_check(item.expression, vals)))
        return {
            "values": vals,
            "results": results,
            "checks": checks,
            "passed": all(p for _, p in checks) if checks else None,
        }

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
                }
                for i in self.items
            ],
            "results": self.results(),
            "units": dict(self.units),
            "checks_passed": self.all_passed() if self.checks() else None,
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
        subs = {sp.Symbol(n): sp.Float(v) for n, v in self.values.items()}
        result = expr.xreplace(subs)
        result = sp.N(result)
        if not result.is_number:
            raise CalcSheetError(f"Expression {source!r} did not evaluate")
        return float(result)

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
        return sp.latex(
            expr, mul_symbol="dot", symbol_names=self._symbol_names(expr)
        )

    def _latex_substituted(self, expr: sp.Expr) -> str:
        subs = {}
        for name, value in self.values.items():
            text = fmt_number(value)
            if value < 0:
                text = f"({text})"
            subs[sp.Symbol(name)] = sp.Symbol(text)
        # evaluate(False) so injecting the numbers does not re-trigger
        # simplification and undo the faithful display structure.
        with sp.evaluate(False):
            replaced = expr.xreplace(subs)
            return sp.latex(replaced, mul_symbol="dot")

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
        )
        inputs = [v for v in self.variables if v.role == "input"]
        derived = [v for v in self.variables if v.role == "derived"]
        if inputs:
            sheet.section("Input Parameters")
            for var in inputs:
                try:
                    sheet.define(
                        var.name, var.value if var.value is not None else 0.0,
                        unit=var.unit, description=var.description,
                    )
                except CalcSheetError as exc:
                    self.warnings.append(f"Input '{var.name}' skipped: {exc}")
        if derived:
            sheet.section("Calculation")
            for var in derived:
                try:
                    sheet.calc(
                        var.name, var.expression, unit=var.unit,
                        description=var.description,
                    )
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
