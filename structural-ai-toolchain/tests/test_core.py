"""Expression engine, units and notation."""
import math

import pytest

from ckb import expr as X
from ckb import units as U
from ckb.notation import ident, pretty, split_label, symkey
from ckb.convert.excel_formula import parse_formula

VRDC = "max((C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d, V_Rd_c_min)"
ENV = dict(C_Rd_c=0.12, k=1.6667, rho_l=0.00698, f_ck=30, k_1=0.15, sigma_cp=0.2, b_w=300, d=450, V_Rd_c_min=55000)


def test_one_tree_prints_to_every_target_consistently():
    tree = X.parse(VRDC)
    value = X.evaluate(tree, ENV)
    assert value == pytest.approx(78474.4, rel=1e-4)
    # Python text parses back to the same tree
    assert X.same(X.parse(X.to_python(tree)), tree)
    # the Excel formula, read by the Excel parser, is the same formula
    cells = {s: f"A{i}" for i, s in enumerate(X.symbols(tree), 1)}
    back = parse_formula("=" + X.to_excel(tree, cells.get), lambda sh, c: X.Sym({v: k for k, v in cells.items()}[c]))
    assert X.evaluate(back, ENV) == pytest.approx(value, rel=1e-12)
    assert "Math.max" in X.to_js(tree) and "<mfrac>" in X.to_mathml(X.parse("a / b"), lambda s: f"<mi>{s}</mi>")
    assert X.from_json(X.to_json(tree)) == tree


def test_excel_keeps_its_own_operator_rules():
    ref = lambda sh, c: X.Sym(c)                                       # noqa: E731
    assert X.evaluate(parse_formula("=-2^2", ref), {}) == 4            # unary minus binds first
    assert X.evaluate(parse_formula("=2^3^2", ref), {}) == 64          # ^ associates to the left
    assert X.evaluate(parse_formula("=50%+SUM(A1:A2,1)", ref), {"A1": 1, "A2": 2}) == 4.5
    assert X.evaluate(parse_formula('=IF(A1="N",1,2)', ref), {"A1": "n"}) == 1
    with pytest.raises(X.ExprError):
        parse_formula("=VLOOKUP(A1,B1:C9,2)", ref)


def test_unit_literals_and_conversion_factors_disappear():
    factor = lambda u: (U.parse_unit(u).factor, U.parse_unit(u).text)   # noqa: E731
    k = X.fold(X.strip_units(X.parse("min(1 + sqrt(200 * ureg.mm / d), 2)"), factor))
    assert X.to_python(k) == "min(1 + sqrt(200 / d), 2)"
    assert "200 mm" in X.to_text(k)                                    # the literal remembers its unit
    load = X.fold(X.strip_units(X.parse("1.7 * (ureg.kN / ureg.m**2) * W"), factor))
    assert X.evaluate(load, {"W": 1000}) == pytest.approx(1.7)         # N/mm
    assert X.to_python(X.fold(X.parse("(a + b) * 1000 * d / 1000"))) == "(a + b) * d"
    assert X.to_python(X.fold(X.parse("1 / 12 * b * h ** 3"))) == "1 / 12 * b * h ** 3"   # untouched


def test_formulas_typed_differently_have_the_same_key():
    assert X.same(X.parse("a * b * sqrt(c)"), X.parse("c ** 0.5 * b * a"))
    assert X.same(X.parse("k ** 1.5"), X.parse("k ** (3 / 2)"))
    assert not X.same(X.parse("a - b"), X.parse("b - a"))


def test_units():
    assert U.parse_unit("kN/m").factor == 1 and U.parse_unit("mm2/m").factor == pytest.approx(1e-3)
    assert U.parse_unit("Mpa").text == "MPa" and U.parse_unit("kNm").factor == 1e6
    assert U.parse_unit("deg").factor == pytest.approx(math.pi / 180)
    assert not U.is_unit("k") and not U.is_unit("tensile") and U.is_unit("KN")
    assert U.fmt(157082.4) == "157082" and U.fmt(0.0079898) == "0.0079898" and U.fmt(1.63789) == "1.6379"


def test_notation():
    assert symkey("VRd.c") == symkey("V_Rd,c") == symkey("V_Rd.c") == "VRdc"
    assert ident("Δε_sm.cm") == "Deltaeps_sm_cm" and pretty("V_Rd_c_min") == "V_Rd,c,min"
    assert split_label("VRd.c (kN/m)") == ("VRd.c", "kN/m", "")
    assert split_label("VEd (kN) - crane only") == ("VEd", "kN", "crane only")
    assert split_label("fcd (αcc = 1)")[0] == "fcd"
