"""The whole chain on a synthetic inbox: sources in, usable objects out."""
import csv
import json
import shutil
import subprocess
import sys

import pytest

from ckb import expr as X
from ckb.kb.objects import ResolveError
from ckb.use import excel_bridge, toolschema
from ckb.use import report as R
from ckb.use.calc import parse_assignments, run
from ckb.use.prompt import ask
from ckb.use.style import Style
from ckb.use.webapp import render

PRIMARY = dict(gamma_C=1.5, d=450.0, A_sl=942.0, b_w=300.0, f_ck=30.0, k_1=0.15, sigma_cp=0.0)
CODE_V_RD_C = "max((C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d, V_Rd_c_min)"


def test_curation_drops_duplicates_and_reports_what_it_skipped(built):
    assert [d.kind for d in built.docs] == ["python", "excel"]
    reasons = {s["file"]: s["reason"] for s in built.skipped}
    assert "identical copy" in reasons["beam_check_copy.py"] and "not a calculation" in reasons["notes.txt"]


def test_objects_are_the_code_expressions_and_the_sources_are_evidence(kb):
    o = kb.objects["V_Rd_c"]
    assert X.same(o.tree, X.parse(CODE_V_RD_C)) and o.basis == "code"
    # no source writes the complete expression; each is a simplification of it
    assert {v["relation"] for v in o.evidence["variants"]} == {"simplified"} and o.evidence["sources"] == 2
    assert o.confidence["level"] == "high" and o.reference["status"] == "agrees" and o.reference["samples"] == 200
    assert o.topic_path[-1].startswith("6.2.2")
    # objects carry the full expression even where every source simplifies it
    assert X.same(kb.objects["f_cd"].tree, X.parse("alpha_cc * f_ck / gamma_C"))
    # the lever arm 0.9 d of the shear sheet is the shear lever arm z_V, not the bending z
    assert X.same(kb.objects["z"].tree, X.parse("d - lam * x / 2"))
    assert kb.objects["z_V"].evidence["variants"][0]["relation"] == "as code"


def test_benchmarks_explain_each_simplification(kb):
    o = kb.objects["V_Rd_c"]
    b = o.benchmarks
    assert b["total"] == 4 and b["agree"] + b["deviation"] == 4 and b["deviation"] >= 1
    dev = [i for i in b["items"] if i["status"] == "deviation"]
    assert all("lower bound" in i["detail"] and "safe side" in i["detail"] for i in dev)
    assert any("lower bound" in p for p in o.evidence["practice"])
    # the minimum without the axial-stress term is wrong where σcp is not zero
    m = kb.objects["V_Rd_c_min"].benchmarks["items"]
    assert any("leaves out" in (i.get("detail") or "") for i in m if i["status"] == "deviation")


def test_a_second_code_shares_objects(kb):
    codes = {c["code"]: c for c in kb.codes}
    assert codes["EN 1994-1-1"]["fixed"] == {"alpha_cc": 1.0}
    n = kb.objects["N_pl_Rd"]
    assert n.fixed == {"alpha_cc": 1.0} and "alpha_cc" not in kb.plan("N_pl_Rd")[1]
    assert "f_sd" not in kb.objects and "f_yd" in n.params
    assert any(r["code"] == "EN 1994-1-1" for r in kb.objects["f_cd"].refs)
    vals = dict(A_a=10000.0, f_y=355.0, gamma_M0=1.0, A_c=200000.0, f_ck=30.0, gamma_C=1.5, A_s=3000.0,
                f_yk=500.0, gamma_S=1.15)
    value, _ = kb.evaluate("N_pl_Rd", vals)
    assert value == pytest.approx(10000 * 355 + 0.85 * 200000 * 20 + 3000 * 500 / 1.15)


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
    checks = kb.checks_for("V_Rd_c", {**PRIMARY, "sigma_cp": 9.0})
    assert [c["status"] for c in checks] == ["violated"]          # σ_cp > 0.2 f_cd


def test_code_blocks_hold_design_logic_only(built, kb):
    from ckb.kb.codegen import module_source
    text = module_source(kb, kb.objects["V_Rd_c"])
    assert f"# ckb V_Rd_c {kb.objects['V_Rd_c'].version}" in text
    for word in ("source", "benchmark", "consensus", "reproduced", "S1", "S2"):
        assert word not in text
    sys.path.insert(0, str(built.root / "knowledge_base" / "python"))
    try:
        import ckb_objects
        assert ckb_objects.V_Rd_c_chain(**PRIMARY) == pytest.approx(kb.evaluate("V_Rd_c", PRIMARY)[0], rel=1e-12)
        assert ckb_objects.k(450.0) == pytest.approx(1.6667, rel=1e-4)
    finally:
        sys.path.pop(0)


def test_calculation_text_and_units(kb):
    values, given = parse_assignments(kb, "V_Rd_c", ["d=0.45 m", "f_ck=30", "b_w=300", "A_sl=942", "γ_C=1.5",
                                                      "k_1=0.15", "σcp=0"])
    res = run(kb, "V_Rd_c", values, given, check_value=60e3)
    assert res.shown == pytest.approx(74.412, rel=1e-4) and res.unit == "kN"
    assert res.check["utilisation"] == pytest.approx(0.806, rel=1e-3) and res.check["ok"]
    text = R.render_text(kb, res)
    assert "V_Rd,c = max(" in text and "= 74.41 kN" in text and "cl. 6.2.2(1), expr. (6.2.a)" in text
    # number style: decimals and display units, the logic untouched
    res3 = run(kb, "V_Rd_c", values, given, style=Style(decimals=3, units={"V_Rd_c": "N"}))
    assert res3.unit == "N" and res3.style.fmt(res3.shown).startswith("74412.04")
    with pytest.raises(ValueError):
        parse_assignments(kb, "V_Rd_c", ["d=450 kN"])        # wrong kind of unit
    asked = iter(["", "500", "", "", "", "", "", ""])
    out = []
    res2 = ask(kb, "V_Rd_c", read=lambda _: next(asked), write=out.append)
    assert res2.shown != res.shown and any("V_Rd,c" in str(line) for line in out)


def test_report_is_printed_from_the_object_tree_without_history(kb):
    t = R.quick_template("V_Rd_c", PRIMARY, kb, check=60e3)
    page = R.render(kb, t)
    o = kb.objects["V_Rd_c"]
    assert X.to_mathml(o.tree, kb.ml) in page                 # the equation is the object's own tree
    assert f"ckb V_Rd_c {o.version}" in page and "74.41" in page and "NOT OK" not in page
    for word in ("source", "reproduced", "benchmark", "consensus", "range"):
        assert word not in page.lower()                         # no evidence, no sliders


def test_report_template_over_many_cases(kb, tmp_path):
    rows = [{"case": "A", "d": 273, "A_sl": 1340, "V_Ed": 150}, {"case": "B", "d": 259, "A_sl": 754, "V_Ed": 140},
            {"case": "C", "d": 450, "A_sl": 2513, "V_Ed": 230}]
    with open(tmp_path / "cases.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["case", "d [mm]", "A_sl", "V_Ed"])
        w.writeheader()
        for r in rows:
            w.writerow({"case": r["case"], "d [mm]": r["d"], "A_sl": r["A_sl"], "V_Ed": r["V_Ed"]})
    template = {"title": "Slab strips", "defaults": {"f_ck": 35, "b_w": 1000},
                "style": {"decimals": 1, "units": {"V_Rd_c": "kN"}}, "cases": {"file": "cases.csv"},
                "blocks": [{"calc": "V_Rd_c", "case": "governing", "show": ["equation", "result"],
                            "remarks": {"d": "from drawing 12"}},
                           {"table": "V_Rd_c", "columns": ["case", "d", "V_Rd_c", "V_Ed", "utilisation", "verdict"],
                            "sort": "utilisation desc"},
                           {"chart": "V_Rd_c", "x": "d", "range": [150, 600]}]}
    cases = R.build_cases(kb, "V_Rd_c", R._rows_from_file(tmp_path / "cases.csv"), template["defaults"])
    gov = R.governing(cases, kb, "V_Rd_c")
    assert gov.name == max(cases, key=lambda c: c.result.check["utilisation"]).name
    page, used = R.render(kb, template, tmp_path, with_objects=True)
    assert "Case: " + gov.name + " (governing)" in page and 'class="gov"' in page and "<svg" in page
    assert "from drawing 12" in page and "V_Rd_c" in used
    assert page.count('class="eq"') == len(kb.plan("V_Rd_c")[0])      # equations, no substituted lines


def test_web_calculator_gives_the_same_numbers(kb, tmp_path):
    page = render(kb)
    assert page.count("function (e)") >= len(kb.objects) and "<title>Calculation Knowledge Base</title>" in page
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    start, end = page.index("const F = {"), page.index("const STANDALONE")
    script = page[start:end] + "\nconst e = " + json.dumps(PRIMARY) + ";\n" + \
        "for (const s of " + json.dumps(kb.plan("V_Rd_c")[0]) + ") e[s] = F[s](e);\nconsole.log(e.V_Rd_c);"
    (tmp_path / "t.js").write_text(script, encoding="utf-8")
    got = float(subprocess.run([node, str(tmp_path / "t.js")], capture_output=True, text=True).stdout)
    assert got == pytest.approx(kb.evaluate("V_Rd_c", PRIMARY)[0], rel=1e-12)


def test_excel_calculator_round_trip(built, kb, tmp_path):
    from openpyxl import load_workbook
    from ckb.convert import convert_file
    from ckb.kb.search import classify
    path = excel_bridge.export_calculator(kb, "V_Rd_c", tmp_path / "calc.xlsx", PRIMARY)
    wb = load_workbook(path)
    assert "d" in wb.defined_names and "V_Rd_c" in wb.defined_names            # named ranges
    rec = excel_bridge.read_calculator(path)
    assert rec["object"] == "V_Rd_c" and not rec["changed_formulas"] and rec["inputs"]["d"] == 450
    formula = wb["Calculation"][json.loads(wb["_ckb"]["B1"].value)["cells"]["rho_l"]].value
    assert "A_sl" in formula and "$" not in formula                          # =MIN(A_sl/(b_w*d),0.02)
    check = excel_bridge.verify(kb, path)
    assert check["same_version"] and not check["edited"]
    if check.get("rows"):                                                    # LibreOffice installed
        assert check["ok"] and len(check["rows"]) == 6
    res = classify(convert_file(path), kb, built.tax)
    assert res["summary"].get("as code", 0) >= 5 and "differs" not in res["summary"]
    # an engineer edits a formula: the change is recognised
    ws = wb["Calculation"]
    cell = json.loads(wb["_ckb"]["B1"].value)["cells"]["rho_l"]
    ws[cell] = ws[cell].value.replace("0.02", "0.04")
    wb.save(tmp_path / "edited.xlsx")
    assert list(excel_bridge.read_calculator(tmp_path / "edited.xlsx")["changed_formulas"]) == ["rho_l"]
    assert not excel_bridge.verify(kb, tmp_path / "edited.xlsx")["ok"]
    # a report straight from the workbook's inputs
    rows = R.cases_from_calculator(kb, path)
    assert rows[0]["d [mm]"] == 450


def test_mathcad_worksheet_round_trip(kb, tmp_path):
    from ckb.use.mathcad_export import export_worksheet, verify
    path = export_worksheet(kb, "V_Rd_c", tmp_path / "calc.mcdx", PRIMARY)
    res = verify(kb, path)
    assert res["ok"] and res["same_version"] and all(r["agree"] for r in res["rows"])


def test_verify_tells_whether_a_file_is_the_same_logic(built, kb, tmp_path):
    from ckb.use.verify import verify
    block = built.root / "knowledge_base" / "python" / "ckb_objects" / "V_Rd_c.py"
    assert verify(kb, block)["ok"]
    page = tmp_path / "r.html"
    page.write_text(R.render(kb, R.quick_template("V_Rd_c", PRIMARY, kb)), encoding="utf-8")
    assert verify(kb, page)["ok"]
    page.write_text(page.read_text(encoding="utf-8").replace(kb.objects["k"].version, "0" * 12), encoding="utf-8")
    assert not verify(kb, page)["ok"]


def test_search_tools_and_health(built, kb):
    from ckb.kb.search import search
    from ckb.maintain.health import check
    assert search(kb, built.tax, "VRd.c")[0][1] == "V_Rd_c"
    assert "V_Rd_c" in [h[1] for h in search(kb, built.tax, "concrete shear")]
    assert search(kb, built.tax, "crack width")[0][1] == "w_k"
    assert {"N_pl_Rd", "N_b_Rd_c"} <= {h[1] for h in search(kb, built.tax, "composite column")[:4]}
    assert search(kb, built.tax, "punching")[0][1] in kb.objects and "v_Rd_c_p" in [h[1] for h in search(kb, built.tax, "punching")]
    tools = toolschema.definitions(kb)
    tool = next(t for t in tools if t["name"] == "calc_V_Rd_c")
    assert set(tool["input_schema"]["required"]) == {"d", "A_sl", "b_w", "f_ck", "sigma_cp"}   # coefficients optional
    out = toolschema.call(kb, "calc_V_Rd_c", dict(PRIMARY))
    assert out["result"]["value"] == pytest.approx(74.412, rel=1e-4) and len(out["steps"]) == 6
    assert out["conditions"][0]["status"] == "ok" and out["version"] == kb.objects["V_Rd_c"].version
    assert "error" in toolschema.call(kb, "calc_V_Rd_c", {"nonsense": 1})
    health = check(kb, built.root / "knowledge_base")
    assert health["problems"] == 0 and health["healthy"] == len(kb.objects)
    # an edit without a new version is caught
    kb.objects["k"].formula = "min(1 + sqrt(210 / d), 2)"
    kb.objects["k"]._tree = None
    bad = check(kb, built.root / "knowledge_base")
    assert bad["problems"] >= 1 and any("version" in p for r in bad["rows"] for p in r["problems"])
    kb.objects["k"].formula = "min(1 + sqrt(200 / d), 2)"
    kb.objects["k"]._tree = None


def test_command_line(built, tmp_path):
    from ckb.cli import ROOT
    base = [sys.executable, "-m", "ckb", "--kb", str(built.root / "knowledge_base"),
            "--workspace", str(built.root / "workspace")]

    def ckb(*args):
        return subprocess.run(base + list(args), capture_output=True, text=True, cwd=ROOT)
    out = ckb("list")
    assert out.returncode == 0 and "V_Rd_c" in out.stdout and "EN 1994-1-1" in out.stdout
    out = ckb("run", "VRd.c", "d=450", "f_ck=30", "b_w=300", "A_sl=942", "sigma_cp=0", "--check", "60")
    assert "= 74.41 kN" in out.stdout and "0.81" in out.stdout
    out = ckb("search", "concrete", "shear")
    assert "V_Rd_c" in out.stdout
    out = ckb("report", "V_Rd_c", "d=450", "b_w=300", "A_sl=942", "--check", "60", "-o", str(tmp_path / "r.html"))
    assert out.returncode == 0 and (tmp_path / "r.html").exists()
    out = ckb("verify", str(tmp_path / "r.html"))
    assert out.returncode == 0 and "same logic" in out.stdout
    out = ckb("report-template", "V_Rd_c", "-o", str(tmp_path / "t.yaml"))
    out = ckb("report", "--template", str(tmp_path / "t.yaml"), "-o", str(tmp_path / "t.html"))
    assert out.returncode == 0, out.stderr
    out = ckb("run", "nothing_like_this")
    assert out.returncode != 0 and "No calculation object" in out.stderr


def test_practice_context_reaches_the_object(kb):
    # the spreadsheet fixture works per metre width: that becomes context on the object and its b_w input
    notes = [b for b in kb.objects["V_Rd_c"].background if b["kind"] == "practice"]
    assert notes and notes[0]["about"] == "b_w" and "per metre" in notes[0]["text"]


def test_word_report_with_native_equations(kb, tmp_path):
    from ckb.use.report_docx import render_docx
    t = R.quick_template("V_Rd_c", PRIMARY, kb, check=60e3)
    t["blocks"].append({"table": "V_Rd_c"})
    path = render_docx(kb, t, tmp_path / "r.docx")
    import zipfile
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    assert xml.count("<m:oMath") > 10 and "<m:f>" in xml and "<m:rad>" in xml       # fractions, roots
    assert "Heading" in xml or "w:pStyle" in xml
    pandoc = shutil.which("pandoc")
    if pandoc:                                                                          # read the equations back
        md = subprocess.run([pandoc, str(path), "-t", "markdown"], capture_output=True, text=True).stdout
        assert "\\frac" in md and "\\sqrt" in md


def test_pdf_report_has_bookmarks(kb, tmp_path):
    if not R.find_browser():
        pytest.skip("no Chromium-based browser")
    from pypdf import PdfReader
    t = R.quick_template("V_Rd_c", PRIMARY, kb, check=60e3)
    t["blocks"].insert(0, {"heading": "Shear check"})
    html_path = tmp_path / "r.html"
    html_path.write_text(R.render(kb, t), encoding="utf-8")
    assert R.to_pdf(html_path, tmp_path / "r.pdf")
    titles = []

    def walk(items):
        for it in items:
            walk(it) if isinstance(it, list) else titles.append(it.title)
    walk(PdfReader(str(tmp_path / "r.pdf")).outline)
    assert "Shear check" in titles and any("V_Rd,c" in t for t in titles)


def test_excel_form_is_a_report_template(kb, tmp_path):
    from ckb.use.report_form import read_form, write_form
    path = write_form(kb, "V_Rd_c", tmp_path / "form.xlsx")
    t = read_form(path)
    assert [list(b)[0] for b in t["blocks"]] == ["heading", "calc", "table", "chart"]
    assert len(t["cases"]) == 3 and "V_Ed [kN]" in t["cases"][0] and t["defaults"]["gamma_C"] == 1.5
    page = R.render(kb, t)
    assert 'class="gov"' in page and "<svg" in page


def test_excel_calculator_with_cell_references(kb, tmp_path):
    from openpyxl import load_workbook
    path = excel_bridge.export_calculator(kb, "V_Rd_c", tmp_path / "c.xlsx", PRIMARY, refs="cells")
    wb = load_workbook(path)
    cell = json.loads(wb["_ckb"]["B1"].value)["cells"]["rho_l"]
    assert wb["Calculation"][cell].value.startswith("=MIN(C") and excel_bridge.verify(kb, path)["same_version"]


def test_latex_and_word_printers(kb):
    from ckb.notation import latex
    o = kb.objects["k"]
    assert X.to_latex(o.tree, kb.tex) == "\\min\\left(1 + \\sqrt{\\frac{200}{d}}, 2\\right)"
    assert latex("V_Rd_c", "V_{Rd,c}") == "V_{\\mathrm{Rd,c}}"
    assert "<m:sSub>" in kb.omml("V_Rd_c") and "<m:func>" in X.to_omml(o.tree, kb.omml)


def test_web_calculator_carries_the_excel_and_mathcad_files(kb, tmp_path):
    import base64
    from ckb.use import share
    from ckb.use.mathcad_export import verify as verify_mcdx
    files = share.calculator_files(kb, log=lambda *_: None)
    entry = files["V_Rd_c"]
    (tmp_path / "c.xlsx").write_bytes(base64.b64decode(entry["xlsx"]))
    (tmp_path / "c.mcdx").write_bytes(base64.b64decode(entry["mcdx"]))
    check = excel_bridge.verify(kb, tmp_path / "c.xlsx")
    assert check["same_version"] and not check["edited"]
    assert verify_mcdx(kb, tmp_path / "c.mcdx")["same_version"]
    assert {"d", "A_sl", "V_Rd_c"} <= set(entry["cells"]) and entry["check"].startswith("C")
    page = render(kb, files={"V_Rd_c": entry})
    assert 'id="dl-xlsx"' in page and 'id="dl-mcdx"' in page and entry["xlsx"][:200] in page
