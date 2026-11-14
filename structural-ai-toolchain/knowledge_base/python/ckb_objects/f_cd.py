"""f_cd - Design value of concrete compressive strength

EN 1992-1-1 cl. 3.1.6(1), expr. (3.15)
3 Materials > 3.1 Concrete

Status: single source - 4 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 4 of 4 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 fcd(fck, alpha_cc, gamma_c) (200 samples).
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/f_cd.yaml (version 005ea82f6bd7) - do not edit by hand.
"""


def f_cd(f_ck, gamma_C):
    """Design value of concrete compressive strength [MPa]
    
    f_ck     Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    gamma_C  Partial factor for concrete [-]
    """
    return f_ck / gamma_C
