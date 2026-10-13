"""Mathcad Prime ingestion: units inside formulas, conditionals,
precedence, display units, checks — on a fixture with the real worksheet
XML layout."""

from xml.etree import ElementTree as ET

import pytest

from examples.make_fixtures import make_stud_mcdx
from src.ingestion.base import get_parser
from src.ingestion.mathcad_parser import ML, _translate, _Untranslatable


@pytest.fixture()
def stud_tool(tmp_path):
    path = make_stud_mcdx(tmp_path)
    return get_parser(path).parse(path)


def test_stud_sheet_reproduces_ec4_values(stud_tool):
    assert stud_tool.title == "Shear resistance of headed studs"
    assert stud_tool.reference == "EN 1994-1-1 6.6.3.1"
    assert stud_tool.warnings == [] and stud_tool.clarifications == []
    sheet = stud_tool.to_sheet()
    r = sheet.results()
    assert r["P_Rd_1"] == pytest.approx(81.66, abs=0.01)     # eq. 6.18, kN
    assert r["P_Rd_2"] == pytest.approx(83.33, abs=0.01)     # eq. 6.19, kN
    assert r["P_Rd"] == pytest.approx(81.66, abs=0.01)
    assert r["UR"] == pytest.approx(0.7005, abs=1e-4)
    assert sheet.units["UR"] == "-"            # inferred: dimensionless
    assert sheet.all_passed()                   # UR <= 1


def test_unit_written_inside_a_formula_is_honoured(stud_tool):
    # h_eff = h_sc - 0.003 m must be 97 mm, not 100 - 0.003
    sheet = stud_tool.to_sheet()
    assert sheet.results()["h_eff"] == pytest.approx(97.0)
    step = next(i for i in sheet.calcs() if i.name == "h_eff")
    assert r"\mathrm{m}" in step.latex_symbolic


def test_if_conditional_takes_the_right_branch(stud_tool):
    sheet = stud_tool.to_sheet()
    assert sheet.results()["alpha"] == 1.0                   # h_sc/d >= 4
    short = sheet.recompute({"h_sc": 60})                    # h_sc/d = 3.16
    assert short["results"]["alpha"] == pytest.approx(0.2 * (60 / 19 + 1))


def test_sums_inside_products_keep_their_parentheses(stud_tool):
    alpha = next(v for v in stud_tool.variables if v.name == "alpha")
    # 0.2*(h/d + 1), never 0.2*h/d + 1
    assert "0.2*((h_sc)/(d)+1)" in alpha.expression


def _xml(body: str):
    return ET.fromstring(f'<root xmlns:ml="{ML[1:-1]}">{body}</root>')[0]


def test_program_if_otherwise_becomes_piecewise():
    node = _xml(
        "<ml:program>"
        '<ml:ifThen><ml:apply><ml:lessOrEqual/><ml:id labels="VARIABLE">t'
        "</ml:id><ml:real>16</ml:real></ml:apply><ml:real>355</ml:real>"
        "</ml:ifThen>"
        "<ml:otherwise><ml:real>345</ml:real></ml:otherwise>"
        "</ml:program>")
    assert _translate(node) == "Piecewise((355, ((t) <= (16))), (345, True))"


def test_unknown_unit_is_a_clarification_not_a_number():
    node = _xml('<ml:apply><ml:mult/><ml:real>3</ml:real>'
                '<ml:id labels="UNIT">furlong</ml:id></ml:apply>')
    with pytest.raises(_Untranslatable, match="furlong"):
        _translate(node)


def test_agentic_ingest_of_mathcad_converges(tmp_path):
    from src.ingestion.agent import ingest

    path = make_stud_mcdx(tmp_path)
    res = ingest(path, tmp_path / "repo", answers={"final-result": "UR"},
                 render_pdf=False)
    assert res.converged
    import json

    data = json.loads(open(res.paths["json"]).read())
    assert data["results"]["P_Rd"] == pytest.approx(81.66, abs=0.01)
    assert data["unit_aware"] is True
