"""Structural fingerprinting and atomic reuse analysis."""

import pytest

from src.knowledge_graph.fingerprint import (
    fingerprint,
    fingerprint_if_matchable,
)
from src.knowledge_graph.reuse import analyze_reuse
from src.models.calculation import ParsedTool, ParsedVariable


@pytest.mark.parametrize(
    "a,b",
    [
        ("k_3*c + k_1*k_2*k_4*phi/rho_p_eff", "k3*cn + k1*k2*k4*d/rho"),
        ("(f_cm_t / f_cm)**0.3 * E_cm", "E * (fa/fb)**0.3"),
        ("exp(s_cem*(1 - sqrt(28/t)))", "exp(s*(1-sqrt(28/age)))"),
        ("b*h**2/6", "width*depth**2/6"),
    ],
)
def test_fingerprint_name_independent(a, b):
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_distinguishes_structure():
    assert fingerprint("a/b") != fingerprint("a*b")
    assert fingerprint("b*h**2/6") != fingerprint("q*L**2/8")


def test_trivial_formulas_not_matchable():
    # too few operations to be a meaningful structural match
    assert fingerprint_if_matchable("a*b") is None
    assert fingerprint_if_matchable("a/b") is None
    # but a real multi-op formula is
    assert fingerprint_if_matchable("k_3*c + k_1*k_2*k_4*phi/rho") is not None


def test_e_name_not_hijacked():
    # bare 'E' must be a symbol, not Euler's number
    assert fingerprint("E * x + y*z") == fingerprint("A * b + c*d")


def test_analyze_reuse_flags_atom(tmp_path):
    tool = ParsedTool(title="Demo", source_path="x", source_format="py")
    tool.variables = [
        ParsedVariable("E_s", 200000, role="input"),
        ParsedVariable("E_cm", 33000, role="input"),
        # matches ec2.crack.s_r_max structurally
        ParsedVariable(
            "s", role="derived",
            expression="k_3*c + k_1*k_2*k_4*phi/rho_p_eff",
        ),
        ParsedVariable("brand_new", role="derived", expression="a*b + c*d*e"),
    ]
    findings = analyze_reuse(tool, tmp_path)
    by_name = {f.name: f for f in findings}
    assert by_name["s"].status == "matches_atom"
    assert by_name["s"].match_id == "ec2.crack.s_r_max"
    assert by_name["brand_new"].status == "new"
