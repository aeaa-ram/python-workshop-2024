"""Tests for round-3 features: naming, annexes, discovery, self-contained
PDF reconstruction, parametric studies, branding, dashboard."""

import pytest

from src.models.calculation import CalcSheet
from src.models.naming import find_synonym_clashes, symbol_to_latex


# ---------------------------------------------------------------- naming
@pytest.mark.parametrize("name,expected", [
    ("E_cm", "E_{cm}"),
    ("f_c__k", "f_{c,k}"),
    ("sigma_Rd__max", r"\sigma_{Rd,max}"),
    ("epsilon_sm", r"\varepsilon_{sm}"),
    ("k_1", "k_{1}"),
    ("phi", r"\phi"),
    ("rho_p__eff", r"\rho_{p,eff}"),
])
def test_symbol_to_latex(name, expected):
    assert symbol_to_latex(name) == expected


def test_synonym_clash_detection():
    clashes = find_synonym_clashes(["E_c", "E_cm", "d", "phi"])
    assert clashes and clashes[0][0] == "concrete_elastic_modulus"
    assert set(clashes[0][1]) == {"E_c", "E_cm"}


# ------------------------------------------------------- national annexes
def test_national_annex_parameter_override():
    from src.library import resolve

    en = resolve("crack.max_spacing", "EN")
    demo = resolve("crack.max_spacing", "XX-DEMO")
    assert en.params["k_3"] == 3.4
    assert demo.params["k_3"] == 1.0            # override applied
    assert en.params["k_1"] == demo.params["k_1"]  # untouched param shared
    assert len(demo.provenance) == 2            # base clause + annex clause


def test_full_alternative_variant_shares_concept():
    from src.library import resolve

    base = resolve("crack.characteristic_width", "EN")
    alt = resolve("crack.characteristic_width", "ALT-DIRECT")
    assert base.atom.atom_id == "ec2.crack.w_k"
    assert alt.atom.atom_id == "alt.crack.w_k_direct"
    assert alt.atom.expression != base.atom.expression   # different approach


def test_apply_injects_annex_coefficient():
    s = CalcSheet(title="t")
    s.define("c", 30, unit="mm")
    s.define("phi", 16, unit="mm")
    s.define("rho_p_eff", 0.012, unit="-")
    s.apply("s_r_max", "ec2.crack.s_r_max", jurisdiction="XX-DEMO")
    assert s.values["k_3"] == 1.0     # NA coefficient auto-defined
    # result uses the overridden coefficient
    assert s.values["s_r_max"] == pytest.approx(1.0 * 30 + 0.8 * 0.5 * 0.425 * 16 / 0.012, rel=1e-6)


def test_atom_params_vs_inputs():
    from src.library import get_atom

    atom = get_atom("ec2.crack.s_r_max")
    assert set(atom.params) == {"k_1", "k_2", "k_3", "k_4"}
    assert set(atom.inputs) == {"c", "phi", "rho_p_eff"}
    # callable with inputs only (params default)
    val = atom(c=30, phi=16, rho_p_eff=0.012)
    assert val == pytest.approx(3.4 * 30 + 0.8 * 0.5 * 0.425 * 16 / 0.012)


# ------------------------------------------------------------- discovery
def test_catalog_tree_and_search():
    from src.library import catalog, search

    tree = catalog()
    assert "EN" in tree and "EN 1992-1-1" in tree["EN"]
    hits = search("crack width")
    assert hits and hits[0].atom.concept == "crack.characteristic_width"
    assert search("modulus of elasticity")  # non-empty


# ----------------------------------------------- parametric / recompute
def test_recompute_and_parametric_study():
    from src.output_engine.parametric import ParametricStudy

    s = CalcSheet(title="Beam")
    s.define("q", 4.0, unit="kN/m")
    s.define("L", 5.0, unit="m")
    s.define("W", 12.5, unit="mm^3")  # dummy
    s.define("f_lim", 20.0, unit="MPa")
    s.calc("M", "q*L**2/8", unit="kNm")
    s.calc("sigma", "M", unit="MPa")   # simplified
    s.check("sigma <= f_lim")
    # base passes
    assert s.all_passed()
    # recompute with a bigger load fails
    r = s.recompute({"q": 20.0})
    assert r["passed"] is False
    # parametric study tabulates and flags the first failing (governing)
    study = ParametricStudy(s, [{"q": 4}, {"q": 10}, {"q": 20}])
    md = study.summary_markdown(result_vars=["sigma"])
    assert "NOT OK" in md and "OK" in md
    assert study.critical_index("sigma") == 1  # q=10 already fails
    # when all pass, critical = max utilisation
    ok_study = ParametricStudy(s, [{"q": 1}, {"q": 3}, {"q": 2}])
    assert ok_study.critical_index("sigma") == 1  # q=3 is worst


def test_recompute_rejects_unknown_input():
    from src.models.calculation import CalcSheetError

    s = CalcSheet(title="t")
    s.define("a", 1)
    s.calc("b", "a*2")
    with pytest.raises(CalcSheetError):
        s.recompute({"nope": 5})


# ---------------------------------------- self-contained PDF reconstruction
def _has_chromium():
    from src.output_engine import find_chromium
    return find_chromium() is not None


@pytest.mark.skipif(not _has_chromium(), reason="no Chromium")
def test_pdf_reconstructs_from_itself(tmp_path):
    from src.output_engine import render_pdf_browser, reconstruct_from_pdf
    from src.output_engine.branding import Branding, ReportMeta

    s = CalcSheet(title="Self Contained", reference="EN 1990")
    s.define("b", 300, unit="mm", description="Width")
    s.define("h", 500, unit="mm", description="Depth")
    s.define("lim", 20, unit="MPa")
    s.calc("W", "b*h**2/6", unit="mm^3", description="Modulus")
    s.calc("sig", "45e6/W", unit="MPa", description="Stress")
    s.check("sig <= lim", "Within limit")
    pdf = render_pdf_browser(
        s, tmp_path / "r.pdf",
        branding=Branding(),
        meta=ReportMeta(prepared_by="AB", checked_by="CD", approved_by="EF"),
    )
    # THE requirement: reconstruct from the PDF alone (in-page layer)
    data = reconstruct_from_pdf(pdf)
    assert data["schema"] == CalcSheet.SCHEMA
    assert data["results"]["W"] == pytest.approx(12.5e6)
    assert data["results"]["sig"] == pytest.approx(3.6)
    assert data["checks_passed"] is True


@pytest.mark.skipif(not _has_chromium(), reason="no Chromium")
def test_compact_mode_renders(tmp_path):
    from src.output_engine import render_html

    s = CalcSheet(title="Compact")
    s.define("f_ck", 30, unit="MPa")
    s.calc("E", "22000*((f_ck+8)/10)**0.3", unit="MPa", description="Modulus")
    detailed = render_html(s, mode="detailed")
    compact = render_html(s, mode="compact")
    assert "compact" in compact           # compact css class present
    assert compact != detailed


# ----------------------------------------------------------- dashboard
def test_dashboard_generation(tmp_path):
    from examples.make_fixtures import make_crack_width_xlsx
    from src.dashboard import generate_dashboard
    from src.ingestion import grind

    repo = tmp_path / "repo"
    grind(make_crack_width_xlsx(tmp_path), repo, skip_gatekeeper=True)
    out = generate_dashboard(repo, tmp_path / "dash.html")
    html = out.read_text(encoding="utf-8")
    assert "Dashboard" in html
    assert "Crack Width" in html
    assert "Digested formula library" in html
    assert "Recycles" in html            # reuse view present
