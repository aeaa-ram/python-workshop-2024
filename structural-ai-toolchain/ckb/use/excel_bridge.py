"""The Excel bridge: a calculation object as a live spreadsheet, and back.

Out: ``export_calculator`` writes a workbook in which every step of the
calculation is a native Excel formula - no macros, no add-in, nothing to
install.  The engineer changes the yellow cells and Excel recalculates.

Back: the workbook is laid out as "description | symbol | value | unit", which
is exactly what the Excel converter reads.  A calculator that comes back with
changed formulas is therefore just another source: its logic is distilled and
compared with the object (``python -m ckb check file.xlsx``).  A hidden sheet
records which object and version the file was generated from.
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import expr as X
from .. import units as U
from ..kb.objects import KnowledgeBase
from .calc import run, starting_values

META_SHEET = "_ckb"


def _layout(kb: KnowledgeBase, target: str, given=()) -> tuple[list, list, dict]:
    steps, inputs = kb.plan(target, given)
    cells: dict[str, str] = {}
    row = 7
    for p in inputs:
        cells[p] = f"C{row}"
        row += 1
    row += 2
    for s in steps:
        cells[s] = f"C{row}"
        row += 1
    return steps, inputs, cells


def formula_for(kb: KnowledgeBase, oid: str, cells: dict) -> str:
    """Excel formula of one step; cells hold values in their display units."""
    def ref(sym: str) -> str:
        f = U.parse_unit(kb.unit(sym)).factor
        cell = "$" + cells[sym][0] + "$" + cells[sym][1:]
        return cell if abs(f - 1.0) < 1e-12 else f"({cell}*{f!r})"

    body = X.to_excel(kb.objects[oid].tree, ref)
    f_out = U.parse_unit(kb.unit(oid)).factor
    return f"={body}" if abs(f_out - 1.0) < 1e-12 else f"=({body})/{f_out!r}"


def export_calculator(kb: KnowledgeBase, target: str, path: Path, values: dict | None = None,
                      given=()) -> Path:
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    obj = kb.objects[target]
    steps, inputs, cells = _layout(kb, target, given)
    if values is None:
        values, _ = starting_values(kb, target, given)
    wb = Workbook()
    ws = wb.active
    ws.title = "Calculation"
    bold, grey = Font(bold=True), Font(color="666666")
    head_fill = PatternFill("solid", fgColor="E6EBE9")
    in_fill = PatternFill("solid", fgColor="FFF2B3")
    thin = Side(style="thin", color="999999")
    ws["A1"], ws["A1"].font = f"{obj.text} - {obj.name}", Font(bold=True, size=13)
    ws["A2"], ws["A2"].font = f"{obj.reference_text} - {' > '.join(obj.topic_path)}", grey
    s = obj.support
    ws["A3"] = (f"Status: {obj.status} - {s.get('formula_instances', 0)} formulas in {s.get('sources', 0)} independent "
                f"source(s); {obj.benchmarks.get('agree', 0)} of {obj.benchmarks.get('total', 0)} source values reproduced"
                + (f"; reference: {obj.reference['status']} with {obj.reference['library']}" if obj.reference else ""))
    ws["A3"].font = grey
    ws["A4"] = "Change the yellow cells. Every other value is an Excel formula."
    ws["A4"].font = grey

    def header(row: int, title: str):
        for col, text in zip("ABCDEF", (title, "Symbol", "Value", "Unit", "Reference", "Formula")):
            c = ws[f"{col}{row}"]
            c.value, c.font, c.fill = text, bold, head_fill
            c.border = Border(bottom=thin)

    header(6, "Input")
    for p in inputs:
        r = int(cells[p][1:])
        item = kb.objects.get(p) or kb.quantities.get(p)
        ws[f"A{r}"], ws[f"B{r}"] = (item.name if item else p), kb.name(p)
        v = values.get(p)
        ws[f"C{r}"] = kb.to_display(p, v) if isinstance(v, (int, float)) else v
        ws[f"C{r}"].fill = in_fill
        ws[f"D{r}"] = "" if kb.unit(p) == "-" else kb.unit(p)
        clause = getattr(item, "clause", "") if item else ""
        ws[f"E{r}"] = (f"cl. {clause}" if clause and not clause.lower().startswith("table") else clause)
        if p in given:
            ws[f"F{r}"] = "entered directly (not calculated)"
    first_step = int(cells[steps[0]][1:])
    header(first_step - 1, "Calculation")
    for sid in steps:
        r = int(cells[sid][1:])
        o = kb.objects[sid]
        ws[f"A{r}"], ws[f"B{r}"] = o.name, o.text
        ws[f"C{r}"] = formula_for(kb, sid, cells)
        ws[f"D{r}"] = "" if o.unit == "-" else o.unit
        ws[f"E{r}"] = o.reference_text.replace(kb.meta.get("code", "") + " ", "")
        ws[f"F{r}"] = f"{o.text} = {X.to_text(o.tree, kb.name)}   ({o.status})"
        ws[f"F{r}"].font = grey
        if sid == target:
            for col in "ABCD":
                ws[f"{col}{r}"].font = bold
    last = int(cells[target][1:])
    row = last + 2
    if obj.check and (obj.check in kb.quantities or obj.check in kb.objects):
        chk = obj.check
        header(row, "Check")
        ws[f"A{row + 1}"], ws[f"B{row + 1}"] = (kb.quantities[chk].name if chk in kb.quantities else chk), kb.name(chk)
        ws[f"C{row + 1}"].fill = in_fill
        ws[f"D{row + 1}"] = "" if kb.unit(chk) == "-" else kb.unit(chk)
        action = chk.endswith("_Ed")
        ws[f"A{row + 2}"], ws[f"B{row + 2}"] = "Utilisation", (f"{kb.name(chk)} / {obj.text}" if action else f"{obj.text} / {kb.name(chk)}")
        a, b = (f"C{row + 1}", f"C{last}") if action else (f"C{last}", f"C{row + 1}")
        ws[f"C{row + 2}"] = f'=IF(OR({a}="",{b}=""),"",{a}/{b})'
        ws[f"A{row + 3}"] = "Verified"
        ws[f"C{row + 3}"] = f'=IF(C{row + 2}="","",IF(C{row + 2}<=1,"OK","NOT OK"))'
        ws.conditional_formatting.add(f"C{row + 2}", CellIsRule(operator="greaterThan", formula=["1"],
                                                               fill=PatternFill("solid", bgColor="F6C7C3")))
        ws.conditional_formatting.add(f"C{row + 2}", CellIsRule(operator="between", formula=["0.0000001", "1"],
                                                               fill=PatternFill("solid", bgColor="CDEBD9")))
        row += 5
    notes = [f"{kb.objects[sid].text}: {w}" for sid in steps for w in kb.objects[sid].warnings] + \
            [f"{kb.objects[sid].text}: {n}" for sid in steps for n in kb.objects[sid].notes]
    if notes:
        ws[f"A{row}"], ws[f"A{row}"].font = "Notes and limitations", bold
        for i, n in enumerate(dict.fromkeys(notes), 1):
            ws[f"A{row + i}"] = n
            ws[f"A{row + i}"].alignment = Alignment(wrap_text=False)
    for col, width in zip("ABCDEF", (52, 14, 16, 9, 30, 90)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A6"

    meta = wb.create_sheet(META_SHEET)
    meta.sheet_state = "hidden"
    record = {"object": target, "version": obj.version, "code": kb.meta.get("code", ""),
              "branch": kb.meta.get("branch", ""), "generated": _dt.date.today().isoformat(),
              "given": list(given), "cells": cells,
              "formulas": {sid: formula_for(kb, sid, cells) for sid in steps}}
    meta["A1"], meta["B1"] = "ckb", json.dumps(record)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def read_calculator(path: Path) -> dict | None:
    """Read back a generated calculator: its object, the inputs now in it, and
    which formulas were edited.  Returns None for a workbook we did not generate."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=False)
    if META_SHEET not in wb.sheetnames:
        return None
    try:
        record = json.loads(wb[META_SHEET]["B1"].value)
    except (TypeError, ValueError):
        return None
    ws = wb["Calculation"] if "Calculation" in wb.sheetnames else wb.worksheets[0]
    cells = record["cells"]
    changed = {sid: ws[cells[sid]].value for sid, f in record["formulas"].items() if ws[cells[sid]].value != f}
    inputs = {sid: ws[c].value for sid, c in cells.items() if sid not in record["formulas"]}
    return {"object": record["object"], "version": record["version"], "inputs": inputs,
            "changed_formulas": changed, "given": record.get("given", [])}


def recalculate(path: Path) -> dict | None:
    """Let LibreOffice calculate the workbook and return {cell: value} of the
    'Calculation' sheet.  None when LibreOffice is not installed."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    from openpyxl import load_workbook
    with tempfile.TemporaryDirectory(prefix="ckb_xl_") as tmp:
        try:
            subprocess.run([soffice, "--headless", f"-env:UserInstallation=file://{tmp}/profile", "--convert-to",
                            "xlsx:Calc MS Excel 2007 XML", "--outdir", tmp, str(Path(path).resolve())],
                           capture_output=True, timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        out = Path(tmp) / Path(path).name
        if not out.exists():
            return None
        ws = load_workbook(out, data_only=True)["Calculation"]
        return {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}


def verify(kb: KnowledgeBase, target: str, path: Path, values: dict, given=()) -> dict | None:
    """Compare what Excel (LibreOffice) calculates with the knowledge base."""
    got = recalculate(path)
    if got is None:
        return None
    _, _, cells = _layout(kb, target, given)
    res = run(kb, target, values, given)
    rows = []
    for ln in res.steps:
        xl = got.get(cells[ln.id])
        ok = isinstance(xl, (int, float)) and isinstance(ln.shown, (int, float)) and \
            abs(xl - ln.shown) <= 1e-9 * max(1.0, abs(ln.shown))
        rows.append({"id": ln.id, "excel": xl, "knowledge_base": ln.shown, "agree": bool(ok) or xl == ln.shown})
    return {"agree": all(r["agree"] for r in rows), "rows": rows}
