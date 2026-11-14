"""Calculation objects as tools for an AI assistant.

An assistant should not do structural arithmetic from memory.  With these
definitions it calls the knowledge base instead: the numbers come from the
same deterministic, benchmarked objects an engineer uses, and the answer
carries every step and its clause, so the assistant can show its working.

``definitions`` returns one tool per object in the JSON-schema form used by
tool-calling APIs; ``call`` executes one.
"""
from __future__ import annotations

from .. import units as U
from ..kb.objects import KnowledgeBase, ResolveError
from .calc import run


def definitions(kb: KnowledgeBase) -> list[dict]:
    tools = []
    for o in kb.objects.values():
        _, inputs = kb.plan(o.id)
        props, required = {}, []
        for p in inputs:
            q = kb.quantities.get(p) or kb.objects.get(p)
            unit = kb.unit(p)
            props[kb.var(p) if _unique(kb, inputs, p) else p] = {
                "type": "number",
                "description": f"{q.name if q else p} ({kb.name(p)})" + (f", in {unit}" if unit != "-" else ", dimensionless"),
            }
            required.append(kb.var(p) if _unique(kb, inputs, p) else p)
        tools.append({
            "name": f"calc_{o.id}",
            "description": (f"{o.name} ({o.text}), {o.reference_text}. Result in {o.unit if o.unit != '-' else 'no unit'}. "
                            f"Status: {o.status}; {o.benchmarks.get('agree', 0)} of {o.benchmarks.get('total', 0)} "
                            "source values reproduced. Returns the value with every intermediate step and its clause."
                            + (" Warning: " + " ".join(o.warnings) if o.warnings else "")),
            "input_schema": {"type": "object", "properties": props, "required": required,
                             "additionalProperties": False},
        })
    return tools


def _unique(kb: KnowledgeBase, inputs: list, p: str) -> bool:
    return sum(kb.var(x) == kb.var(p) for x in inputs) == 1


def call(kb: KnowledgeBase, name: str, arguments: dict) -> dict:
    """Run a tool call.  Arguments are in the units given in the tool definition."""
    oid = name[5:] if name.startswith("calc_") else name
    if oid not in kb.objects:
        return {"error": f"unknown tool {name}"}
    _, inputs = kb.plan(oid)
    key = {(kb.var(p) if _unique(kb, inputs, p) else p): p for p in inputs}
    values = {}
    for k, v in arguments.items():
        if k not in key:
            return {"error": f"{k} is not an input of {name}"}
        values[key[k]] = kb.from_display(key[k], float(v))
    try:
        res = run(kb, oid, values)
    except ResolveError as exc:
        return {"error": str(exc)}
    return {
        "result": {"symbol": kb.name(oid), "value": res.shown, "unit": res.unit},
        "steps": [{"symbol": ln.text, "name": ln.name, "value": ln.shown, "unit": ln.unit,
                   "reference": ln.reference, "status": ln.status} for ln in res.steps],
        "warnings": res.warnings, "notes": res.notes,
    }
