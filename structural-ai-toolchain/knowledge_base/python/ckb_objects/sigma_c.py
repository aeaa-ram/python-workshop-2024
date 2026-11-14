"""σ_c - Compressive stress in the concrete assuming a cracked section

EN 1992-1-1 cl. 7.2(2)
7 Serviceability limit states (SLS) > 7.2 Stress limitation

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 1 of 3 source values reproduced.
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/sigma_c.yaml (version ffe9ad9e9034) - do not edit by hand.
"""
from .x import x as _x


def sigma_c(M_Ed, I_cr, x):
    """Compressive stress in the concrete assuming a cracked section [MPa]
    
    M_Ed  Design bending moment [Nmm]
    I_cr  Second moment of area of the cracked section [mm4]
    x     Neutral axis depth [mm]
    """
    return M_Ed / I_cr * x


def sigma_c_chain(M_Ed, I_cr, f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck):
    """σ_c from the primary inputs, through the objects it depends on."""
    x = _x(f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck)
    return sigma_c(M_Ed, I_cr, x)
