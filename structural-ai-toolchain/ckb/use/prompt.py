"""A calculation in the terminal: the program asks, the engineer answers.

    python -m ckb run V_Rd_c

Each input is asked for with its unit and a starting value (the recommended
value of a coefficient, an example value otherwise); pressing Enter keeps it.  The answer is the self-documenting
calculation as text.
"""
from __future__ import annotations

from .. import units as U
from ..kb.objects import KnowledgeBase
from .calc import parse_assignments, run, starting_values
from .report import render_text


def ask(kb: KnowledgeBase, target: str, preset: dict | None = None, given=(), read=input, write=print,
        style=None):
    values, origin = starting_values(kb, target, given)
    values.update(preset or {})
    _, inputs = kb.plan(target, given)
    obj = kb.objects[target]
    write(f"\n{obj.text} - {obj.name}\n{obj.reference_text}\n")
    write("Enter each value, or press Enter to keep the value in brackets.\n")
    for p in inputs:
        item = kb.quantities.get(p) or kb.objects.get(p)
        unit = "" if kb.unit(p) == "-" else kb.unit(p)
        default = values.get(p)
        shown = U.fmt(kb.to_display(p, default), 8) if isinstance(default, (int, float)) else ""
        while True:
            answer = read(f"  {kb.name(p):>10}  {item.name if item else p} [{shown}{' ' + unit if unit else ''}]: ").strip()
            if not answer:
                if default is None:
                    write("    a value is needed")
                    continue
                break
            try:
                got, _ = parse_assignments(kb, target, [f"{p}={answer}"], given)
                values[p] = got[p]
                origin[p] = "entered"
                break
            except ValueError as exc:
                write(f"    {exc}")
    check = None
    if obj.check:
        unit = kb.unit(obj.check)
        answer = read(f"  {kb.name(obj.check):>10}  design value to check against, optional [{unit}]: ").strip()
        if answer:
            try:
                check = kb.from_display(obj.check, float(answer.replace(",", ".")))
            except ValueError:
                write("    not a number; no check made")
    res = run(kb, target, values, given, origin, check, style)
    write("")
    write(render_text(kb, res))
    return res
