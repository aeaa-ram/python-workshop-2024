"""The AI Grinder pipeline (stages 3-6) — orchestration.

extract  ->  interpret (LLM | heuristic)  ->  translate (deterministic)
        ->  verify (recompute vs cached)   ->  ParsedTool (+ clarifications)

Design guarantee: the LLM only assigns *meaning* (roles, names, units, the
cell->symbol map). All arithmetic is redone deterministically by the
CalcSheet engine and cross-checked against the workbook's own cached
values — so a wrong AI guess surfaces as a clarification, never as a
silently-wrong tool.
"""

from __future__ import annotations

from pathlib import Path

from src.ingestion.excel_parser import translate_excel_formula
from src.ingestion.interpret import (
    HeuristicInterpreter,
    Interpretation,
    LLMInterpreter,
)
from src.ingestion.llm_client import get_llm_client
from src.ingestion.workbook_extract import extract_workbook
from src.models.calculation import Clarification, ParsedTool, ParsedVariable

# accept a recomputed value if within this relative tolerance of the cached
_VERIFY_RTOL = 1e-3


def choose_interpreter(prefer_client: str | None = None):
    client = get_llm_client(prefer=prefer_client)
    if client.available():
        return LLMInterpreter(client)
    return HeuristicInterpreter()


def run_ai_pipeline(path: str | Path,
                   prefer_client: str | None = None) -> ParsedTool:
    path = Path(path)
    digest = extract_workbook(path)
    interpreter = choose_interpreter(prefer_client)
    interp: Interpretation = interpreter.interpret(digest)

    tool = ParsedTool(
        title=interp.title or path.stem.replace("_", " ").title(),
        source_path=str(path),
        source_format=path.suffix.lstrip("."),
        reference=interp.reference,
        interpreter=interp.interpreter,
    )

    # carry over interpreter-raised clarifications
    for c in interp.clarifications:
        tool.clarifications.append(Clarification(
            location=c.get("location", "?"),
            issue=c.get("issue", "ambiguous"),
            question=c.get("question", ""),
            options=list(c.get("options", [])),
            context=str(c.get("context", "")),
        ))

    cell_map = dict(interp.cell_map)
    # cached values by variable name, for verification + fallbacks
    cached_by_name: dict[str, float] = {}
    for spec in interp.variables:
        if _is_number(spec.value):
            cached_by_name[spec.name] = float(spec.value)

    for spec in interp.variables:
        sheet = spec.cell.split("!", 1)[0] if "!" in spec.cell else \
            (digest.sheet_names[0] if digest.sheet_names else "Sheet1")

        if spec.role == "input":
            tool.variables.append(ParsedVariable(
                name=spec.name, value=_num(spec.value), unit=spec.unit,
                description=spec.description, role="input",
                source_cell=spec.cell,
            ))
            continue

        # derived or check -> translate the Excel formula
        tr = translate_excel_formula(spec.formula, sheet, cell_map)

        if tr.unknown_funcs:
            tool.clarifications.append(Clarification(
                location=spec.cell, issue="untranslatable-function",
                question=(f"'{spec.name}' at {spec.cell} uses "
                          f"{tr.unknown_funcs} which reads external/lookup "
                          "data. Confirm the intended value or provide the "
                          "underlying formula."),
                options=([f"freeze at cached value {spec.value}"]
                         if _is_number(spec.value) else []),
                context=spec.formula,
            ))
            # pragmatic fallback: freeze the cached value as an input so the
            # rest of the tool still works, clearly flagged for review.
            if _is_number(spec.value):
                tool.variables.append(ParsedVariable(
                    name=spec.name, value=float(spec.value), unit=spec.unit,
                    description=(spec.description + " [frozen lookup]").strip(),
                    role="input", source_cell=spec.cell,
                    source_formula=spec.formula,
                ))
            continue

        if tr.unresolved_refs:
            tool.clarifications.append(Clarification(
                location=spec.cell, issue="unresolved-reference",
                question=(f"'{spec.name}' at {spec.cell} references "
                          f"{tr.unresolved_refs} which could not be mapped "
                          "to a named quantity. What are they?"),
                context=spec.formula,
            ))
            if _is_number(spec.value):
                tool.variables.append(ParsedVariable(
                    name=spec.name, value=float(spec.value), unit=spec.unit,
                    description=(spec.description + " [unresolved refs]").strip(),
                    role="input", source_cell=spec.cell,
                    source_formula=spec.formula,
                ))
            continue

        if tr.is_check:
            normalized = tr.check_expression.replace(" ", "")
            if normalized not in {c.replace(" ", "") for c in tool.checks}:
                tool.checks.append(tr.check_expression)
        else:
            tool.variables.append(ParsedVariable(
                name=spec.name, expression=tr.expression, unit=spec.unit,
                description=spec.description, role="derived",
                value=_num(spec.value), source_cell=spec.cell,
                source_formula=spec.formula,
            ))

    _verify_against_cached(tool, cached_by_name)

    if not tool.variables:
        tool.warnings.append(
            "The AI parser found no usable quantities — the sheet may be "
            "empty, image-based, or entirely lookup-driven. Manual review "
            "needed."
        )
    return tool


def _verify_against_cached(tool: ParsedTool, cached: dict[str, float]) -> None:
    """Recompute the derived quantities and compare to the workbook's own
    cached values; mismatches become clarifications (translation caught)."""
    try:
        sheet = tool.to_sheet()
    except Exception as exc:  # never let verification crash a parse
        tool.warnings.append(f"Verification skipped: {exc}")
        return
    results = sheet.results()
    for name, cached_val in cached.items():
        if name in results and cached_val not in (0, None):
            recomputed = results[name]
            if abs(recomputed - cached_val) > _VERIFY_RTOL * abs(cached_val):
                tool.clarifications.append(Clarification(
                    location=name, issue="value-mismatch",
                    question=(f"Recomputed '{name}' = {recomputed:.4g} but "
                              f"the sheet's cached value is {cached_val:.4g}. "
                              "The translated formula may be wrong — please "
                              "confirm."),
                    context=f"recomputed={recomputed}, cached={cached_val}",
                ))


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _num(v):
    return float(v) if _is_number(v) else None
