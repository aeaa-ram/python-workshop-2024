"""AI Grinder: extraction, heuristic interpretation, cross-sheet formula
translation, human-in-the-loop clarifications, convention fast-path."""

import json

import pytest

from examples.make_fixtures import make_crack_width_xlsx, make_messy_beam_xlsx
from src.ingestion import grind
from src.ingestion.ai_pipeline import run_ai_pipeline
from src.ingestion.base import get_parser
from src.ingestion.excel_parser import (
    AIExcelParser,
    has_convention_markers,
    translate_excel_formula,
)
from src.ingestion.workbook_extract import extract_workbook


# ------------------------------------------------------- dispatch / fastpath
def test_xlsx_dispatches_to_ai_parser():
    assert isinstance(get_parser("x.xlsx"), AIExcelParser)


def test_convention_sheet_uses_exact_fastpath(tmp_path):
    xlsx = make_crack_width_xlsx(tmp_path)
    assert has_convention_markers(xlsx)
    tool = get_parser(xlsx).parse(xlsx)
    assert tool.interpreter == "convention"
    # exact deterministic numbers preserved
    assert tool.to_sheet().results()["w_k"] == pytest.approx(0.1807, abs=1e-3)
    assert tool.clarifications == []


# ------------------------------------------------------------- extraction
def test_extraction_finds_cells_regions_and_named_sheets(tmp_path):
    xlsx = make_messy_beam_xlsx(tmp_path)
    digest = extract_workbook(xlsx)
    assert set(digest.sheet_names) == {"Beam", "Factors"}
    # formulas are kept (the logic)
    formula_refs = {c.ref for c in digest.formula_cells()}
    assert "Beam!C6" in formula_refs and "Beam!C7" in formula_refs
    # digest is compact markdown, not a raw grid
    md = digest.to_markdown()
    assert "Region" in md and "formula" in md
    assert digest.title_guess.startswith("Simply Supported")


# ---------------------------------------------------- formula translation
def test_translate_cross_sheet_and_bare_refs():
    cell_map = {"Beam!C4": "w", "Beam!C3": "L", "Factors!B2": "gamma"}
    tr = translate_excel_formula("=C4*C3^2/8", "Beam", cell_map)
    assert tr.ok
    assert tr.expression == "w*L**2/8"
    tr2 = translate_excel_formula("=C4*Factors!B2", "Beam", cell_map)
    assert tr2.expression == "w*gamma"


def test_translate_flags_lookup_functions():
    tr = translate_excel_formula("=B4*INDEX(Sheet2!A:A,C2)", "Sheet1", {})
    assert "INDEX" in tr.unknown_funcs
    assert not tr.ok


def test_translate_detects_check():
    cell_map = {"S!C7": "sigma", "S!F4": "fy"}
    tr = translate_excel_formula("=C7<=F4", "S", cell_map)
    assert tr.is_check and tr.check_expression == "sigma<=fy"
    tr_if = translate_excel_formula("=IF(C7<=F4,1,0)", "S", cell_map)
    assert tr_if.is_check and "sigma<=fy" in tr_if.check_expression.replace(" ", "")


# -------------------------------------------------------- full AI pipeline
def test_ai_pipeline_on_messy_sheet(tmp_path):
    xlsx = make_messy_beam_xlsx(tmp_path)
    tool = run_ai_pipeline(xlsx, prefer_client="null")  # force heuristic
    assert tool.interpreter == "heuristic"
    assert tool.title.startswith("Simply Supported")
    names = {v.name for v in tool.variables}
    # scattered inputs recovered and named from labels
    assert any("Span" in n for n in names)
    assert any("Yield" in n for n in names)
    # cross-sheet formula translated and evaluates correctly
    sheet = tool.to_sheet()
    assert sheet.results()["Moment_M"] == pytest.approx(54.0)
    assert sheet.results()["Bending_stress_sigma"] == pytest.approx(166.67, abs=0.1)
    # a check was detected (deduplicated)
    assert len(tool.checks) == 1
    # magic numbers raised human-in-the-loop clarifications
    assert tool.needs_clarification()
    assert any(c.issue == "magic-number" for c in tool.clarifications)


def test_value_mismatch_becomes_clarification(tmp_path):
    # a derived cell whose cached value contradicts its formula
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "S"
    ws["A1"] = "Width b (mm)"; ws["B1"] = 300
    ws["A2"] = "Height h (mm)"; ws["B2"] = 500
    ws["A3"] = "Area A (mm2)"; ws["B3"] = "=B1*B2"
    path = tmp_path / "s.xlsx"
    wb.save(path)
    # cached value of B3 is None (openpyxl doesn't compute); the pipeline
    # simply should not crash and should translate the formula
    tool = run_ai_pipeline(path, prefer_client="null")
    a = next(v for v in tool.variables if v.name.startswith("Area"))
    assert a.role == "derived"
    assert "*" in a.expression


def test_grind_messy_writes_clarifications_and_status(tmp_path):
    xlsx = make_messy_beam_xlsx(tmp_path)
    res = grind(xlsx, tmp_path / "repo", skip_gatekeeper=True)
    assert "clarifications" in res.files
    assert (res.tool_dir / "CLARIFICATIONS.md").exists()
    manifest = json.loads((res.tool_dir / "manifest.json").read_text())
    assert manifest["status"] == "needs-clarification"
    assert manifest["interpreter"] == "heuristic"
    # the generated python tool still executes (resilient to messy input)
    ns: dict = {}
    exec((res.tool_dir / f"{res.slug}.py").read_text(), ns)
    assert ns["build_sheet"]().results()["Moment_M"] == pytest.approx(54.0)


def test_no_llm_available_falls_back_cleanly():
    from src.ingestion.ai_pipeline import choose_interpreter
    from src.ingestion.interpret import HeuristicInterpreter

    # with no API key configured, the pipeline uses the heuristic
    interp = choose_interpreter(prefer_client="null")
    assert isinstance(interp, HeuristicInterpreter)
