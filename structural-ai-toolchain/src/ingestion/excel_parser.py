"""Excel parser for The Grinder.

Reads structured calculation workbooks (.xlsx/.xlsm) that follow the
ingestion convention (see docs/ARCHITECTURE.md):

    <Title cell A1>
    INPUTS
    Name | Value | Unit | Description
    ...
    CALCULATIONS
    Name | Formula (real Excel formula) | Unit | Description
    ...
    CHECKS
    Expression (e.g. "w_k <= w_max") | Description

The parser reads the *formulas*, not Excel's cached values: cell
references are mapped back to the variable names declared in the same
sheet, and Excel functions/operators are translated to our expression
syntax. The toolchain then re-computes everything — which doubles as an
independent verification of the legacy workbook.

Free-form spreadsheets that don't follow the convention are parsed
best-effort and produce warnings instead of silent garbage.
"""

from __future__ import annotations

import re
from pathlib import Path

from openpyxl import load_workbook

from src.ingestion.base import BaseParser
from src.models.calculation import ParsedTool, ParsedVariable

_CELL_REF = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")
_FUNCTION_MAP = {
    "SQRT": "sqrt",
    "MIN": "min",
    "MAX": "max",
    "ABS": "abs",
    "POWER": "pow",  # POWER(a,b) handled by ** rewrite below
    "LN": "log",
    "EXP": "exp",
    "PI()": "pi",
}
_MARKERS = ("INPUTS", "CALCULATIONS", "CHECKS")


class ExcelParser(BaseParser):
    extensions = (".xlsx", ".xlsm")

    def parse(self, path: Path) -> ParsedTool:
        path = Path(path)
        wb = load_workbook(path, data_only=False)
        ws = wb.worksheets[0]
        tool = ParsedTool(
            title=str(ws["A1"].value or path.stem),
            source_path=str(path),
            source_format=path.suffix.lstrip("."),
        )
        if ws["A2"].value:
            tool.description = str(ws["A2"].value)

        cell_to_name: dict[str, str] = {}
        mode: str | None = None
        for row in ws.iter_rows(min_row=1):
            first = row[0].value
            if isinstance(first, str) and first.strip().upper() in _MARKERS:
                mode = first.strip().upper()
                continue
            if first is None or mode is None:
                continue
            label = str(first).strip()
            if label.lower() == "name" or label.lower() == "expression":
                continue  # header row
            if mode == "INPUTS":
                self._parse_input(tool, row, cell_to_name)
            elif mode == "CALCULATIONS":
                self._parse_calc(tool, row, cell_to_name, ws.title)
            elif mode == "CHECKS":
                self._parse_check(tool, row)
        if not tool.variables:
            tool.warnings.append(
                f"No INPUTS/CALCULATIONS blocks found in {path.name}; the "
                "workbook does not follow the ingestion convention and "
                "needs manual conversion."
            )
        return tool

    # ------------------------------------------------------------------ #
    def _parse_input(self, tool, row, cell_to_name) -> None:
        name = str(row[0].value).strip()
        value_cell = row[1]
        try:
            value = float(value_cell.value)
        except (TypeError, ValueError):
            tool.warnings.append(
                f"Input '{name}': non-numeric value "
                f"{value_cell.value!r} skipped."
            )
            return
        cell_to_name[value_cell.coordinate] = name
        tool.variables.append(
            ParsedVariable(
                name=name,
                value=value,
                unit=str(row[2].value or "") if len(row) > 2 else "",
                description=str(row[3].value or "") if len(row) > 3 else "",
                role="input",
            )
        )

    def _parse_calc(self, tool, row, cell_to_name, sheet_title) -> None:
        name = str(row[0].value).strip()
        formula_cell = row[1]
        raw = formula_cell.value
        if raw is None:
            return
        raw = str(raw)
        if not raw.startswith("="):
            tool.warnings.append(
                f"Calculation '{name}': cell {formula_cell.coordinate} holds "
                f"a literal, not a formula; treated as input."
            )
            try:
                value = float(raw)
            except ValueError:
                return
            cell_to_name[formula_cell.coordinate] = name
            tool.variables.append(
                ParsedVariable(name=name, value=value, role="input")
            )
            return
        expression, unresolved = self.translate_formula(
            raw[1:], cell_to_name
        )
        if unresolved:
            tool.warnings.append(
                f"Calculation '{name}': unresolved cell references "
                f"{unresolved} — formula kept but will not evaluate."
            )
        cell_to_name[formula_cell.coordinate] = name
        tool.variables.append(
            ParsedVariable(
                name=name,
                unit=str(row[2].value or "") if len(row) > 2 else "",
                description=str(row[3].value or "") if len(row) > 3 else "",
                role="derived",
                expression=expression,
            )
        )

    def _parse_check(self, tool, row) -> None:
        tool.checks.append(str(row[0].value).strip())

    @staticmethod
    def translate_formula(
        formula: str, cell_to_name: dict[str, str]
    ) -> tuple[str, list[str]]:
        """Excel formula body -> toolchain expression string."""
        unresolved: list[str] = []

        def repl(match: re.Match) -> str:
            coord = f"{match.group(1)}{match.group(2)}"
            if coord in cell_to_name:
                return cell_to_name[coord]
            unresolved.append(coord)
            return coord

        out = _CELL_REF.sub(repl, formula)
        out = out.replace("^", "**")
        for excel_fn, py_fn in _FUNCTION_MAP.items():
            out = re.sub(
                rf"\b{re.escape(excel_fn)}\b", py_fn, out,
                flags=re.IGNORECASE,
            )
        # POWER(a, b) -> (a)**(b)
        out = re.sub(
            r"\bpow\(([^,]+),([^)]+)\)", r"(\1)**(\2)", out
        )
        return out.strip(), unresolved


class CsvParser(BaseParser):
    """CSV variant of the ingestion convention (no cell references).

    Rows: block markers INPUTS/CALCULATIONS/CHECKS, then
    ``name,value_or_expression,unit,description``. Because CSV has no
    formula cells, CALCULATIONS rows hold expression strings that
    reference variable names directly, e.g. ``A,b*h,mm^2,Area``.
    """

    extensions = (".csv",)

    def parse(self, path: Path) -> ParsedTool:
        import csv

        path = Path(path)
        tool = ParsedTool(
            title=path.stem.replace("_", " ").title(),
            source_path=str(path),
            source_format="csv",
        )
        mode: str | None = None
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.reader(fh):
                if not row or not row[0].strip():
                    continue
                first = row[0].strip()
                if first.upper() in _MARKERS:
                    mode = first.upper()
                    continue
                if first.lower() in ("name", "expression") or mode is None:
                    continue
                unit = row[2].strip() if len(row) > 2 else ""
                desc = row[3].strip() if len(row) > 3 else ""
                if mode == "INPUTS":
                    try:
                        value = float(row[1])
                    except (IndexError, ValueError):
                        tool.warnings.append(
                            f"Input '{first}': missing/non-numeric value."
                        )
                        continue
                    tool.variables.append(
                        ParsedVariable(
                            name=first, value=value, unit=unit,
                            description=desc, role="input",
                        )
                    )
                elif mode == "CALCULATIONS":
                    if len(row) < 2 or not row[1].strip():
                        continue
                    tool.variables.append(
                        ParsedVariable(
                            name=first, unit=unit, description=desc,
                            role="derived", expression=row[1].strip(),
                        )
                    )
                elif mode == "CHECKS":
                    tool.checks.append(first)
        return tool
