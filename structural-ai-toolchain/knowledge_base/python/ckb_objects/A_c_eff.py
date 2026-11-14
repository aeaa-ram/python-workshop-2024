"""A_c,eff - Effective area of concrete in tension surrounding the reinforcement

EN 1992-1-1 cl. 7.3.2(3)
7 Serviceability limit states (SLS) > 7.3 Crack control > 7.3.4 Calculation of crack widths

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 1 of 1 source values reproduced.
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/A_c_eff.yaml (version 7fcfc2800f9a) - do not edit by hand.
"""
from .x import x as _x
from .h_c_ef import h_c_ef as _h_c_ef


def A_c_eff(h_c_ef, b):
    """Effective area of concrete in tension surrounding the reinforcement [mm2]
    
    h_c_ef  Effective height of the concrete tension zone [mm]
    b       Width of the cross-section (compression zone) [mm]
    """
    return h_c_ef * b


def A_c_eff_chain(h, d, f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck):
    """A_c,eff from the primary inputs, through the objects it depends on."""
    x = _x(f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck)
    h_c_ef = _h_c_ef(h, d, x)
    return A_c_eff(h_c_ef, b)
