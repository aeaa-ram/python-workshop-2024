"""Generated code blocks: one readable Python function per calculation object.

The function is printed from the object's formula, so it cannot drift from
the equation shown in a report.  Each module also offers a ``*_chain``
function that calls the objects it depends on, i.e. the calculation from the
primary inputs.  Numbers are in N, mm, MPa (N/mm²) and radians.
"""
from __future__ import annotations

import keyword
import re
import textwrap
from pathlib import Path

from .. import expr as X
from .objects import CalcObject, KnowledgeBase

_MATH = ["sqrt", "pi", "sin", "cos", "tan", "asin", "acos", "atan", "exp", "log10", "radians",
         "degrees", "floor", "ceil"]


def _vars(kb: KnowledgeBase, ids: list[str]) -> dict[str, str]:
    """Short argument names; fall back to the ids if two would collide."""
    names = {i: kb.var(i) for i in ids}
    if len(set(names.values())) != len(names) or any(keyword.iskeyword(v) for v in names.values()):
        names = {i: (i + "_" if keyword.iskeyword(i) else i) for i in ids}
    return names


def module_source(kb: KnowledgeBase, obj: CalcObject) -> str:
    """The object as a Python module: the design logic and nothing else."""
    names = _vars(kb, obj.params)
    body = X.to_python(obj.tree, lambda s: names.get(s, s))
    tokens = set(re.findall(r"[A-Za-z_]\w*(?=\()", body)) | set(re.findall(r"\bpi\b", body))
    used = sorted(f for f in _MATH if f in tokens)
    extra = []
    if "cot" in tokens:
        extra.append("\n\ndef cot(x):\n    return 1.0 / tan(x)")
        if "tan" not in used:
            used.append("tan")
    if "ln" in tokens:
        extra.append("from math import log as ln")
    fn = _fn(kb, obj.id)
    doc = [f"{obj.name} [{_canon(kb, obj.id)}]", obj.reference_text, ""]
    width = max((len(names[p]) for p in obj.params), default=1)
    for p in obj.params:
        item = kb.item(p)
        doc.append(f"{names[p]:<{width}}  {item.name if item else p} [{_canon(kb, p)}]")
    for k, v in obj.fixed.items():
        doc.append(f"{kb.name(k)} = {X._short(v)} in {obj.code}")
    steps, inputs = kb.plan(obj.id)
    others = [s for s in steps if s != obj.id]
    lines = [f'"""{obj.text} - {obj.reference_text}.  Units: N, mm, MPa, rad."""', f"# ckb {obj.id} {obj.version}"]
    if used:
        lines.append("from math import " + ", ".join(sorted(set(used))))
    lines += [e for e in extra if e.startswith("from")]
    for s in others:                       # imported under a private name: the plain names are variables
        lines.append(f"from .{s} import {_fn(kb, s)} as _{s}")
    lines += [e for e in extra if not e.startswith("from")]
    lines += ["", ""]
    lines.append(f"def {fn}({', '.join(names[p] for p in obj.params)}):")
    lines.append('    """' + "\n    ".join(doc) + '\n    """')
    lines.append(f"    return {body}")
    if others:
        chain_names = _vars(kb, inputs + steps)
        lines += ["", ""]
        lines.append(f"def {fn}_chain({', '.join(chain_names[p] for p in inputs)}):")
        lines.append(f'    """{obj.text} from the primary inputs."""')
        for k, v in obj.fixed.items():
            lines.append(f"    {chain_names.get(k, k)} = {X._short(v)}")
        for s in steps:
            o = kb.objects[s]
            args = ", ".join(chain_names.get(p, p) for p in o.params)
            lines.append(f"    return {fn}({args})" if s == obj.id else f"    {chain_names[s]} = _{s}({args})")
    return "\n".join(lines) + "\n"


def _fn(kb: KnowledgeBase, oid: str) -> str:
    v = kb.objects[oid].var or oid
    return v + "_" if keyword.iskeyword(v) else v


def _canon(kb: KnowledgeBase, sid: str) -> str:
    """Canonical unit of a quantity (what the generated function expects)."""
    from .. import units as U
    try:
        dims = U.parse_unit(kb.unit(sid)).dims
    except U.UnitError:
        return "-"
    table = {(1, 0, 0, 0): "N", (0, 1, 0, 0): "mm", (1, -2, 0, 0): "MPa", (1, 1, 0, 0): "Nmm",
             (0, 2, 0, 0): "mm2", (0, 4, 0, 0): "mm4", (0, 0, 0, 0): "-"}
    if kb.unit(sid) == "°":
        return "rad"
    return table.get(tuple(dims), U.canonical_text(dims))


def write_package(kb: KnowledgeBase, root: Path) -> Path:
    pkg = Path(root) / "ckb_objects"
    pkg.mkdir(parents=True, exist_ok=True)
    for old in pkg.glob("*.py"):
        old.unlink()
    exports = []
    for obj in kb.objects.values():
        (pkg / f"{obj.id}.py").write_text(module_source(kb, obj), encoding="utf-8")
        exports.append((obj.id, _fn(kb, obj.id), len(kb.plan(obj.id)[0]) > 1))
    init = ['"""Calculation objects distilled from source calculations (generated).',
            "", "Units: N, mm, MPa (N/mm2), rad.", '"""']
    names = {}
    for oid, fn, chain in exports:
        alias = fn if fn not in names else oid         # two objects may share a short symbol
        names[alias] = oid
        init.append(f"from .{oid} import {fn}" + (f" as {alias}" if alias != fn else "")
                    + (f", {fn}_chain" + (f" as {alias}_chain" if alias != fn else "") if chain else ""))
    (pkg / "__init__.py").write_text("\n".join(init) + "\n", encoding="utf-8")
    return pkg
