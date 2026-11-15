"""Stages 3 and 4: recognising quantities and merging variants."""
import pytest

from ckb import expr as X
from ckb.distill.consolidate import Merger, Variant, consolidate, is_special_case
from ckb.distill.decompose import Instance, decompose
from ckb.distill.taxonomy import load
from ckb.convert import convert_file
from conftest import make_excel

tax = load()


def test_the_registry_holds_the_code_expressions():
    from ckb.distill.taxonomy import DATA
    assert (DATA / "common.yaml").exists() and len(list((DATA / "codes").glob("*.yaml"))) >= 2
    assert len(tax.concepts) > 50 and tax.concepts["V_Rd_c"].topic == "6.2.2"
    # the full code expression, even though most sources write f_ck / γ_C
    assert X.same(tax.concepts["f_cd"].tree, X.parse("alpha_cc * f_ck / gamma_C"))
    assert tax.concepts["alpha_cc"].ndp and tax.concepts["alpha_cc"].value == 1.0
    # every object knows when it applies and why
    v = tax.concepts["V_Rd_c"]
    assert any("0.2" in c["when"] for c in v.checks) and {b["kind"] for b in v.background} >= {"scope", "pitfall"}
    assert all(r.split(":")[0] in tax.references for b in v.background for r in b.get("refs", []))


def test_a_second_code_reuses_objects_instead_of_repeating_them():
    # EN 1994-1-1 writes f_cd = f_ck / γ_C: a special case of the EN 1992-1-1 object, not a second formula
    f_cd = tax.concepts["f_cd"]
    assert [r["code"] for r in f_cd.refs] == ["EN 1992-1-1", "EN 1994-1-1"] and "α_cc = 1" in f_cd.refs[1]["how"]
    assert tax.fixed_for("EN 1994-1-1") == {"alpha_cc": 1.0}
    # f_sd = f_yk / γ_S is the same expression as f_yd: one object, two names
    assert tax.id_alias.get("f_sd") == "f_yd" and "f_sd" not in tax.concepts
    assert "f_yd" in X.symbols(tax.concepts["N_pl_Rd"].tree)
    # E_cm is declared the same object
    assert any(r["code"] == "EN 1994-1-1" for r in tax.concepts["E_cm"].refs)


def test_sources_are_classified_against_the_code():
    from ckb.distill.baseline import compare
    code = tax.concepts["V_Rd_c"].tree
    rel, missing, _ = compare(code, X.parse(
        "(C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d"), tax, {})
    assert rel == "simplified" and [d.kind for d in missing] == ["bound"]
    rel, missing, _ = compare(tax.concepts["f_cd"].tree, X.parse("f_ck / gamma_C"), tax, {})
    assert rel == "simplified" and missing[0].kind == "factor"          # α_cc left out
    rel, _, _ = compare(tax.concepts["f_cd"].tree, X.parse("f_ck / 1.5"), tax, {})
    assert rel == "simplified"                                             # γ_C typed as a number too
    assert compare(tax.concepts["nu"].tree, X.parse("0.6 * (1 - f_ck / 250)"), tax, {})[0] == "as code"
    assert compare(tax.concepts["nu"].tree, X.parse("max(0.7 - f_ck / 200, 0.45)"), tax, {})[0] == "differs"
    # a source writing A_s where shear needs A_sl is read as A_sl
    renamed = {}
    rel, _, _ = compare(tax.concepts["rho_l"].tree, X.parse("min(A_s / (b_w * d), 0.02)"), tax, {}, renamed)
    assert rel == "as code" and renamed == {"A_s": "A_sl"}


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
