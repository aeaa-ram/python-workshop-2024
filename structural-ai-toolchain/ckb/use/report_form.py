"""A report template as an Excel form, for people who do not want to edit YAML.

    python -m ckb report-template V_Rd_c -o shear_report.xlsx     # the form, filled with a start
    python -m ckb report --template shear_report.xlsx --pdf --docx

Four sheets, with drop-down lists where there is a choice:

    Report    title block, number style, values that apply to every case, display units
    Blocks    one row per block of the report, in order: heading, text, calc, table, chart, page break
    Cases     one row per case: the inputs, and the value to check against
    Remarks   a note beside any line of a calculation

The form is read into the same template the YAML holds, so both stay interchangeable.
"""
from __future__ import annotations

from pathlib import Path

from .. import units as U
from ..kb.objects import KnowledgeBase
from .calc import starting_values

YES = ("yes", "no")
BLOCK_COLS = ["Block", "Object", "Text", "Case", "Equation", "Substituted values", "Result", "Steps",
              "Table columns", "Sort by", "Chart: vary", "From", "To", "Also show", "Scope and limitations"]
FIELDS = [("Title", "title"), ("Project", "project"), ("Calc. no.", "number"), ("Made by", "made_by"),
          ("Checked by", "checked_by"), ("Approved by", "approved_by")]


def write_form(kb: KnowledgeBase, target: str, path: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    obj = kb.objects[target]
    steps, inputs = kb.plan(target)
    values, _ = starting_values(kb, target)
    bold, grey = Font(bold=True), Font(color="5B6966", italic=True)
    fill = PatternFill("solid", fgColor="FFF2B3")
    head = PatternFill("solid", fgColor="E6EBE9")
    wb = Workbook()

    ws = wb.active
    ws.title = "Report"
    ws["A1"], ws["A1"].font = f"Report: {obj.name} ({obj.reference_text})", Font(bold=True, size=13)
    ws["A2"], ws["A2"].font = ("Fill in the yellow cells. Then: python -m ckb report --template this_file.xlsx "
                               "--pdf --docx"), grey
    r = 4
    for label, key in FIELDS:
        ws[f"A{r}"], ws[f"B{r}"] = label, obj.name if key == "title" else ""
        ws[f"B{r}"].fill = fill
        r += 1
    ws[f"A{r}"], ws[f"B{r}"] = "Decimals", 2
    ws[f"A{r + 1}"], ws[f"B{r + 1}"] = "Significant digits for small values", 3
    for rr in (r, r + 1):
        ws[f"B{rr}"].fill = fill
    r += 3
    ws[f"A{r}"], ws[f"A{r}"].font = "Values for every case (a column in Cases overrides them)", bold
    ws[f"A{r + 1}"], ws[f"B{r + 1}"], ws[f"C{r + 1}"] = "Quantity", "Value", "Unit"
    for c in "ABC":
        ws[f"{c}{r + 1}"].fill, ws[f"{c}{r + 1}"].font = head, bold
    r += 2
    coeffs = [p for p in inputs if kb.quantities.get(p) and kb.quantities[p].kind == "coefficient"]
    for p in coeffs:
        ws[f"A{r}"] = kb.var(p)
        ws[f"B{r}"] = round(U.from_canonical(values[p], kb.unit(p)), 6)
        ws[f"C{r}"] = "" if kb.unit(p) == "-" else kb.unit(p)
        ws[f"D{r}"], ws[f"D{r}"].font = f"{kb.quantities[p].name} (recommended value)", grey
        ws[f"B{r}"].fill = fill
        r += 1
    r += 1
    ws[f"A{r}"], ws[f"A{r}"].font = "Display units (leave empty for the usual unit)", bold
    ws[f"A{r + 1}"], ws[f"B{r + 1}"] = "Quantity", "Unit"
    for c in "AB":
        ws[f"{c}{r + 1}"].fill, ws[f"{c}{r + 1}"].font = head, bold
    r += 2
    from .webapp import unit_choices
    for sid in list(reversed(steps)) + inputs + ([obj.check] if obj.check else []):
        opts = [u for u, _ in unit_choices(kb.unit(sid))]
        if len(opts) < 2:
            continue
        ws[f"A{r}"], ws[f"C{r}"] = kb.var(sid), kb.item(sid).name
        ws[f"C{r}"].font = grey
        ws[f"B{r}"].fill = fill
        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"B{r}")
        r += 1
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 34, 22
    ws.column_dimensions["C"].width, ws.column_dimensions["D"].width = 12, 60

    bl = wb.create_sheet("Blocks")
    for i, h in enumerate(BLOCK_COLS):
        c = bl.cell(row=1, column=i + 1, value=h)
        c.font, c.fill = bold, head
    x = next((p for p in inputs if kb.quantities.get(p) and kb.quantities[p].kind == "input"), inputs[0])
    rows = [["heading", "", obj.name],
            ["calc", target, "", "governing", "yes", "yes", "yes", "all", "", "", "", "", "", "", "no"],
            ["table", target, "", "", "", "", "", "", "", "utilisation desc" if obj.check else ""],
            ["chart", target, "", "governing", "", "", "", "", "", "", kb.var(x)]]
    for r_, row in enumerate(rows, 2):
        for c_, v in enumerate(row, 1):
            bl.cell(row=r_, column=c_, value=v)
    for col, choices in (("A", ("heading", "text", "calc", "table", "chart", "page break")),
                         ("E", YES), ("F", YES), ("G", YES), ("O", YES), ("H", ("all", "result"))):
        dv = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True)
        bl.add_data_validation(dv)
        dv.add(f"{col}2:{col}60")
    bl["A13"], bl["A13"].font = ("One row per block, top to bottom. Case: governing, first, or a case name. "
                                 "Steps: all, result, or a list such as k, rho_l. Table columns: e.g. case, d, "
                                 "V_Rd_c, V_Ed, utilisation, verdict (empty: the usual ones)."), grey
    for i, w in enumerate((12, 12, 40, 14, 10, 10, 8, 10, 40, 18, 12, 8, 8, 14, 12)):
        bl.column_dimensions[chr(65 + i)].width = w

    cs = wb.create_sheet("Cases")
    cols = ["case"] + [f"{kb.var(p)} [{kb.unit(p)}]" if kb.unit(p) != "-" else kb.var(p)
                       for p in inputs if p not in coeffs]
    if obj.check:
        cols.append(f"{kb.var(obj.check)} [{kb.unit(obj.check)}]")
    for i, h in enumerate(cols):
        c = cs.cell(row=1, column=i + 1, value=h)
        c.font, c.fill = bold, head
        cs.column_dimensions[c.column_letter].width = max(12, len(h) + 2)
    for k, scale in enumerate((1.0, 0.85, 1.2), 2):
        cs.cell(row=k, column=1, value=f"Case {k - 1}")
        for i, p in enumerate([p for p in inputs if p not in coeffs], 2):
            cs.cell(row=k, column=i, value=round(U.from_canonical(values[p], kb.unit(p)) * scale, 3))
        if obj.check:
            q = kb.quantities.get(obj.check)
            start = q.start if q is not None and q.start else 1.0
            cs.cell(row=k, column=len(cols), value=round(U.from_canonical(start, kb.unit(obj.check)) * scale, 2))

    rm = wb.create_sheet("Remarks")
    rm["A1"], rm["B1"] = "Quantity", "Remark"
    for c in "AB":
        rm[f"{c}1"].font, rm[f"{c}1"].fill = bold, head
    rm["A2"], rm["B2"] = kb.var(x), ""
    rm.column_dimensions["A"].width, rm.column_dimensions["B"].width = 16, 70
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def read_form(path: Path) -> dict:
    """The form as a template dict (the same keys as a YAML template)."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    ws = wb["Report"]
    t: dict = {"style": {"units": {}}, "defaults": {}, "blocks": []}
    label_of = {lab: key for lab, key in FIELDS}
    section = ""
    for row in ws.iter_rows(min_row=3, values_only=True):
        a, b = (row[0], row[1] if len(row) > 1 else None)
        c = row[2] if len(row) > 2 else None
        if a is None:
            continue
        a = str(a).strip()
        if a.startswith("Values for every case"):
            section = "defaults"
            continue
        if a.startswith("Display units"):
            section = "units"
            continue
        if a in ("Quantity",):
            continue
        if a in label_of:
            t[label_of[a]] = "" if b is None else str(b)
        elif a == "Decimals" and b is not None:
            t["style"]["decimals"] = int(b)
        elif a.startswith("Significant digits") and b is not None:
            t["style"]["min_significant"] = int(b)
        elif section == "defaults" and b is not None:
            t["defaults"][f"{a} [{c}]" if c else a] = b
        elif section == "units" and b:
            t["style"]["units"][a] = str(b)
    bl = wb["Blocks"]
    head = [str(h).strip() if h else "" for h in next(bl.iter_rows(min_row=1, max_row=1, values_only=True))]
    yes = lambda v: str(v or "").strip().lower() in ("yes", "y", "true", "1")      # noqa: E731
    for row in bl.iter_rows(min_row=2, values_only=True):
        r = dict(zip(head, row))
        kind = str(r.get("Block") or "").strip().lower()
        if not kind:
            continue
        obj = str(r.get("Object") or "").strip()
        if kind == "heading":
            t["blocks"].append({"heading": str(r.get("Text") or "")})
        elif kind == "text":
            t["blocks"].append({"text": str(r.get("Text") or "")})
        elif kind == "page break":
            t["blocks"].append({"pagebreak": True})
        elif kind == "calc" and obj:
            show = [k for k, col in (("equation", "Equation"), ("substituted", "Substituted values"),
                                     ("result", "Result")) if yes(r.get(col))] or ["result"]
            steps = str(r.get("Steps") or "all").strip()
            b = {"calc": obj, "case": str(r.get("Case") or "governing"), "show": show,
                 "steps": steps if steps in ("all", "result") else [s.strip() for s in steps.split(",") if s.strip()],
                 "limitations": yes(r.get("Scope and limitations"))}
            t["blocks"].append(b)
        elif kind == "table" and obj:
            b = {"table": obj}
            if r.get("Table columns"):
                b["columns"] = [s.strip() for s in str(r["Table columns"]).split(",") if s.strip()]
            if r.get("Sort by"):
                b["sort"] = str(r["Sort by"])
            t["blocks"].append(b)
        elif kind == "chart" and obj:
            b = {"chart": obj, "case": str(r.get("Case") or "governing")}
            if r.get("Chart: vary"):
                b["x"] = str(r["Chart: vary"])
            if r.get("From") is not None and r.get("To") is not None:
                b["range"] = [float(r["From"]), float(r["To"])]
            if r.get("Also show"):
                b["series"] = [obj, str(r["Also show"])]
            t["blocks"].append(b)
    cs = wb["Cases"]
    rows = list(cs.iter_rows(values_only=True))
    if rows:
        hdr = [str(h).strip() if h is not None else "" for h in rows[0]]
        t["cases"] = [{h: v for h, v in zip(hdr, r) if h and v is not None} for r in rows[1:] if any(v is not None for v in r)]
    if "Remarks" in wb.sheetnames:
        remarks = {str(a).strip(): str(b) for a, b in wb["Remarks"].iter_rows(min_row=2, max_col=2, values_only=True)
                   if a and b}
        for b in t["blocks"]:
            if "calc" in b and remarks:
                b["remarks"] = remarks
    return t
