"""Scans, handwritten sheets and prints -> statements, through a vision model.

Used for an image, for a PDF without a text layer, and - on request - for a
text PDF whose formulas should be recovered and not only its printed values.
The model transcribes; arithmetic decides.  Every transcribed formula is
re-evaluated from the transcribed inputs and is accepted only if it gives the
transcribed result (see ``records.py``).  Without a configured model the file
is flagged, not guessed at.
"""
from __future__ import annotations

from pathlib import Path

from ..ir import SourceDocument, file_sha256
from ..llm import LLMError, describe, get_llm_client
from .python_src import ConversionError
from .records import build_from_records

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["title", "quantities"],
    "properties": {
        "title": {"type": "string"},
        "quantities": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["name", "var", "formula", "value", "unit", "label", "clause", "section"],
                "properties": {
                    "name": {"type": "string"}, "var": {"type": "string"},
                    "formula": {"type": "string"}, "value": {"type": "string"},
                    "unit": {"type": "string"}, "label": {"type": "string"},
                    "clause": {"type": "string"}, "section": {"type": "string"},
                },
            },
        },
    },
}

SYSTEM = """You transcribe structural engineering calculations into data.
Read the page(s) and list every quantity that is defined or calculated, in the order it appears.
For each quantity give:
- name: the symbol exactly as written, with subscripts after an underscore (V_Rd.c, f_ck, ρ_l).
- var: the same symbol as a Python identifier (V_Rd_c, f_ck, rho_l).
- formula: the right-hand side as a Python expression using the `var` names of earlier quantities,
  with max(), min(), sqrt(), sin(), cos(), tan(), pi and `a if condition else b`.
  Write it in consistent units N, mm, MPa (a literal with a unit is converted: 200 mm -> 200,
  1.7 kN/m2 -> 0.0017, 45 deg -> 0.7853981634). For a plain input, the formula is the number itself.
  If you cannot read the formula reliably, leave it empty - do not guess.
- value: the result as printed (text of the number only), empty if none is shown.
- unit: the unit printed with the result, empty if dimensionless.
- label: the descriptive text next to it.  clause: any code reference next to it.
- section: the heading it stands under.
Transcribe only what is on the page. Do not correct the calculation and do not add steps."""


def convert_scan(path: Path, llm=None, kind: str = "scan") -> SourceDocument:
    path = Path(path)
    llm = llm or get_llm_client()
    if not llm.available():
        raise ConversionError(
            "this file has no machine-readable content (scan, photo or handwriting); it needs the "
            "vision transcription path, which requires a language model (set ANTHROPIC_API_KEY)")
    data = path.read_bytes()
    is_pdf = data[:4] == b"%PDF"
    try:
        answer = llm.complete_json(
            SYSTEM, "Transcribe this calculation.", schema=SCHEMA, task="transcribe",
            documents=[data] if is_pdf else (), images=() if is_pdf else [data])
    except LLMError as exc:
        raise ConversionError(f"vision transcription failed: {exc}") from exc
    doc = SourceDocument(name=path.name, kind=kind, sha256=file_sha256(path),
                         converter=f"vision transcription ({describe(llm)}), verified by re-evaluation")
    doc.meta["units"] = "declared"
    doc.meta["title"] = answer.get("title", "")
    records = []
    for q in answer.get("quantities", []):
        rec = dict(q)
        rec["section"] = [q["section"]] if q.get("section") else []
        records.append(rec)
    build_from_records(doc, records)
    return doc
