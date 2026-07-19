"""Stage 3 of the AI Grinder: interpret the digest into an Interpretation.

Two interchangeable interpreters consume the same ``WorkbookDigest`` and
produce the same ``Interpretation`` (variable dictionary + cell->symbol map
+ clarifications):

- ``LLMInterpreter``  — asks Claude to read the digest and assign roles /
  names / units, returning strict JSON. Best on messy sheets.
- ``HeuristicInterpreter`` — deterministic fallback (label-adjacency +
  formula analysis). Runs with no API/network so the pipeline and tests
  always work; the LLM simply does a better job when available.

Deliberately, NEITHER does arithmetic — they only assign meaning. The
downstream deterministic translator turns Excel formulas into math and the
CalcSheet engine recomputes, so a wrong LLM guess can be caught, not
silently trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.ingestion.workbook_extract import CellRecord, WorkbookDigest

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class VarSpec:
    name: str
    role: str                 # 'input' | 'derived' | 'check'
    cell: str = ""            # "Sheet1!C7"
    value: object = None
    unit: str = ""
    description: str = ""
    formula: str = ""         # raw Excel formula for derived/check


@dataclass
class Interpretation:
    title: str
    reference: str
    variables: list[VarSpec] = field(default_factory=list)
    cell_map: dict[str, str] = field(default_factory=dict)  # ref -> symbol
    clarifications: list[dict] = field(default_factory=list)
    interpreter: str = ""


# ------------------------------------------------------------------ #
# Prompt construction (LLM path)
# ------------------------------------------------------------------ #
SYSTEM_PROMPT = """\
You are a structural engineer digitising a legacy Excel calculation sheet.
You are given a compact digest of a workbook: named ranges and, per region,
a table of cells with any adjacent text label, the cached value, and the
Excel formula.

Your job is to assign MEANING, not to do arithmetic. For every meaningful
numeric cell decide whether it is:
  - "input": a given quantity (a number a user supplies), OR
  - "derived": computed by a formula, OR
  - "check": a verification / acceptance criterion (a comparison).

Give each a short, valid variable name using the convention: '_' starts a
subscript, '__' separates sub-parts (e.g. f_c__k, sigma_Rd__max), spell
greek out (phi, sigma, rho, epsilon). Reuse the same name for the same
quantity across sheets. Infer units and a one-line description from labels.

Rules:
- Map EVERY cell reference that a formula uses to a variable name, so the
  formula can be rewritten symbolically. Put these in "cell_map".
- If a value is a magic number with no label, or the logic is circular or
  ambiguous, DO NOT guess — add a "clarifications" entry pointing at the
  exact cell with a precise question (and options if helpful).
- Do not invent values or formulas that are not in the digest.
"""

USER_TEMPLATE = """\
Workbook digest:

{digest}

Return JSON with this shape:
{{
  "title": "...",
  "reference": "code clause if evident, else ''",
  "cell_map": {{"Sheet1!B6": "b", "Sheet1!B7": "h", ...}},
  "variables": [
    {{"name":"b","role":"input","cell":"Sheet1!B6","value":300,
      "unit":"mm","description":"Section width"}},
    {{"name":"A","role":"derived","cell":"Sheet1!B10","unit":"mm^2",
      "description":"Area","formula":"=B6*B7"}},
    {{"name":"util","role":"check","cell":"Sheet1!B20",
      "description":"Utilisation","formula":"=B18<=B19"}}
  ],
  "clarifications": [
    {{"location":"Sheet2!D14","issue":"magic-number",
      "question":"Cell D14 = 1.35 has no label. Is this a load factor?",
      "options":["load factor gamma_G","dead load","other"]}}
  ]
}}
"""


def build_prompt(digest: WorkbookDigest, max_cells: int = 400) -> tuple[str, str]:
    return SYSTEM_PROMPT, USER_TEMPLATE.format(digest=digest.to_markdown(max_cells))


# ------------------------------------------------------------------ #
# LLM interpreter
# ------------------------------------------------------------------ #
class LLMInterpreter:
    name = "llm"

    def __init__(self, client) -> None:
        self.client = client

    def interpret(self, digest: WorkbookDigest) -> Interpretation:
        system, user = build_prompt(digest)
        data = self.client.complete_json(system, user)
        variables = [
            VarSpec(
                name=v["name"], role=v.get("role", "input"),
                cell=v.get("cell", ""), value=v.get("value"),
                unit=v.get("unit", ""), description=v.get("description", ""),
                formula=v.get("formula", ""),
            )
            for v in data.get("variables", [])
        ]
        return Interpretation(
            title=data.get("title", "") or digest.title_guess,
            reference=data.get("reference", ""),
            variables=variables,
            cell_map=dict(data.get("cell_map", {})),
            clarifications=list(data.get("clarifications", [])),
            interpreter=f"llm:{getattr(self.client, 'name', '?')}",
        )


# ------------------------------------------------------------------ #
# Heuristic interpreter (deterministic, offline)
# ------------------------------------------------------------------ #
class HeuristicInterpreter:
    name = "heuristic"

    def interpret(self, digest: WorkbookDigest) -> Interpretation:
        used_names: set[str] = set()
        cell_map: dict[str, str] = {}
        specs: list[VarSpec] = []
        clarifications: list[dict] = []

        # 1) name every non-empty numeric/formula cell from its label
        for cell in digest.all_cells():
            if cell.is_formula or _is_number(cell.value):
                name = _name_from(cell, used_names)
                cell_map[cell.ref] = name

        # 2) classify
        for cell in digest.all_cells():
            if cell.ref not in cell_map:
                continue
            name = cell_map[cell.ref]
            if cell.is_formula:
                role = "check" if _looks_like_check(cell.formula) else "derived"
                specs.append(VarSpec(
                    name=name, role=role, cell=cell.ref,
                    value=cell.value, unit=_unit_from_label(cell.label),
                    description=_clean_label(cell.label) or name,
                    formula=cell.formula,
                ))
            elif _is_number(cell.value):
                if not cell.label:
                    clarifications.append({
                        "location": cell.ref, "issue": "magic-number",
                        "question": f"Cell {cell.ref} = {cell.value} has no "
                                    "adjacent label. What quantity is it?",
                        "options": [], "context": str(cell.value),
                    })
                specs.append(VarSpec(
                    name=name, role="input", cell=cell.ref,
                    value=float(cell.value),
                    unit=_unit_from_label(cell.label),
                    description=_clean_label(cell.label) or name,
                ))
        return Interpretation(
            title=digest.title_guess,
            reference="",
            variables=specs,
            cell_map=cell_map,
            clarifications=clarifications,
            interpreter="heuristic",
        )


# ------------------------------------------------------------------ #
_CHECK_HINTS = ("<=", ">=", "<", ">", "=<", "=>")
_UNIT_RE = re.compile(r"[\[(]\s*([A-Za-z%µ][A-Za-z0-9/^²³·%]*)\s*[\])]")


def _looks_like_check(formula: str) -> bool:
    body = formula[1:] if formula.startswith("=") else formula
    if body.strip().upper().startswith("IF("):
        return any(op in body for op in ("<", ">"))
    # a top-level comparison, e.g. =B18<=B19
    return any(op in body for op in ("<=", ">=", "<", ">")) and "IF" not in body.upper()


def _name_from(cell: CellRecord, used: set[str]) -> str:
    base = _slug_ident(cell.label) if cell.label else ""
    if not base:
        base = f"{_slug_ident(cell.sheet)}_{cell.coord}".lower()
    name = base
    i = 2
    while name in used:
        name = f"{base}_{i}"
        i += 1
    used.add(name)
    return name


def _slug_ident(text: str) -> str:
    text = re.sub(r"[\[(].*?[\])]", " ", str(text))  # drop bracketed units
    text = text.strip().replace("%", "pct")
    parts = re.findall(r"[A-Za-z0-9]+", text)
    if not parts:
        return ""
    ident = "_".join(parts)
    if ident[0].isdigit():
        ident = "v_" + ident
    return ident[:40]


def _clean_label(label: str) -> str:
    return re.sub(r"\s+", " ", str(label)).strip(" :=\t")


def _unit_from_label(label: str) -> str:
    m = _UNIT_RE.search(str(label))
    return m.group(1) if m else ""


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
