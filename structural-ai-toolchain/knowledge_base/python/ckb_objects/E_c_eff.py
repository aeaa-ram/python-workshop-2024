"""E_c,eff - Effective modulus of elasticity of concrete (creep)

EN 1992-1-1 cl. 7.4.3(5), expr. (7.20)
7 Serviceability limit states (SLS) > 7.4 Deflection control

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 2 source values reproduced.
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/E_c_eff.yaml (version a48916bb9c1e) - do not edit by hand.
"""


def E_c_eff(E_cm, phi):
    """Effective modulus of elasticity of concrete (creep) [MPa]
    
    E_cm  Secant modulus of elasticity of concrete [MPa]
    phi   Creep coefficient [-]
    """
    return E_cm / (1 + phi)
