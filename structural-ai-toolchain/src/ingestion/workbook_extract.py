"""Stage 1-2 of the AI Grinder: deterministic extraction + digest.

Reads a messy workbook into a compact, LLM-friendly intermediate
representation (IR) WITHOUT any interpretation. The goal is to feed an LLM
(or the heuristic interpreter) the *logic* of the sheet — formulas, labels,
named ranges, cached values — while keeping the token footprint small:

- only non-empty cells are kept
- cells are grouped into *regions* (connected non-empty blocks) so the
  digest is "tables", not a raw grid
- each cell becomes one compact record: sheet, coord, value, formula
- a nearby text cell is attached as the cell's ``label`` guess

``WorkbookDigest.to_markdown()`` / ``.to_json()`` produce the exact text
handed to the interpreter, with a token-budget cap that keeps every
formula (the logic) and samples value-only cells if the sheet is huge.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_to_tuple


@dataclass
class CellRecord:
    sheet: str
    coord: str
    row: int
    col: int
    is_formula: bool
    formula: str = ""       # the "=..." text (formula cells)
    value: object = None    # cached/literal value
    label: str = ""         # nearest text label guess

    @property
    def ref(self) -> str:
        return f"{self.sheet}!{self.coord}"


@dataclass
class Region:
    sheet: str
    min_row: int
    max_row: int
    min_col: int
    max_col: int
    cells: list[CellRecord] = field(default_factory=list)

    @property
    def bbox(self) -> str:
        return (f"{self.sheet}!{get_column_letter(self.min_col)}{self.min_row}"
                f":{get_column_letter(self.max_col)}{self.max_row}")


@dataclass
class WorkbookDigest:
    path: str
    sheet_names: list[str]
    named_ranges: dict[str, str]
    regions: list[Region]
    title_guess: str = ""

    # -------------------------------------------------------------- #
    def formula_cells(self) -> list[CellRecord]:
        return [c for r in self.regions for c in r.cells if c.is_formula]

    def all_cells(self) -> list[CellRecord]:
        return [c for r in self.regions for c in r.cells]

    def to_json(self, max_cells: int = 400) -> str:
        cells = self._budgeted_cells(max_cells)
        return json.dumps({
            "path": self.path,
            "sheets": self.sheet_names,
            "named_ranges": self.named_ranges,
            "cells": [
                {k: v for k, v in asdict(c).items()
                 if k not in ("row", "col")}
                for c in cells
            ],
        }, indent=2, default=str)

    def to_markdown(self, max_cells: int = 400) -> str:
        """Compact per-region markdown tables — the LLM-facing digest."""
        lines: list[str] = [f"# Workbook: {Path(self.path).name}",
                            f"Sheets: {', '.join(self.sheet_names)}"]
        if self.named_ranges:
            lines.append("Named ranges: " + ", ".join(
                f"{k} -> {v}" for k, v in self.named_ranges.items()))
        budget = self._budgeted_cells(max_cells)
        keep = {c.ref for c in budget}
        for region in self.regions:
            rc = [c for c in region.cells if c.ref in keep]
            if not rc:
                continue
            lines.append(f"\n## Region {region.bbox}")
            lines.append("| cell | label | value | formula |")
            lines.append("|---|---|---|---|")
            for c in rc:
                val = "" if c.value is None else str(c.value)
                lines.append(
                    f"| {c.coord} | {c.label} | {val} | {c.formula} |")
        return "\n".join(lines)

    def _budgeted_cells(self, max_cells: int) -> list[CellRecord]:
        """Always keep formula cells (the logic); sample value-only cells."""
        cells = self.all_cells()
        if len(cells) <= max_cells:
            return cells
        formulas = [c for c in cells if c.is_formula]
        values = [c for c in cells if not c.is_formula]
        room = max(max_cells - len(formulas), 0)
        step = max(len(values) // room, 1) if room else len(values) + 1
        sampled = values[::step][:room]
        return formulas + sampled


# ------------------------------------------------------------------ #
# Extraction
# ------------------------------------------------------------------ #
_TEXTY = (str,)


def _is_text_label(value) -> bool:
    return isinstance(value, str) and value.strip() != "" and \
        not value.startswith("=")


def extract_workbook(path: str | Path) -> WorkbookDigest:
    from openpyxl import load_workbook

    path = Path(path)
    # data_only=False keeps formulas; a second read gets cached values.
    wb_f = load_workbook(path, data_only=False)
    try:
        wb_v = load_workbook(path, data_only=True)
    except Exception:
        wb_v = None

    named = {}
    try:
        for name, defn in (wb_f.defined_names or {}).items():
            named[name] = str(getattr(defn, "value", defn))
    except Exception:
        pass

    regions: list[Region] = []
    for ws in wb_f.worksheets:
        vs = wb_v[ws.title] if wb_v is not None and ws.title in wb_v.sheetnames \
            else None
        records = _cells_of_sheet(ws, vs)
        _attach_labels(records)
        regions.extend(_regions_of(ws.title, records))

    title = _guess_title(regions, wb_f.sheetnames)
    return WorkbookDigest(
        path=str(path),
        sheet_names=wb_f.sheetnames,
        named_ranges=named,
        regions=regions,
        title_guess=title,
    )


def _cells_of_sheet(ws, vs) -> list[CellRecord]:
    records: list[CellRecord] = []
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if v is None or (isinstance(v, str) and v.strip() == ""):
                continue
            is_formula = isinstance(v, str) and v.startswith("=")
            cached = None
            if vs is not None:
                try:
                    cached = vs[cell.coordinate].value
                except Exception:
                    cached = None
            r, c = coordinate_to_tuple(cell.coordinate)
            records.append(CellRecord(
                sheet=ws.title, coord=cell.coordinate, row=r, col=c,
                is_formula=is_formula,
                formula=str(v) if is_formula else "",
                value=cached if is_formula else v,
            ))
    return records


def _attach_labels(records: list[CellRecord]) -> None:
    """Attach the nearest text cell (same row to the left, else above)."""
    by_pos = {(c.row, c.col): c for c in records}
    for c in records:
        if c.is_formula or not _is_number(c.value):
            continue
        # scan left on the same row for a text label
        label = ""
        for dc in range(1, 6):
            left = by_pos.get((c.row, c.col - dc))
            if left and _is_text_label(left.value):
                label = left.value.strip()
                break
        if not label:
            up = by_pos.get((c.row - 1, c.col))
            if up and _is_text_label(up.value):
                label = up.value.strip()
        c.label = label
    # formula cells too
    for c in records:
        if not c.is_formula:
            continue
        for dc in range(1, 6):
            left = by_pos.get((c.row, c.col - dc))
            if left and _is_text_label(left.value):
                c.label = left.value.strip()
                break


def _regions_of(sheet: str, records: list[CellRecord]) -> list[Region]:
    """Group cells into connected blocks (row/col gap <= 1)."""
    if not records:
        return []
    remaining = {(c.row, c.col): c for c in records}
    regions: list[Region] = []
    while remaining:
        seed = next(iter(remaining))
        stack = [seed]
        cluster: list[CellRecord] = []
        while stack:
            pos = stack.pop()
            cell = remaining.pop(pos, None)
            if cell is None:
                continue
            cluster.append(cell)
            r, cc = pos
            for dr in (-1, 0, 1):
                for dcc in (-1, 0, 1):
                    npos = (r + dr, cc + dcc)
                    if npos in remaining:
                        stack.append(npos)
        rows = [c.row for c in cluster]
        cols = [c.col for c in cluster]
        regions.append(Region(
            sheet=sheet, min_row=min(rows), max_row=max(rows),
            min_col=min(cols), max_col=max(cols),
            cells=sorted(cluster, key=lambda c: (c.row, c.col)),
        ))
    return sorted(regions, key=lambda r: (r.min_row, r.min_col))


def _guess_title(regions: list[Region], sheet_order: list[str]) -> str:
    """The title is usually the longest text near the top of the FIRST sheet
    (a heading), so prefer sheet order + length over raw grid position."""
    rank = {name: i for i, name in enumerate(sheet_order)}
    candidates = [
        c for region in regions for c in region.cells
        if _is_text_label(c.value) and len(str(c.value).strip()) > 8
        and c.row <= 6
    ]
    if not candidates:
        return ""
    # first sheet first, then longest text, then topmost/leftmost
    best = min(candidates, key=lambda c: (
        rank.get(c.sheet, 99), -len(str(c.value).strip()), c.row, c.col))
    return str(best.value).strip()


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
