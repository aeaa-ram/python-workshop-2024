"""The whole chain on a synthetic inbox: sources in, usable objects out."""
import json
import shutil
import subprocess
import sys

import pytest

from ckb import expr as X
from ckb.kb.objects import ResolveError
from ckb.use import excel_bridge, toolschema
from ckb.use.calc import parse_assignments, run, starting_values
from ckb.use.prompt import ask
from ckb.use.report import render_html, render_text
from ckb.use.webapp import render

PRIMARY = dict(gamma_C=1.5, d=450.0, A_sl=942.0, b_w=300.0, f_ck=30.0, k_1=0.15, sigma_cp=0.0)


def test_curation_drops_duplicates_and_reports_what_it_skipped(built):
    assert [d.kind for d in built.docs] == ["python", "excel"]
    reasons = {s["file"]: s["reason"] for s in built.skipped}
    assert "identical copy" in reasons["beam_check_copy.py"] and "not a calculation" in reasons["notes.txt"]


def test_shear_resistance_is_unified_from_spreadsheet_and_script(kb):
    o = kb.objects["V_Rd_c"]
    assert X.same(o.tree, X.parse(
        "max((C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d, V_Rd_c_min)"))
    assert o.status == "unified" and o.support["sources"] == 2 and o.support["variants_merged"] == 3
    assert X.same(kb.objects["V_Rd_c_min"].tree, X.parse("(v_min + k_1 * sigma_cp) * b_w * d"))
    assert kb.objects["k"].status == "consensus"
    assert kb.objects["z"].status == "disagreement"         # 0.9 d against d - λx/2
    assert o.reference["status"] == "agrees" and o.reference["samples"] == 200
    assert o.topic_path[-1].startswith("6.2.2")


def test_benchmarks_expose_a_simplification_in_a_source(kb):
    o = kb.objects["V_Rd_c"]
    b = o.benchmarks
    assert b["total"] == 4 and b["agree"] + b["deviation"] == 4 and b["deviation"] >= 1
    assert any("lower bound" in f for f in o.findings)
    # the minimum without the axial-stress term is wrong where σcp is not zero
    assert any("leaves out" in f for f in kb.objects["V_Rd_c_min"].findings)


def test_dependencies_resolve_to_primary_inputs(kb):
    steps, inputs = kb.plan("V_Rd_c")
    assert steps[-1] == "V_Rd_c" and set(steps) == {"C_Rd_c", "k", "rho_l", "v_min", "V_Rd_c_min", "V_Rd_c"}
    assert set(inputs) == set(PRIMARY)
    value, trace = kb.evaluate("V_Rd_c", PRIMARY)
    assert value == pytest.approx(74412.04, rel=1e-6) and [s.id for s in trace] == steps
    # an intermediate value can be given instead of calculated
    v2, _ = kb.evaluate("V_Rd_c", {**PRIMARY, "k": 2.0}, given=("k",))
    assert v2 > value
    with pytest.raises(ResolveError):
        kb.evaluate("V_Rd_c", {"d": 450.0})


def test_generated_python_matches_the_object(built, kb):
    sys.path.insert(0, str(built.root / "knowledge_base" / "python"))
    try:
        import ckb_objects
        assert ckb_objects.V_Rd_c_chain(**PRIMARY) == pytest.approx(kb.evaluate("V_Rd_c", PRIMARY)[0], rel=1e-12)
        assert ckb_objects.k(450.0) == pytest.approx(1.6667, rel=1e-4)
    finally:
        sys.path.pop(0)


def test_calculation_text_report_and_units(kb):
    values, given = parse_assignments(kb, "V_Rd_c", ["d=0.45 m", "f_ck=30", "b_w=300", "A_sl=942", "γ_C=1.5",
                                                      "k_1=0.15", "σcp=0"])
    res = run(kb, "V_Rd_c", values, given, check_value=60e3)
    assert res.shown == pytest.approx(74.412, rel=1e-4) and res.unit == "kN"
    assert res.check["utilisation"] == pytest.approx(0.806, rel=1e-3) and res.check["ok"]
    text = render_text(kb, res)
    assert "V_Rd,c = max(" in text and "= 74.412 kN" in text and "cl. 6.2.2(1), expr. (6.2.a)" in text
    html = render_html(kb, res, {"project": "Test"})
    assert "<msqrt>" in html and "74.412" in html and "Basis of this calculation" in html
    with pytest.raises(ValueError):
        parse_assignments(kb, "V_Rd_c", ["d=450 kN"])        # wrong kind of unit
    asked = iter(["", "500", "", "", "", "", "", ""])
    out = []
    res2 = ask(kb, "V_Rd_c", read=lambda _: next(asked), write=out.append)
    assert res2.shown != res.shown and any("V_Rd,c" in str(line) for line in out)


def test_web_calculator_gives_the_same_numbers(kb, tmp_path):
    page = render(kb)
    assert page.count("function (e)") == len(kb.objects) and "Calculation Knowledge Base" in page
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    start, end = page.index("const F = {"), page.index("const KB = JSON.parse")
    script = page[start:end] + "\nconst e = " + json.dumps(PRIMARY) + ";\n" + \
        "for (const s of " + json.dumps(kb.plan("V_Rd_c")[0]) + ") e[s] = F[s](e);\nconsole.log(e.V_Rd_c);"
    (tmp_path / "t.js").write_text(script, encoding="utf-8")
    got = float(subprocess.run([node, str(tmp_path / "t.js")], capture_output=True, text=True).stdout)
    assert got == pytest.approx(kb.evaluate("V_Rd_c", PRIMARY)[0], rel=1e-12)


def test_excel_calculator_round_trip(built, kb, tmp_path):
    from ckb.convert import convert_file
    from ckb.kb.search import classify
    path = excel_bridge.export_calculator(kb, "V_Rd_c", tmp_path / "calc.xlsx", PRIMARY)
    rec = excel_bridge.read_calculator(path)
    assert rec["object"] == "V_Rd_c" and not rec["changed_formulas"] and rec["inputs"]["d"] == 450
    check = excel_bridge.verify(kb, "V_Rd_c", path, PRIMARY)
    if check is not None:                                    # LibreOffice installed
        assert check["agree"] and len(check["rows"]) == 6
    doc = convert_file(path)
    res = classify(doc, kb, built.tax)
    assert res["summary"]["existing"] == 6 and "differs" not in res["summary"]
    # an engineer edits a formula: the change is recognised, not just called wrong
    from openpyxl import load_workbook
    wb = load_workbook(path)
    ws = wb["Calculation"]
    cell = rec_cell = json.loads(wb["_ckb"]["B1"].value)["cells"]["rho_l"]
    ws[cell] = ws[cell].value.replace("0.02", "0.04")
    wb.save(tmp_path / "edited.xlsx")
    assert list(excel_bridge.read_calculator(tmp_path / "edited.xlsx")["changed_formulas"]) == ["rho_l"]
    res = classify(convert_file(tmp_path / "edited.xlsx"), kb, built.tax)
    assert res["summary"].get("differs") == 1 and rec_cell


def test_search_tools_and_health(built, kb):
    from ckb.kb.search import search
    from ckb.maintain.health import check
    assert search(kb, built.tax, "VRd.c")[0][1] == "V_Rd_c"
    assert search(kb, built.tax, "shear resistance without shear reinforcement")[0][1] == "V_Rd_c"
    tools = toolschema.definitions(kb)
    tool = next(t for t in tools if t["name"] == "calc_V_Rd_c")
    assert set(tool["input_schema"]["required"]) == set(PRIMARY)
    args = dict(PRIMARY)
    out = toolschema.call(kb, "calc_V_Rd_c", args)
    assert out["result"]["value"] == pytest.approx(74.412, rel=1e-4) and len(out["steps"]) == 6
    assert "error" in toolschema.call(kb, "calc_V_Rd_c", {"nonsense": 1})
    health = check(kb, built.root / "knowledge_base")
    assert health["problems"] == 0 and health["healthy"] == len(kb.objects)
    # an edit without a new version is caught
    kb.objects["k"].formula = "min(1 + sqrt(210 / d), 2)"
    kb.objects["k"]._tree = None
    bad = check(kb, built.root / "knowledge_base")
    assert bad["problems"] >= 1 and any("version" in p for r in bad["rows"] for p in r["problems"])


def test_command_line(built):
    from ckb.cli import ROOT
    base = [sys.executable, "-m", "ckb", "--kb", str(built.root / "knowledge_base"),
            "--workspace", str(built.root / "workspace")]
    out = subprocess.run(base + ["list"], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and "V_Rd_c" in out.stdout
    out = subprocess.run(base + ["run", "VRd.c", "d=450", "f_ck=30", "b_w=300", "A_sl=942", "gamma_C=1.5",
                                 "k_1=0.15", "sigma_cp=0", "--check", "60"], capture_output=True, text=True, cwd=ROOT)
    assert "= 74.412 kN" in out.stdout and "0.81" in out.stdout
    out = subprocess.run(base + ["run", "nothing_like_this"], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode != 0 and "No calculation object" in out.stderr
