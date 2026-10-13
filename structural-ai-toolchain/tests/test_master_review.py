"""Master reviewer: catch results that look right but are wrong (units),
plus unresolved values; and the units engine."""

import pytest

from src.models.calculation import CalcSheet
from src.qa import deterministic_review, review, review_to_convergence
from src.qa import units as U


# ------------------------------------------------------------- units engine
def test_unit_parsing_and_scale():
    assert U.scale_of("mm") == 1.0
    assert U.scale_of("m") == 1000.0
    assert U.scale_of("kN") == 1000.0
    assert U.scale_of("MPa") == 1.0
    assert U.scale_of("GPa") == 1000.0
    assert U.dim_of("MPa") == (1, -2)
    assert U.known("kNm") and not U.known("furlong")


def test_nearest_power_of_ten():
    assert U.nearest_power_of_ten(0.001) == pytest.approx(0.001)
    assert U.nearest_power_of_ten(1000) == pytest.approx(1000)
    assert U.nearest_power_of_ten(1.0) == pytest.approx(1.0)
    assert U.nearest_power_of_ten(3.3) is None   # not a clean factor


# --------------------------------------------------------- the wrong-units bug
def test_reviewer_catches_units_scale_slip():
    # the real error class: a force in N shown as kN
    s = CalcSheet(title="Stud")
    s.define("f_uk", 450, unit="MPa")
    s.define("phi", 19, unit="mm")
    s.define("gamma", 1.25, unit="-")
    s.calc("P_Rd", "0.8*f_uk*pi*phi**2/4/gamma", unit="kN")  # WRONG: it's N
    findings = deterministic_review(s)
    codes = {f.code for f in findings}
    assert "unit-scale-mismatch" in codes
    bad = next(f for f in findings if f.code == "unit-scale-mismatch")
    assert "81.66" in bad.message          # corrected value surfaced
    assert bad.severity == "error"


def test_reviewer_passes_consistent_sheet():
    s = CalcSheet(title="OK")
    s.define("b", 300, unit="mm")
    s.define("h", 500, unit="mm")
    s.define("lim", 12, unit="MPa")
    s.define("M", 45, unit="kNm")
    s.calc("W", "b*h**2/6", unit="mm^3")
    s.calc("sigma", "M*1e6/W", unit="MPa")
    s.check("sigma <= lim")
    rep = review(s)
    assert rep.passed()
    assert str(rep).startswith("✔")


def test_magic_number_carrying_a_hidden_unit_is_reported():
    s = CalcSheet(title="Magic")
    s.define("b", 300, unit="mm")
    s.define("h", 500, unit="mm")
    s.calc("W", "b*h**2/6", unit="mm^3")
    s.calc("sigma", "45e6/W", unit="MPa")   # 45e6 is a moment in Nmm
    f = next(f for f in deterministic_review(s)
             if f.code == "hidden-unit-literal")
    assert f.severity == "warning" and "moment" in f.message


def test_reviewer_flags_unresolved_result():
    # a derived that ended up non-finite (upstream unresolved) is flagged
    s = CalcSheet(title="Bad")
    s.define("a", 1, unit="mm")
    s.define("b", 5, unit="mm")
    s.calc("r", "b/a", unit="mm")
    # simulate an unresolved upstream leaving r non-finite
    for it in s.items:
        if it.name == "r":
            it.value = float("nan")
    s.values["r"] = float("nan")
    findings = deterministic_review(s)
    assert any(f.code == "unresolved-result" for f in findings)


def test_division_by_zero_is_flagged_not_crashed():
    from src.models.calculation import CalcSheetError

    s = CalcSheet(title="DivZero")
    s.define("a", 0, unit="mm")
    s.define("b", 5, unit="mm")
    with pytest.raises(CalcSheetError):
        s.calc("r", "b/a", unit="mm")   # graceful, not a TypeError crash


def test_unit_aware_evaluation_produces_correct_display():
    # the real bug class: MPa·mm² gives N, must display as kN correctly
    s = CalcSheet(title="Stud", unit_aware=True)
    s.define("f_uk", 450, unit="MPa")
    s.define("phi", 19, unit="mm")
    s.define("gamma", 1.25, unit="-")
    step = s.calc("P_Rd", "0.8*f_uk*pi*phi**2/4/gamma", unit="kN")
    # displayed value is in kN (81.66), NOT the raw N number (81656)
    assert step.value == pytest.approx(81.66, abs=0.1)
    # internal canonical value stays in N for downstream consistency
    assert s.canonical_results()["P_Rd"] == pytest.approx(81656, rel=1e-3)
    # and the reviewer is clean (no false unit flag on a correct sheet)
    assert review(s).passed()


def test_unit_aware_area_converts_mm2_to_cm2():
    s = CalcSheet(title="Area", unit_aware=True)
    s.define("D", 1420, unit="mm")
    s.calc("A", "pi*D**2/4", unit="cm2")
    # pi*1420^2/4 = 1.583e6 mm^2 = 15833 cm^2
    assert s.results()["A"] == pytest.approx(15833, rel=1e-3)


def test_unit_naive_sheet_unchanged():
    # default sheets (Excel with baked-in conversions) must be untouched
    s = CalcSheet(title="Crack")  # unit_aware defaults False
    s.define("M_qp", 45, unit="kNm")
    s.define("z", 243.2, unit="mm")
    s.define("A_s", 1005, unit="mm^2")
    step = s.calc("sigma_s", "M_qp*1000000/(z*A_s)", unit="MPa")
    assert step.value == pytest.approx(184.1, abs=0.5)  # manual conv. intact


def test_review_report_and_convergence_smoke():
    from src.qa import review_to_convergence

    def build():
        s = CalcSheet(title="Conv")
        s.define("f_uk", 450, unit="MPa")
        s.define("phi", 19, unit="mm")
        s.calc("P", "f_uk*phi**2", unit="kN")  # wrong units
        return s

    sheet, rep = review_to_convergence(build, render_dir=None, max_iter=4)
    # the slip is FIXED, not just flagged, and the fix is on record
    assert rep.passed() and rep.converged
    assert sheet.results()["P"] == pytest.approx(162.45)
    assert rep.fixes and rep.fixes[0].action == "convert"
    assert sheet.review_log[0]["name"] == "P"
    step = next(i for i in sheet.calcs() if i.name == "P")
    assert "Reviewer correction" in step.note


# ------------------------------------------------------ dimensional analysis
def test_dimension_mismatch_in_unit_aware_sheet():
    s = CalcSheet(title="Dims", unit_aware=True)
    s.define("F", 100, unit="kN")
    s.define("A", 2000, unit="mm2")
    s.calc("sigma", "F/A", unit="kN")       # a stress labelled as a force
    f = next(f for f in deterministic_review(s)
             if f.code == "dimension-mismatch")
    assert f.severity == "error" and "stress" in f.message


def test_empirical_code_formula_is_recognised_not_flagged():
    s = CalcSheet(title="EC2 k", unit_aware=True)
    s.define("d", 450, unit="mm")
    s.calc("k", "min(1 + sqrt(200/d), 2)", unit="-")
    codes = {f.code: f.severity for f in deterministic_review(s)}
    assert codes.get("empirical-formula") == "info"
    assert review(s).passed()


def test_check_comparing_force_with_length_is_an_error():
    s = CalcSheet(title="Bad check", unit_aware=True)
    s.define("F", 10, unit="kN")
    s.define("L", 10, unit="m")
    s.check("F <= L")
    assert any(f.code == "check-dimension-mismatch"
               for f in deterministic_review(s))


# ------------------------------------------ verdicts flip when units honoured
def _stud_naive():
    s = CalcSheet(title="Stud (naive)")
    s.define("f_u", 450, unit="MPa")
    s.define("d", 19, unit="mm")
    s.define("gamma_V", 1.25, unit="-")
    s.define("P_Ed", 87.97, unit="kN")
    s.calc("P_Rd", "0.8*f_u*pi*d**2/4/gamma_V", unit="kN")   # really N
    s.check("P_Ed <= P_Rd")
    return s


def test_units_slip_that_flips_a_verdict_is_caught_and_fixed():
    s = _stud_naive()
    assert s.all_passed()                      # wrong: 87.97 <= 81656
    codes = {f.code for f in deterministic_review(s)}
    assert "unit-scale-mismatch" in codes
    # merely relabelling P_Rd as N makes the check compare kN with N:
    relabelled = s.replay(lambda it: (setattr(it, "unit", "N") or it)
                          if it.name == "P_Rd" else it)
    assert "check-verdict-units" in {
        f.code for f in deterministic_review(relabelled)}
    fixed, rep = review_to_convergence(s)
    assert rep.passed()
    # relabelling P_Rd as N would leave the verdict wrong; the reviewer
    # must pick the conversion that keeps the whole sheet consistent
    assert fixed.results()["P_Rd"] == pytest.approx(81.66, abs=0.01)
    assert fixed.all_passed() is False         # 87.97 kN > 81.66 kN


# ------------------------------------------------- one-to-one correspondence
def test_correspondence_with_original_values():
    s = CalcSheet(title="Stud", unit_aware=True)
    s.define("f_u", 450, unit="MPa")
    s.define("d", 19, unit="mm")
    s.define("gamma_V", 1.25, unit="-")
    s.calc("P_Rd", "0.8*f_u*pi*d**2/4/gamma_V", unit="kN")
    # printed precision is honoured: "81.66" agrees, "81.7 kN" agrees too
    assert review(s, original_values={"P_Rd": {"value": 81.66, "unit": "kN",
                                               "shown": "81.66"}}).passed()
    assert review(s, original_values={"P_Rd": ("81.7", "kN")}).passed()
    # a value that does not match is an error
    bad = review(s, original_values={"P_Rd": (73.5, "kN")})
    assert any(f.code == "correspondence-mismatch" for f in bad.errors())
    # the ORIGINAL showing 81656 'kN' is recognised as the original's slip
    slip = review(s, original_values={"P_Rd": (81656.3, "kN")})
    assert slip.passed()
    assert any(f.code == "original-units-slip" for f in slip.findings)


# ------------------------------------------------------- AI corrections
def test_ai_corrections_are_verified_before_being_applied():
    from src.llm import ScriptedLLMClient

    s = CalcSheet(title="Stud", unit_aware=True)
    s.define("f_u", 450, unit="MPa")
    s.define("d", 16, unit="mm")              # transcription error: was 19
    s.define("gamma_V", 1.25, unit="-")
    s.calc("P_Rd", "0.8*f_u*pi*d**2/4/gamma_V", unit="kN")
    original = {"P_Rd": (81.66, "kN")}

    def correction(name, value):
        return {"name": name, "issue": "value", "original": "19 mm",
                "produced": "16 mm", "proposed_expression": "",
                "proposed_unit": "", "proposed_value": value}

    good = ScriptedLLMClient({"review": {
        "verdict": "REWORK", "findings": [],
        "corrections": [correction("d", 19)]}})
    fixed, rep = review_to_convergence(s, client=good,
                                       original_values=original, max_iter=3)
    assert fixed.results()["P_Rd"] == pytest.approx(81.66, abs=0.01)
    assert any(f.source == "ai" for f in rep.fixes)

    wrong = ScriptedLLMClient({"review": {
        "verdict": "REWORK", "findings": [],
        "corrections": [correction("d", 12)]}})      # makes it worse
    kept, rep2 = review_to_convergence(s, client=wrong,
                                       original_values=original, max_iter=3)
    assert kept.results()["d"] == 16           # rejected: not applied
    assert not rep2.fixes and not rep2.passed()
