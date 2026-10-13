"""JSON schemas the model's answers must satisfy (structured outputs).

Every schema is strict: all properties required, no extra keys, so the
caller can index the answer without defensive ``.get`` chains and a
malformed answer is rejected at the API instead of half-parsed here.
"""

from __future__ import annotations


def _obj(**props) -> dict:
    return {"type": "object", "properties": props,
            "required": list(props), "additionalProperties": False}


def _arr(items: dict) -> dict:
    return {"type": "array", "items": items}


_STR = {"type": "string"}
_NUM_OR_NULL = {"anyOf": [{"type": "number"}, {"type": "null"}]}


def _enum(*values: str) -> dict:
    return {"type": "string", "enum": list(values)}


# AI Grinder: assign meaning to the cells of a messy workbook.
INTERPRETATION = _obj(
    title=_STR,
    reference=_STR,
    cell_map=_arr(_obj(cell=_STR, name=_STR)),
    variables=_arr(_obj(
        name=_STR,
        role=_enum("input", "derived", "check"),
        cell=_STR,
        value=_NUM_OR_NULL,
        unit=_STR,
        description=_STR,
        formula=_STR,
    )),
    clarifications=_arr(_obj(
        location=_STR, issue=_STR, question=_STR,
        options=_arr(_STR), context=_STR,
    )),
)

# Agentic research stage: which standard and clause each step implements.
RESEARCH = _obj(
    standard=_STR,
    fragments=_arr(_obj(
        name=_STR,
        clause=_STR,
        confidence=_enum("high", "medium", "low"),
        note=_STR,
    )),
    missing_steps=_arr(_obj(description=_STR, clause=_STR)),
)

_FINDING = _obj(
    severity=_enum("error", "warning", "info"),
    code=_STR,
    location=_STR,
    message=_STR,
    suggested_fix=_STR,
)

# A concrete, machine-applicable correction. The reviewer proposes it; the
# deterministic engine re-evaluates the sheet with it and only keeps it if
# the numbers then agree with the original.
_CORRECTION = _obj(
    name=_STR,
    issue=_enum("value", "unit", "formula", "missing", "label"),
    original=_STR,
    produced=_STR,
    proposed_expression=_STR,
    proposed_unit=_STR,
    proposed_value=_NUM_OR_NULL,
)

# Master reviewer (visual + numeric) and agentic self-reflection.
REVIEW = _obj(
    verdict=_enum("APPROVE", "APPROVE_WITH_COMMENTS", "REWORK"),
    findings=_arr(_FINDING),
    corrections=_arr(_CORRECTION),
)

# Transcription of the values an ORIGINAL calculation prints.
ORIGINAL_VALUES = _obj(
    values=_arr(_obj(name=_STR, value=_NUM_OR_NULL, unit=_STR, shown=_STR)),
)
