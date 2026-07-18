"""Atomic formula library — single source of truth."""

import pytest

from src.library import Atom, AtomError, all_atoms, custom, get_atom


def test_custom_namespace_callable():
    # EN 1992-1-1 concrete modulus in time, C30/37, class N, 7 days
    beta = custom.beta_cc_t(s_cem=0.25, t=7)
    assert beta == pytest.approx(0.7788, abs=1e-3)
    fcm_t = custom.f_cm_t(beta_cc_t=beta, f_cm=38)
    assert fcm_t == pytest.approx(29.59, abs=0.05)
    E_cm_t = custom.E_cm_t(f_cm_t=fcm_t, f_cm=38, E_cm=32837)
    assert E_cm_t == pytest.approx(30464, abs=5)


def test_lookup_by_short_and_full_id():
    assert get_atom("ec2.concrete.E_cm_t") is get_atom("E_cm_t")


def test_missing_argument_raises():
    with pytest.raises(AtomError):
        custom.E_cm_t(f_cm_t=30)  # missing f_cm, E_cm


def test_expression_for_is_faithful_and_renamed():
    atom = get_atom("ec2.concrete.beta_cc_t")
    # no subs -> original string, sqrt(28/t) preserved
    assert atom.expression_for({}) == "exp(s_cem*(1 - sqrt(28/t)))"
    # renamed, still faithful
    renamed = atom.expression_for({"t": "age", "s_cem": "s"})
    assert renamed == "exp(s*(1 - sqrt(28/age)))"


def test_expression_for_rejects_unknown_symbol():
    atom = get_atom("ec2.general.alpha_e")
    with pytest.raises(AtomError):
        atom.expression_for({"not_a_symbol": "x"})


def test_all_atoms_have_provenance():
    for atom in all_atoms():
        assert atom.result
        assert atom.expression
        # every seeded atom cites a clause or a mechanics source
        assert atom.clause, f"{atom.atom_id} missing clause"


def test_apply_in_sheet_reuses_atom():
    from src.models.calculation import CalcSheet

    sheet = CalcSheet(title="t")
    sheet.define("E_s", 200000, unit="MPa")
    sheet.define("E_cm", 33000, unit="MPa")
    item = sheet.apply("alpha_e", "ec2.general.alpha_e")
    assert item.atom_id == "ec2.general.alpha_e"
    assert item.value == pytest.approx(200000 / 33000)
