"""ρ_p,eff - Effective reinforcement ratio

EN 1992-1-1 cl. 7.3.4(2), expr. (7.10)
7 Serviceability limit states (SLS) > 7.3 Crack control > 7.3.4 Calculation of crack widths

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 2 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 rho_p_eff(As, xi1=0, Ap=0, Ac_eff) (200 samples).
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/rho_p_eff.yaml (version 8a3f3d86bce9) - do not edit by hand.
"""
from .x import x as _x
from .h_c_ef import h_c_ef as _h_c_ef
from .A_c_eff import A_c_eff as _A_c_eff


def rho_p_eff(A_s, A_c_eff):
    """Effective reinforcement ratio [-]
    
    A_s      Cross-sectional area of tension reinforcement [mm2]
    A_c_eff  Effective area of concrete in tension surrounding the reinforcement [mm2]
    """
    return A_s / A_c_eff


def rho_p_eff_chain(A_s, h, d, f_yk, gamma_S, gamma_C, lam, b, alpha_cc, f_ck):
    """ρ_p,eff from the primary inputs, through the objects it depends on."""
    x = _x(f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck)
    h_c_ef = _h_c_ef(h, d, x)
    A_c_eff = _A_c_eff(h_c_ef, b)
    return rho_p_eff(A_s, A_c_eff)
