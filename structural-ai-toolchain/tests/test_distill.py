"""Stages 3 and 4: recognising quantities and merging variants."""
import pytest

from ckb import expr as X
from ckb.distill.consolidate import Merger, Variant, consolidate, is_special_case
from ckb.distill.decompose import Instance, decompose
from ckb.distill.taxonomy import load
from ckb.convert import convert_file
from conftest import make_excel

tax = load()


def test_the_seed_holds_notation_but_no_formulas():
    import yaml
    from ckb.distill.taxonomy import DATA
    data = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    assert all("formula" not in c and "expr" not in c for c in data["concepts"])
    assert len(tax.concepts) > 50 and tax.concepts["V_Rd_c"].topic == "6.2.2"


def test_a_symbol_is_recognised_however_it_is_spelled():
    for name in ("VRd.c", "V_Rd,c", "V_Rd.c", "VRdc"):
        assert tax.resolve(name).concept.id == "V_Rd_c"
    assert tax.resolve("νmin").concept.id == "v_min" and tax.resolve("γ_Mc").concept.id == "gamma_C"
    assert tax.resolve("perimeter u") is None and tax.resolve("Utilization") is None


def test_context_decides_an_ambiguous_symbol():
    assert tax.resolve("k_1", clause="EN 1992-1-1 cl. 6.2.2(1)").concept.id == "k_1"
    assert tax.resolve("k_1", clause="EN 1992-1-1 cl. 7.3.4").concept.id == "k_1_bond"
    # the same reinforcement area plays a different role in bending and in shear
    assert tax.resolve("A_s.y.total", scope="6.1", argument=True).concept.id == "A_s"
    assert tax.resolve("A_s.y.total", scope="6.2.2", argument=True).concept.id == "A_sl"
    assert tax.resolve("b_c", scope="6.2.2", argument=True).concept.id == "b_w"
    # a numbered subscript is part of the name: z_1 is not the lever arm z
    assert tax.resolve("z_1", scope="6.1", argument=True) is None


def test_decomposition_rewrites_spreadsheet_formulas_in_consistent_units(tmp_path):
    doc = convert_file(make_excel(tmp_path / "slab.xlsx"))
    doc.id = "S1"
    dec = decompose(doc, tax)
    forms = {(i.concept, i.loc.split()[-1]): X.to_python(i.formula) for i in dec.instances}
    # kN/m with "*1000*d/1000": per unit width, no conversion factors left
    assert forms[("V_Rd_c", "E20")] == "(C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * d"
    assert forms[("rho_l", "E16")] == "min(A_sl / d, 0.02)"
    # the template sheet states kN and has an explicit width
    assert forms[("V_Rd_c", "D15")] == "(C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d"
    per_width = [i for i in dec.instances if i.concept == "V_Rd_c" and i.per_width]
    assert len(per_width) == 2
    # project geometry and unknown quantities are kept apart, not distilled
    assert {dec.producer[s.id][0].id for s in dec.glue} == {"d"}
    assert {"Utilization", "Verified?"} <= {s.name for s in dec.unmapped}
    assert not dec.issues


def _merge(a, b):
    da, db = [], []
    out = Merger(tax).merge(X.parse(a), X.parse(b), da, db)
    return (X.to_python(out) if out is not None else None), [d.kind for d in da], [d.kind for d in db]


def test_merge_rules():
    assert _merge("0.18 / 1.5", "0.18 / gamma_C") == ("0.18 / gamma_C", ["literal"], [])
    assert _merge("f_ck / gamma_C", "alpha_cc * f_ck / gamma_C") == ("alpha_cc * f_ck / gamma_C", ["factor"], [])
    assert _merge("v_min * d", "(v_min + k_1 * sigma_cp) * d * b_w")[1] == ["term", "factor"]
    out, da, db = _merge("max(T * b_w * d, V_Rd_c_min)", "(T + k_1 * sigma_cp) * b_w * d")
    assert out == "max((T + k_1 * sigma_cp) * b_w * d, V_Rd_c_min)" and da == ["term"] and db == ["bound"]
    # disagreements are not papered over
    assert _merge("0.9 * d", "d - lam * x / 2")[0] is None
    assert _merge("0.9 * d", "0.85 * d")[0] is None
    assert _merge("0.9 * d", "0.9 * (d - 60)")[0] is None
    assert _merge("2 * d", "b_w * d")[0] is None          # 2 is not a plausible width
    assert _merge("A_sl / d", "A_sl / h")[0] is None


def _inst(concept, formula, doc, per_width=False, **args):
    tree = X.parse(formula)
    return Instance(concept, doc, "s", "formula", X.evaluate(tree, args), tree,
                    {k: {"value": v, "stmt": k, "name": k} for k, v in args.items()}, per_width=per_width)


def test_consolidation_of_three_variants_gives_the_code_expression():
    a = _inst("V_Rd_c", "(C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * d", "S1", True,
              C_Rd_c=0.12, k=1.8, rho_l=0.005, f_ck=30, k_1=0.15, sigma_cp=0.0, d=250)
    b = _inst("V_Rd_c", "(C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d", "S1",
              C_Rd_c=0.12, k=1.8, rho_l=0.005, f_ck=30, k_1=0.15, sigma_cp=0.0, d=250, b_w=1000)
    c = _inst("V_Rd_c", "max(C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) * b_w * d, V_Rd_c_min)", "S2",
              C_Rd_c=0.12, k=1.8, rho_l=0.005, f_ck=30, d=250, b_w=300, V_Rd_c_min=40000)
    cons = consolidate("V_Rd_c", [a, a, b, c], tax, {"sigma_cp": [0.0, 0.5]})
    assert X.to_python(cons.unified) == \
        "max((C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d, V_Rd_c_min)"
    assert cons.status == "unified" and len(cons.merged) == 3 and not cons.conflicts
    assert cons.neutral == {"sigma_cp": 0.0}
    assert sorted(sorted(d.kind for d in v.diffs) for v in cons.merged) == [["bound"], ["bound", "factor"], ["term"]]
    for v in cons.merged:                                    # each variant really is a special case
        assert is_special_case(cons.unified, v, tax, {"sigma_cp": [0.0, 0.5]})


def test_a_missing_width_is_only_accepted_from_a_per_width_source():
    wide = _inst("V_Rd_c_min", "v_min * b_w * d", "S1", v_min=0.4, b_w=300, d=450)
    strip = _inst("V_Rd_c_min", "v_min * d", "S2", per_width=False, v_min=0.4, d=450)   # claims a force, has no width
    cons = consolidate("V_Rd_c_min", [wide, wide, strip], tax, {})
    assert X.to_python(cons.unified) == "v_min * b_w * d" and len(cons.conflicts) == 1 and cons.status == "disagreement"


def test_disagreement_and_project_specific_variants_are_kept_apart():
    a = _inst("z", "0.9 * d", "S1", d=400)
    b = _inst("z", "d - lam * x / 2", "S2", d=400, lam=0.8, x=90)
    cons = consolidate("z", [a, a, b], tax, {})
    assert cons.status == "disagreement" and X.to_python(cons.unified) == "0.9 * d"
    assert [v.merged for v in cons.variants] == [True, False]
    tree = X.substitute(X.parse("T * z"), {"T": "~T"})          # ~T: a quantity the taxonomy does not know
    local = Instance("M_Rd", "S1", "s", "formula", 2000.0, tree,
                     {"~T": {"value": 5.0, "stmt": "t", "name": "T"}, "z": {"value": 400.0, "stmt": "z", "name": "z"}})
    cons = consolidate("M_Rd", [local], tax, {})
    assert cons.unified is None and cons.status == "project-specific"


def test_a_wrong_merge_is_caught_numerically():
    v = Variant(X.parse("0.5 * a + b"))
    assert not is_special_case(X.parse("a + b"), v, tax, {})
