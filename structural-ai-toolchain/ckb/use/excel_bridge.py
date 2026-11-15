"""The Excel bridge: a calculation object as a live spreadsheet, and back.

Out: ``export_calculator`` writes a workbook in which every step is a native Excel
formula written with named ranges (``=0.18/gamma_C``), so the formula bar reads like
the equation.  No macros, no add-in.  The engineer changes the yellow cells.

Back: the sheet is laid out as "description | symbol | value | unit", which is what
the Excel converter reads, so an edited calculator is just another source
(``python -m ckb check``).  A hidden sheet records which object and version the file
was generated from; ``python -m ckb verify`` uses it to prove the file still carries
the knowledge base's logic.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import expr as X
from .. import units as U
from ..kb.objects import KnowledgeBase
from .calc import run, starting_values
from .style import Style

META_SHEET = "_ckb"
SHEET = "Calculation"
_CELL_LIKE = re.compile(r"^([A-Za-z]{1,3}\d+|[rR]\d*[cC]\d*|[rRcC])$")


def excel_names(kb: KnowledgeBase, ids: list[str]) -> dict[str, str]:
    """A valid, unique Excel name for every quantity (``f_ck``, ``gamma_C``, ``V_Rd_c``)."""
    out, used = {}, set()
    for sid in ids:
        base = re.sub(r"[^A-Za-z0-9_.]", "_", kb.var(sid) or sid)
        if not re.match(r"[A-Za-z_]", base) or _CELL_LIKE.match(base):
            base = "q_" + base
        name, n = base, 2
        while name.lower() in used:
            name, n = f"{base}_{n}", n + 1
        used.add(name.lower())
        out[sid] = name
    return out


def layout(kb: KnowledgeBase, target: str, given=()) -> tuple[list, list, dict]:
    steps, inputs = kb.plan(target, given)
    cells: dict[str, str] = {}
    row = 6
    for p in inputs + list(kb.objects[target].fixed):
        cells[p] = f"C{row}"
        row += 1
    row += 2
    for s in steps:
        cells[s] = f"C{row}"
        row += 1
    return steps, inputs, cells


def formula_for(kb: KnowledgeBase, oid: str, names: dict, style: Style) -> str:
    """Excel formula of one step; named cells hold values in their display units."""
    def ref(sym: str) -> str:
        f = U.parse_unit(style.unit(kb, sym)).factor
        return names[sym] if abs(f - 1.0) < 1e-12 else f"({names[sym]}*{f!r})"

    body = X.to_excel(kb.objects[oid].tree, ref)
    f_out = U.parse_unit(style.unit(kb, oid)).factor
    return f"={body}" if abs(f_out - 1.0) < 1e-12 else f"=({body})/{f_out!r}"


def export_calculator(kb: KnowledgeBase, target: str, path: Path, values: dict | None = None,
                      given=(), style: Style | None = None, refs: str = "names") -> Path:
    """Excel calculator.  ``refs="names"`` writes =MIN(A_sl/(b_w*d),0.02); ``refs="cells"`` writes
    =MIN(C8/(C9*C7),0.02).  The cells are named in both cases."""
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.workbook.defined_name import DefinedName

    style = style or Style()
    obj = kb.objects[target]
    steps, inputs, cells = layout(kb, target, given)
    if values is None:
        values, _ = starting_values(kb, target, given)
    names = excel_names(kb, list(cells))
    refmap = names if refs == "names" else {sid: cells[sid] for sid in cells}
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    bold, grey = Font(bold=True), Font(color="5B6966")
    head_fill = PatternFill("solid", fgColor="E6EBE9")
    in_fill = PatternFill("solid", fgColor="FFF2B3")
    thin = Side(style="thin", color="9AA5A2")
    ws["A1"], ws["A1"].font = f"{obj.text}   {obj.name}", Font(bold=True, size=13)
    ws["A2"], ws["A2"].font = obj.reference_text, grey
    ws["A3"], ws["A3"].font = "Yellow cells are inputs. Every other value is an Excel formula; the cell names match the symbols.", grey

    def header(row: int, title: str, cols=("Description", "Symbol", "Value", "Unit", "Reference")):
        ws[f"A{row}"] = title
        for col, text in zip("ABCDEF", (title,) + tuple(cols[1:])):
            c = ws[f"{col}{row}"]
            c.value, c.font, c.fill, c.border = text, bold, head_fill, Border(bottom=thin)

    def put(sid: str, row: int, value, is_input: bool, note: str = ""):
        item = kb.item(sid)
        unit = style.unit(kb, sid)
        ws[f"A{row}"] = item.name if item else sid
        ws[f"B{row}"] = kb.name(sid)
        c = ws[f"C{row}"]
        c.value = value
        typical = style.show(kb, sid, getattr(item, "start", None)) if sid in kb.quantities else None
        c.number_format = style.excel_format(typical if isinstance(typical, (int, float)) else
                                             (value if isinstance(value, (int, float)) else None))
        if is_input:
            c.fill = in_fill
        ws[f"D{row}"] = "" if unit == "-" else unit
        if sid in kb.objects:
            ws[f"E{row}"] = kb.objects[sid].reference_text.replace(f"{kb.objects[sid].code} ", "")
        elif item is not None and getattr(item, "clause", ""):
            ws[f"E{row}"] = item.clause if item.clause.lower().startswith(("table", "fig")) else f"cl. {item.clause}"
        if note:
            ws[f"F{row}"], ws[f"F{row}"].font = note, grey
        wb.defined_names[names[sid]] = DefinedName(names[sid], attr_text=f"'{SHEET}'!$C${row}")

    header(5, "Input")
    for p in inputs:
        v = values.get(p)
        put(p, int(cells[p][1:]), style.show(kb, p, v) if isinstance(v, (int, float)) else v, True,
            "entered directly" if p in given else "")
    for k, v in obj.fixed.items():
        put(k, int(cells[k][1:]), style.show(kb, k, v), False, f"fixed by {obj.code}")
    first = int(cells[steps[0]][1:])
    header(first - 1, "Calculation", ("Calculation", "Symbol", "Value", "Unit", "Reference", "Equation"))
    for sid in steps:
        r = int(cells[sid][1:])
        o = kb.objects[sid]
        put(sid, r, None, False)
        ws[f"C{r}"] = formula_for(kb, sid, refmap, style)
        ws[f"C{r}"].number_format = style.excel_format(_typical(kb, sid, style))
        ws[f"F{r}"], ws[f"F{r}"].font = f"{o.text} = {X.to_text(o.tree, kb.name)}", grey
        if sid == target:
            for col in "ABCD":
                ws[f"{col}{r}"].font = bold
    last = int(cells[target][1:])
    row = last + 2
    if obj.check and kb.item(obj.check) is not None:
        chk = obj.check
        header(row, "Verification")
        item = kb.item(chk)
        ws[f"A{row + 1}"], ws[f"B{row + 1}"] = item.name, kb.name(chk)
        ws[f"C{row + 1}"].fill = in_fill
        ws[f"C{row + 1}"].number_format = style.excel_format(_typical(kb, target, style))
        ws[f"D{row + 1}"] = style.unit(kb, chk)
        action = obj.sense == "resistance"
        a, b = (f"C{row + 1}", f"C{last}") if action else (f"C{last}", f"C{row + 1}")
        f_a = U.parse_unit(style.unit(kb, chk if action else target)).factor
        f_b = U.parse_unit(style.unit(kb, target if action else chk)).factor
        ratio = f"({a}*{f_a!r})/({b}*{f_b!r})" if abs(f_a - f_b) > 1e-12 else f"{a}/{b}"
        ws[f"A{row + 2}"] = "Utilisation"
        ws[f"B{row + 2}"] = f"{kb.name(chk)} / {obj.text}" if action else f"{obj.text} / {kb.name(chk)}"
        ws[f"C{row + 2}"] = f'=IF(OR({a}="",{b}=""),"",{ratio})'
        ws[f"C{row + 2}"].number_format = "0.00"
        ws[f"A{row + 3}"] = "Verified"
        ws[f"C{row + 3}"] = f'=IF(C{row + 2}="","",IF(C{row + 2}<=1,"OK","NOT OK"))'
        ws[f"C{row + 3}"].font = bold
        ws.conditional_formatting.add(f"C{row + 2}", CellIsRule(operator="greaterThan", formula=["1"],
                                                               fill=PatternFill("solid", bgColor="F6C7C3")))
        ws.conditional_formatting.add(f"C{row + 2}", CellIsRule(operator="between", formula=["0.0000001", "1"],
                                                               fill=PatternFill("solid", bgColor="CDEBD9")))
        row += 5
    checks = [c for sid in steps for c in kb.objects[sid].checks]
    if checks:
        header(row, "Conditions", ("Conditions", "Condition", "Met", "", "Reference"))
        for i, chk in enumerate(checks, 1):
            r = row + i
            tree = X.parse(chk["when"])
            ws[f"A{r}"] = chk.get("text", chk["when"])
            ws[f"B{r}"] = X.to_text(tree, kb.name)
            if all(s in refmap for s in X.symbols(tree)):
                cond = X.to_excel(tree, lambda s: refmap[s] if abs(U.parse_unit(style.unit(kb, s)).factor - 1) < 1e-12
                                  else f"({refmap[s]}*{U.parse_unit(style.unit(kb, s)).factor!r})")
                ws[f"C{r}"] = f'=IF({cond},"yes","NO")'
            else:
                ws[f"C{r}"] = "check"
            ws[f"E{r}"] = f"cl. {chk.get('clause', '')}" if chk.get("clause") else ""
        row += len(checks) + 2
    limits = [f"{kb.objects[sid].text}: {t}" for sid in steps for t in kb.objects[sid].limitations]
    if limits:
        ws[f"A{row}"], ws[f"A{row}"].font = "Scope and limitations", bold
        for i, text in enumerate(dict.fromkeys(limits), 1):
            ws[f"A{row + i}"] = text
            ws[f"A{row + i}"].alignment = Alignment(wrap_text=False)
    for col, width in zip("ABCDEF", (50, 16, 14, 9, 24, 80)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A5"

    meta = wb.create_sheet(META_SHEET)
    meta.sheet_state = "hidden"
    record = {"object": target, "version": obj.version, "code": obj.code,
              "generated": _dt.date.today().isoformat(), "given": list(given), "cells": cells,
              "names": names, "refs": refs, "style": style.to_dict(),
              "formulas": {sid: formula_for(kb, sid, refmap, style) for sid in steps}}
    meta["A1"], meta["B1"] = "ckb", json.dumps(record)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _typical(kb: KnowledgeBase, sid: str, style: Style):
    """A representative value of an object (display unit), for choosing a number format."""
    try:
        values = kb.defaults(sid)
        v, _ = kb.evaluate(sid, values)
        return style.show(kb, sid, v)
    except Exception:                                            # noqa: BLE001
        return None


def read_calculator(path: Path) -> dict | None:
    """Read back a generated calculator: its object, the inputs now in it, and which
    formulas were edited.  Returns None for a workbook we did not generate."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=False)
    if META_SHEET not in wb.sheetnames:
        return None
    try:
        record = json.loads(wb[META_SHEET]["B1"].value)
    except (TypeError, ValueError):
        return None
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
    cells = record["cells"]
    changed = {sid: ws[cells[sid]].value for sid, f in record["formulas"].items() if ws[cells[sid]].value != f}
    inputs = {sid: ws[c].value for sid, c in cells.items() if sid not in record["formulas"]}
    return {"object": record["object"], "version": record["version"], "inputs": inputs,
            "changed_formulas": changed, "given": record.get("given", []), "style": record.get("style", {})}


def recalculate(path: Path) -> dict | None:
    """Let LibreOffice calculate the workbook; {cell: value} of the calculation sheet, or None."""
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
        ws = load_workbook(out, data_only=True)[SHEET]
        return {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}


def verify(kb: KnowledgeBase, path: Path) -> dict:
    """Does this workbook carry the knowledge base's logic?  Formulas, version and numbers."""
    rec = read_calculator(path)
    if rec is None:
        return {"ok": False, "reason": "not a calculator generated from the knowledge base"}
    target = rec["object"]
    if target not in kb.objects:
        return {"ok": False, "reason": f"object {target} is not in this knowledge base"}
    style = Style.load(rec.get("style") or {})
    obj = kb.objects[target]
    out = {"object": target, "version_in_file": rec["version"], "version_now": obj.version,
           "same_version": rec["version"] == obj.version, "edited": sorted(rec["changed_formulas"])}
    values = {}
    for sid, v in rec["inputs"].items():
        if isinstance(v, (int, float)) and sid not in obj.fixed:
            values[sid] = U.to_canonical(v, style.unit(kb, sid))
    got = recalculate(path)
    if got is None:
        out["numbers"] = "not compared: LibreOffice is not installed"
        out["ok"] = out["same_version"] and not out["edited"]
        return out
    _, _, cells = layout(kb, target, rec.get("given", []))
    res = run(kb, target, values, rec.get("given", []), style=style)
    rows = []
    for ln in res.steps:
        xl = got.get(cells[ln.id])
        ok = isinstance(xl, (int, float)) and isinstance(ln.shown, (int, float)) and \
            abs(xl - ln.shown) <= 1e-9 * max(1.0, abs(ln.shown))
        rows.append({"id": ln.id, "excel": xl, "knowledge_base": ln.shown, "agree": bool(ok) or xl == ln.shown})
    out["rows"] = rows
    out["ok"] = out["same_version"] and not out["edited"] and all(r["agree"] for r in rows)
    return out
