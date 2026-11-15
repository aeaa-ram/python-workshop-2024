"""A package to hand to people who don't run Python: ``python -m ckb share -o workshop``.

    workshop/index.html          the web calculator, with an Excel calculator and a Mathcad
                                 worksheet for every object inside it (downloads work offline)
    workshop/READ ME.txt         what to open and how
    workshop.zip                 both, for SharePoint, Teams or e-mail

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

README = """Calculation Knowledge Base
==========================

Open index.html in a browser (Edge or Chrome). Nothing to install; it works offline.

- Find a quantity in the list on the left, or search ("concrete shear", "V_Rd,c", "6.2.2").
- Calculate: type the inputs; the calculation updates as you type.
- Download Excel: a calculator with your inputs and live formulas.
- Download Mathcad: a Mathcad Prime worksheet.
- Cases and report: add several sets of inputs and download the report as PDF or Word.
- Design background, Chart, Code and Status: where the expression applies, a parameter
  study, the code, and the evidence behind it.
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


def write_bundle(kb: KnowledgeBase, out_dir: Path, log=print) -> Path:
    from .webapp import write
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files = calculator_files(kb, log)
    write(kb, out / "index.html", standalone=True, files=files)
    log(f"    web calculator with {len(files)} Excel calculators and Mathcad worksheets -> {out / 'index.html'}")
    (out / "READ ME.txt").write_text(README, encoding="utf-8")
    zip_path = out.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, Path(out.name) / f.relative_to(out))
    return zip_path
