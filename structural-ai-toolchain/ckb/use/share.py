"""A package to hand to people who don't run Python: ``python -m ckb share -o workshop``.

    workshop/index.html          the web calculator, with an Excel calculator and a Mathcad
                                 worksheet for every object inside it (downloads work offline)
    workshop/examples/           a report run over several cases (PDF with bookmarks, Word, HTML),
                                 its template, and the Excel form that replaces the template
    workshop/READ ME.txt         what to open and how
    workshop.zip                 all of it, for SharePoint, Teams or e-mail

Everything in it is generated from the knowledge base, so it is as anonymous as the
knowledge base it was built from.
"""
from __future__ import annotations

import base64
import shutil
import tempfile
import zipfile
from pathlib import Path

from ..kb.objects import KnowledgeBase
from .excel_bridge import export_calculator, layout
from .mathcad_export import export_worksheet

README = """Calculation knowledge base - workshop package
=============================================

1. Open index.html in a browser (Edge or Chrome). Nothing to install; it works offline.
   - Find a quantity in the tree on the left, or search ("concrete shear", "V_Rd,c", "6.2.2").
   - Calculate tab: type the inputs; equations, substituted values and the result update as you type.
   - "Take it with you": an Excel calculator with your inputs and live formulas, a Mathcad Prime
     worksheet, or the calculation as a page to print to PDF (Ctrl+P).
   - Design background, Chart, Code and Status tabs: where the expression applies, a parameter
     study, the code block, and the evidence behind the object.
   The Excel download carries the inputs on the page when the browser can reach cdnjs.cloudflare.com;
   offline it carries example inputs, which you change in Excel.

2. examples/ holds a report run over five slab strips (PDF with bookmarks, Word with editable
   equations), the template that produced it, and an Excel form that does the same without YAML.
   Reports from your own templates need the Python package: python -m ckb report --template ... --pdf --docx

Every file carries the version of the logic it was made from ("ckb <object> <version>").
"""


def calculator_files(kb: KnowledgeBase, log=print) -> dict:
    """{object id: {xlsx, mcdx (base64), cells, check}} for every object that exports."""
    out, failed = {}, []
    with tempfile.TemporaryDirectory(prefix="ckb_share_") as tmp:
        for oid in kb.objects:
            try:
                x = export_calculator(kb, oid, Path(tmp) / f"{oid}.xlsx")
                m = export_worksheet(kb, oid, Path(tmp) / f"{oid}.mcdx")
            except Exception as exc:                              # noqa: BLE001 - leave that object out
                failed.append(f"{oid}: {exc}")
                continue
            _, _, cells = layout(kb, oid)
            last = int(cells[oid][1:])
            entry = {"xlsx": base64.b64encode(x.read_bytes()).decode(),
                     "mcdx": base64.b64encode(m.read_bytes()).decode(),
                     "cells": cells}
            if kb.objects[oid].check:
                entry["check"] = f"C{last + 3}"                   # the "to check against" input cell
            out[oid] = entry
    if failed:
        log(f"    no Excel/Mathcad file for {len(failed)} object(s): " + "; ".join(failed[:3]))
    return out


def write_bundle(kb: KnowledgeBase, out_dir: Path, examples_dir: Path | None = None, log=print) -> Path:
    from . import report as R
    from .report_docx import render_docx
    from .report_form import write_form
    from .webapp import write
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files = calculator_files(kb, log)
    write(kb, out / "index.html", standalone=True, files=files)
    log(f"    web calculator with {len(files)} Excel calculators and Mathcad worksheets -> {out / 'index.html'}")
    ex = out / "examples"
    ex.mkdir()
    template_file = (examples_dir / "slab_strips.yaml") if examples_dir else None
    if template_file and template_file.exists() and "V_Rd_c" in kb.objects:
        template = R.load_template(template_file)
        page = R.render(kb, template, examples_dir)
        (ex / "slab_strips_report.html").write_text(page, encoding="utf-8")
        R.to_pdf(ex / "slab_strips_report.html", ex / "slab_strips_report.pdf")
        render_docx(kb, template, ex / "slab_strips_report.docx", examples_dir)
        for f in examples_dir.glob("slab_strips.*"):
            shutil.copy(f, ex / f.name)
        write_form(kb, "V_Rd_c", ex / "report_form_V_Rd_c.xlsx")
    (out / "READ ME.txt").write_text(README, encoding="utf-8")
    zip_path = out.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, Path(out.name) / f.relative_to(out))
    return zip_path
