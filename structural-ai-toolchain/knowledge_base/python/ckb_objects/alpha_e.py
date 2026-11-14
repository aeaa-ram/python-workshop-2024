"""α_e - Modular ratio E_s / E_c

EN 1992-1-1 cl. 7.3.4(2)
7 Serviceability limit states (SLS) > 7.3 Crack control > 7.3.4 Calculation of crack widths

Status: disagreement - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 3 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 alpha_e(Es, Ecm) (200 samples).
WARNING: Sources disagree: 1 other formula(s) for this quantity could not be merged with the one
shown. The one shown has the most support; an engineer has to decide.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/alpha_e.yaml (version 56ea4c84fa6c) - do not edit by hand.
"""


def alpha_e(E_s, E_cm):
    """Modular ratio E_s / E_c [-]
    
    E_s   Design value of modulus of elasticity of reinforcing steel [MPa]
    E_cm  Secant modulus of elasticity of concrete [MPa]
    """
    return E_s / E_cm
