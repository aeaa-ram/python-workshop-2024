"""Deterministic QA checks for tools — runs offline, every time.

These catch the mechanical problems; the AI reviewer (ai_reviewer.py)
handles the engineering-judgment ones (assumptions, code compliance,
validity ranges).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.models.calculation import CalcSheet


@dataclass
class QAFinding:
    severity: str  # 'error' | 'warning' | 'info'
    code: str
    message: str

    def __str__(self) -> str:
        icon = {"error": "⛔", "warning": "⚠️ ", "info": "ℹ️ "}[self.severity]
        return f"{icon} [{self.code}] {self.message}"


_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?(?:[eE]\d+)?)(?![\w.])")
_HARMLESS_NUMBERS = {"1", "2", "3", "4", "6", "8", "0.5", "28"}


def run_checks(sheet: CalcSheet) -> list[QAFinding]:
    findings: list[QAFinding] = []
    findings += _unused_inputs(sheet)
    findings += _no_verification(sheet)
    findings += _magic_numbers(sheet)
    findings += _missing_metadata(sheet)
    findings += _library_bypass(sheet)
    findings += _synonym_clashes(sheet)
    return findings


def _synonym_clashes(sheet: CalcSheet) -> list[QAFinding]:
    """Flag variables that mean the same physical quantity (should merge)."""
    from src.models.naming import find_synonym_clashes

    names = [i.name for i in sheet.inputs() + sheet.calcs()]
    out = []
    for concept, clashing in find_synonym_clashes(names):
        out.append(
            QAFinding(
                "warning", "synonym-clash",
                f"Variables {clashing} all mean '{concept}' — use one name "
                "consistently (the AI/graph treats these as duplicates).",
            )
        )
    return out


def _unused_inputs(sheet: CalcSheet) -> list[QAFinding]:
    used: set[str] = set()
    for item in sheet.calcs() + sheet.checks():
        used |= set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", item.expression))
    out = []
    for item in sheet.inputs():
        if item.name not in used:
            out.append(
                QAFinding(
                    "warning", "unused-input",
                    f"Input '{item.name}' is defined but never used — "
                    "leftover from the legacy sheet or a missing formula?",
                )
            )
    return out


def _no_verification(sheet: CalcSheet) -> list[QAFinding]:
    if not sheet.checks():
        return [
            QAFinding(
                "warning", "no-checks",
                "Tool has no pass/fail verification — a calculation "
                "without acceptance criteria cannot be reviewed.",
            )
        ]
    return []


def _magic_numbers(sheet: CalcSheet) -> list[QAFinding]:
    out = []
    for item in sheet.calcs():
        for num in _NUMBER.findall(item.expression):
            if num in _HARMLESS_NUMBERS:
                continue
            if float(num) in (1e3, 1e6, 1e9):
                out.append(
                    QAFinding(
                        "warning", "unit-conversion-smell",
                        f"'{item.name}' multiplies by {num} — hidden unit "
                        "conversion; make units explicit instead.",
                    )
                )
            else:
                out.append(
                    QAFinding(
                        "info", "magic-number",
                        f"'{item.name}' contains literal {num} — should "
                        "this be a named input or a code coefficient?",
                    )
                )
    return out


def _missing_metadata(sheet: CalcSheet) -> list[QAFinding]:
    out = []
    if not sheet.reference:
        out.append(
            QAFinding(
                "warning", "no-reference",
                "No code/standard reference on the sheet — reviewers "
                "cannot verify clause compliance.",
            )
        )
    for item in sheet.inputs() + sheet.calcs():
        if not item.description:
            out.append(
                QAFinding(
                    "info", "no-description",
                    f"'{item.name}' has no description.",
                )
            )
        if not item.unit:
            out.append(
                QAFinding(
                    "info", "no-unit",
                    f"'{item.name}' has no unit (use '-' if dimensionless).",
                )
            )
    return out


def _library_bypass(sheet: CalcSheet) -> list[QAFinding]:
    """Formulas that re-implement a library atom instead of apply()ing it."""
    from src.knowledge_graph.fingerprint import try_fingerprint
    from src.library import all_atoms

    atom_fps = {}
    for atom in all_atoms():
        fp = try_fingerprint(atom.expression)
        if fp:
            atom_fps[fp] = atom.atom_id
    out = []
    for item in sheet.calcs():
        if item.atom_id:
            continue  # already reusing the library
        fp = try_fingerprint(item.expression)
        if fp and fp in atom_fps:
            out.append(
                QAFinding(
                    "warning", "library-bypass",
                    f"'{item.name}' re-implements library atom "
                    f"'{atom_fps[fp]}' — use sheet.apply() so there is "
                    "one source of truth.",
                )
            )
    return out
