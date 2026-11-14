"""σ_s - Stress in the tension reinforcement assuming a cracked section

EN 1992-1-1 cl. 7.3.4(2)
7 Serviceability limit states (SLS) > 7.3 Crack control > 7.3.4 Calculation of crack widths

Status: single source - 2 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 5 source values reproduced.
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/sigma_s.yaml (version 673a89f1f975) - do not edit by hand.
"""
from .alpha_e import alpha_e as _alpha_e
from .x import x as _x


def sigma_s(alpha_e, M_Ed, I_cr, d, x):
    """Stress in the tension reinforcement assuming a cracked section [MPa]
    
    alpha_e  Modular ratio E_s / E_c [-]
    M_Ed     Design bending moment [Nmm]
    I_cr     Second moment of area of the cracked section [mm4]
    d        Effective depth of the cross-section [mm]
    x        Neutral axis depth [mm]
    """
    return alpha_e * M_Ed / I_cr * (d - x)


def sigma_s_chain(E_s, E_cm, M_Ed, I_cr, d, f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck):
    """σ_s from the primary inputs, through the objects it depends on."""
    alpha_e = _alpha_e(E_s, E_cm)
    x = _x(f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck)
    return sigma_s(alpha_e, M_Ed, I_cr, d, x)
