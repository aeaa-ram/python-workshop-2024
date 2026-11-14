"""h_c,ef - Effective height of the concrete tension zone

EN 1992-1-1 cl. 7.3.2(3)
7 Serviceability limit states (SLS) > 7.3 Crack control > 7.3.4 Calculation of crack widths

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 2 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 hc_eff(h, d, x) (200 samples).
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/h_c_ef.yaml (version 451e89571a76) - do not edit by hand.
"""
from .x import x as _x


def h_c_ef(h, d, x):
    """Effective height of the concrete tension zone [mm]
    
    h  Overall depth of the cross-section [mm]
    d  Effective depth of the cross-section [mm]
    x  Neutral axis depth [mm]
    """
    return min(2.5 * (h - d), (h - x) / 3, h / 2)


def h_c_ef_chain(h, d, f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck):
    """h_c,ef from the primary inputs, through the objects it depends on."""
    x = _x(f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck)
    return h_c_ef(h, d, x)
