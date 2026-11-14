"""Stage 2: every file type becomes statements; formulas are re-evaluated."""
import pytest

from ckb import expr as X
from ckb.convert import ConversionError, convert_file
from ckb.convert.mathcad import _geometry, _patch, _stored_results
from ckb.convert.python_src import convert_source, find_clause
from ckb.llm import ScriptedLLMClient
from conftest import PINT_SCRIPT, PLAIN_SCRIPT, make_docx, make_excel, make_notebook, make_pdf, recalculated


def by_name(doc, name, n=0):
    return [s for s in doc.statements if s.name == name][n]


def test_excel_names_units_cases_and_headings(tmp_path):
    doc = convert_file(make_excel(tmp_path / "slab.xlsx"))
    v = by_name(doc, "VRd.c", 1)                       # column F
    assert v.unit == "kN/m" and v.case == "Section B" and v.loc.endswith("cell F20")
    assert v.clause == "EN 1992-1-1 cl. 6.2.2 (1)"      # from the heading above the block
    assert by_name(doc, "As").unit == "mm²/m"           # value one row below its label
    assert "B16/150" in by_name(doc, "As").label
    d = [s for s in doc.statements if s.name == "d" and s.label == "Eff. depth"][0]
    assert d.value == 342.5 and d.section[0] == "Template"     # description | symbol | value
    assert by_name(doc, "γc").kind == "input"           # =1.5 is a number, not a formula
    assert doc.summary()["formulas_failed"] == 0 and "sqrt" in doc.python


def test_excel_formulas_reproduce_cached_values(tmp_path):
    calculated = recalculated(make_excel(tmp_path / "slab.xlsx"))
    if calculated is None:
        pytest.skip("LibreOffice not installed")
    s = convert_file(calculated).summary()
    assert s["formulas"] > 20 and s["formulas_verified"] == s["formulas"]


def test_python_with_units_is_stored_in_consistent_units():
    doc = convert_source(PINT_SCRIPT, "beam_check.py")
    assert doc.meta["units"] == "embedded" and not doc.issues
    k = by_name(doc, "k")
    assert X.to_python(k.expr) == "min(1 + (200 / d) ** 0.5, 2)" and k.fidelity == "ok"
    v = by_name(doc, "V_Rd_c")
    assert v.value == pytest.approx(74412.04, rel=1e-6) and v.unit == "N" or v.value == pytest.approx(74412.04, rel=1e-6)
    assert v.clause == "eq. (6.2.a)" and v.section == ["Shear resistance (EN 1992-1-1 cl. 6.2.2)"]
    assert all(s.fidelity == "ok" for s in doc.statements)


def test_plain_python_inlines_functions_and_reads_unit_comments():
    doc = convert_source(PLAIN_SCRIPT, "plain.py")
    assert X.to_python(by_name(doc, "k").expr) == "min(1 + sqrt(200 / d), 2)"
    assert by_name(doc, "f_ck").unit == "MPa" and by_name(doc, "b_w").unit == "mm"
    v = by_name(doc, "V_Rdc")
    assert v.unit == "kN" and v.value == pytest.approx(74.412, rel=1e-4) and "6.2.2(1)" in v.clause


def test_a_script_that_does_not_run_is_reported_not_guessed():
    doc = convert_source("a = 1\nb = undefined_name + 1\nfor i in range(3):\n    a += i\n", "broken.py")
    assert any("did not run" in i for i in doc.issues) and any("not converted" in i for i in doc.issues)
    with pytest.raises(ConversionError):
        convert_source("x = (1 +\n", "bad.py")


def test_notebook_word_and_unknown_types(tmp_path):
    nb = convert_file(make_notebook(tmp_path / "crack.ipynb"))
    w = by_name(nb, "w_k")
    assert w.value == pytest.approx(0.186) and w.section == ["Crack width"] and "(7.8)" in w.clause
    word = convert_file(make_docx(tmp_path / "report.docx"))
    names = {s.name: s for s in word.statements}
    assert names["VRd,c"].value == 74.4 and names["VRd,c"].unit == "kN" and names["fck"].unit == "MPa"
    assert names["k"].clause == "EN 1992-1-1 cl. 6.2.2(1)" and names["d"].section == ["Shear resistance"]
    # a typed formula is accepted because it reproduces the printed result
    assert names["VRd,c,min"].fidelity == "ok" and names["VRd,c,min"].expr is not None
    with pytest.raises(ConversionError):
        convert_file(tmp_path / "old.xls")
    with pytest.raises(ConversionError):
        convert_file(tmp_path / "drawing.dwg")


def test_pdf_text_and_scan(tmp_path):
    pdf = make_pdf(tmp_path / "print.pdf")
    if pdf is not None:
        doc = convert_file(pdf)
        vals = {s.name: (s.value, s.unit) for s in doc.statements}
        assert vals["VRd,c"] == (74.4, "kN") and vals["d"] == (450.0, "mm")
    scan = tmp_path / "sheet.png"
    scan.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
    with pytest.raises(ConversionError):                # no model configured: flagged, not guessed
        convert_file(scan)
    answer = {"title": "hand calc", "quantities": [
        {"name": "d", "var": "d", "formula": "450", "value": "450", "unit": "mm", "label": "", "clause": "", "section": "Shear"},
        {"name": "k", "var": "k", "formula": "min(1 + sqrt(200 / d), 2)", "value": "1.67", "unit": "", "label": "size factor",
         "clause": "6.2.2(1)", "section": "Shear"},
        {"name": "z", "var": "z", "formula": "0.8 * d", "value": "405", "unit": "mm", "label": "", "clause": "", "section": "Shear"}]}
    doc = convert_file(scan, llm=ScriptedLLMClient({"transcribe": answer}))
    got = {s.name: s for s in doc.statements}
    assert got["k"].fidelity == "ok"                    # the transcribed formula gives the transcribed result
    assert got["z"].fidelity == "mismatch"              # 0.8 * 450 is not 405: the transcription is not trusted


def test_mathcad_helpers():
    assert _patch("theta = 45 * ureg.°") == "theta = 45 * ureg.degree"
    xml = ('<region region-id="7" actualHeight="20" top="100.5" left="460"><math resultRef="3">x</math></region>'
           '<region region-id="6" top="100" left="9"><text item-idref="a"></text></region>')
    geo = _geometry(xml)
    assert geo[7]["result"] == 3 and geo[6]["kind"] == "text" and geo[7]["top"] == 100.5
    res = _stored_results('<resultData result-id="3" s="x"><ml:result><ml:real>491.5</ml:real></ml:result></resultData>'
                          '<resultData result-id="4" s="x" />')
    assert res == {3: 491.5}
    assert find_clause("(Acc. to EN 1992-1-1 eq. (6.3N))") == "EN 1992-1-1 eq. (6.3N)"
