"""Master reviewer: catch results that look right but are wrong (units),
plus unresolved values; and the units engine."""

import pytest

from src.models.calculation import CalcSheet
from src.qa import deterministic_review, review
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
    s.calc("W", "b*h**2/6", unit="mm^3")
    s.calc("sigma", "45e6/W", unit="MPa")
    s.check("sigma <= lim")
    rep = review(s)
    assert rep.passed()
    assert str(rep).startswith("✔")


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


def test_review_report_and_convergence_smoke():
    from src.qa import review_to_convergence

    def build():
        s = CalcSheet(title="Conv")
        s.define("f_uk", 450, unit="MPa")
        s.define("phi", 19, unit="mm")
        s.calc("P", "f_uk*phi**2", unit="kN")  # wrong units
        return s

    sheet, rep = review_to_convergence(build, render_dir=None, max_iter=2)
    # unit slip is surfaced (auto-fix intentionally deferred to human)
    assert not rep.passed()
