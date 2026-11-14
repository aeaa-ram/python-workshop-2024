"""Runs a Python source in a separate process and records every top-level value.

Used by the Python / Jupyter / Mathcad converters.  It is executed with
``python -I`` in an empty working directory; the script it runs is a source
file from the inbox, so it is treated as untrusted and never imported into
the main process.

usage: python -I _runner.py <script.py> <out.json>
"""
import ast
import json
import os
import sys


def encode(v):
    try:
        if hasattr(v, "to_base_units") and hasattr(v, "dimensionality"):
            b = v.to_base_units()
            dims = {str(k): float(p) for k, p in dict(b.dimensionality).items()}
            return {"v": float(b.magnitude), "dims": dims, "unit": format(v.units, "~")}
        if isinstance(v, bool):
            return {"v": float(v)}
        if isinstance(v, (int, float)):
            return {"v": float(v)}
        if isinstance(v, str):
            return {"v": v}
        if hasattr(v, "item") and getattr(v, "shape", None) == ():
            return {"v": float(v.item())}
    except Exception as exc:                      # noqa: BLE001
        return {"skip": f"{type(v).__name__}: {exc}"}
    return {"skip": type(v).__name__}


def main():
    src = open(sys.argv[1], encoding="utf-8").read()
    tree = ast.parse(src)
    ns = {"__name__": "__ckb_source__"}
    real_stdout, sys.stdout = sys.stdout, open(os.devnull, "w")     # the script's own prints
    records, errors = [], []
    for node in tree.body:
        mod = ast.Module(body=[node], type_ignores=[])
        try:
            exec(compile(mod, "source", "exec"), ns)          # noqa: S102
        except BaseException as exc:                           # noqa: BLE001
            errors.append({"line": node.lineno, "error": f"{type(exc).__name__}: {exc}"})
            continue
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            targets = [node.target]
        for t in targets:
            if t.id in ns:
                rec = encode(ns[t.id])
                rec.update(line=node.lineno, name=t.id)
                records.append(rec)
    json.dump({"records": records, "errors": errors}, open(sys.argv[2], "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
