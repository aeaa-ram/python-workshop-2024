"""Is this file still the knowledge base's logic?

Every file the knowledge base writes carries the object id and the version of its
design logic (a fingerprint of formula, unit and checks):

    Python code block   a "# ckb <object> <version>" line
    Excel calculator    a hidden sheet with the formulas as generated
    Mathcad worksheet   the document description
    report (HTML/PDF)   a "ckb <object> <version>" line per calculation

``verify`` reads that back and checks three things: the version is the current one,
nothing was edited, and the numbers in the file are the numbers the knowledge base
gives for the same inputs (Excel recalculated by LibreOffice, Mathcad read back with
mcad2py, Python run in a separate process).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ..kb.objects import KnowledgeBase


def verify(kb: KnowledgeBase, path: Path) -> dict:
    path = Path(path).resolve()
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        from .excel_bridge import verify as v
        return v(kb, path)
    if ext == ".mcdx":
        from .mathcad_export import verify as v
        return v(kb, path)
    if ext == ".py":
        return _verify_python(kb, path)
    if ext in (".html", ".htm", ".pdf"):
        return _verify_report(kb, path)
    return {"ok": False, "reason": f"{ext} files are not produced by the knowledge base"}


def _versions(text: str) -> list[tuple[str, str]]:
    return re.findall(r"ckb ([A-Za-z_]\w*) ([0-9a-f]{12})", text)


def _verify_report(kb: KnowledgeBase, path: Path) -> dict:
    if path.suffix.lower() == ".pdf":
        try:
            text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.TimeoutExpired):
            return {"ok": False, "reason": "pdftotext is needed to read a PDF"}
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    found = _versions(text)
    if not found:
        return {"ok": False, "reason": "no calculation from the knowledge base found in this report"}
    rows = []
    for oid, ver in dict.fromkeys(found):
        now = kb.objects[oid].version if oid in kb.objects else None
        rows.append({"id": oid, "version_in_file": ver, "version_now": now, "agree": ver == now})
    return {"ok": all(r["agree"] for r in rows), "rows": rows,
            "note": "a report is a record: its numbers are checked when it is regenerated, not read back"}


def _verify_python(kb: KnowledgeBase, path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    found = _versions(text)
    if not found:
        return {"ok": False, "reason": "not a code block generated from the knowledge base"}
    oid, ver = found[0]
    if oid not in kb.objects:
        return {"ok": False, "reason": f"object {oid} is not in this knowledge base"}
    obj = kb.objects[oid]
    out = {"object": oid, "version_in_file": ver, "version_now": obj.version, "same_version": ver == obj.version}
    # run the function from the file, in its own package, at the default inputs and at a few
    # other points, and compare with the knowledge base
    from .calc import starting_values
    values, _ = starting_values(kb, oid)
    points = [values]
    for scale in (0.8, 1.25):
        points.append({k: (v * scale if isinstance(v, float) and kb.quantities.get(k) and
                           kb.quantities[k].kind == "input" else v) for k, v in values.items()})
    steps, inputs = kb.plan(oid)
    fn = kb.var(oid)
    script = (f"import json, sys\nsys.path.insert(0, {str(path.parent.parent)!r})\n"
              f"from {path.parent.name}.{path.stem} import *\n"
              f"pts = json.loads(sys.argv[1])\nout = []\n"
              f"for p in pts:\n    out.append({fn}_chain(**p) if {len(steps) > 1} else {fn}(**p))\n"
              f"print(json.dumps(out))\n")
    args = [{kb.var(k): v for k, v in p.items() if k in inputs} for p in points]
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "run.py").write_text(script, encoding="utf-8")
        proc = subprocess.run([sys.executable, "-I", str(Path(tmp) / "run.py"), json.dumps(args)],
                              capture_output=True, text=True, timeout=60, cwd=tmp)
    try:
        got = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        out.update(ok=False, reason="the code block did not run: " + proc.stderr.strip()[-300:])
        return out
    rows = []
    for p, g in zip(points, got):
        want, _ = kb.evaluate(oid, {k: v for k, v in p.items() if k in inputs})
        rows.append({"inputs": {k: p[k] for k in inputs}, "file": g, "knowledge_base": want,
                     "agree": abs(g - want) <= 1e-9 * max(1.0, abs(want))})
    out["rows"] = rows
    out["ok"] = out["same_version"] and all(r["agree"] for r in rows)
    return out
