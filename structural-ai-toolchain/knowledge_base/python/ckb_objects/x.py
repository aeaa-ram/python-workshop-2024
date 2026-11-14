"""x - Neutral axis depth

EN 1992-1-1
6 Ultimate limit states (ULS) > 6.1 Bending with or without axial force

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 4 source values reproduced.
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/x.yaml (version 62c6ced296c7) - do not edit by hand.
"""


def x(f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck):
    """Neutral axis depth [mm]
    
    f_yk      Characteristic yield strength of reinforcement [MPa]
    gamma_S   Partial factor for reinforcing steel [-]
    A_s       Cross-sectional area of tension reinforcement [mm2]
    gamma_C   Partial factor for concrete [-]
    lam       Factor defining the effective height of the compression zone [-]
    b         Width of the cross-section (compression zone) [mm]
    alpha_cc  Coefficient for long-term effects on the compressive strength [-]
    f_ck      Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return f_yk / gamma_S * A_s * gamma_C / (lam * b * alpha_cc * f_ck)
