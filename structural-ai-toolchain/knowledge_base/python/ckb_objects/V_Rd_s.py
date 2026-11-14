"""V_Rd,s - Design shear resistance governed by yielding of the shear reinforcement

EN 1992-1-1 cl. 6.2.3(3), expr. (6.8)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.3 Members requiring design shear reinforcement

Status: single source - 2 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 4 of 4 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 VRds(Asw, s, z, theta, fyk, alpha=90, gamma_s) (200 samples).
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/V_Rd_s.yaml (version e87f4b3b5693) - do not edit by hand.
"""
from math import tan
def cot(x):
    return 1.0 / tan(x)

from .z import z as _z


def V_Rd_s(A_sw, s, z, f_ywk, gamma_S, theta):
    """Design shear resistance governed by yielding of the shear reinforcement [N]
    
    A_sw     Cross-sectional area of the shear reinforcement [mm2]
    s        Spacing of the stirrups [mm]
    z        Lever arm of internal forces [mm]
    f_ywk    Characteristic yield strength of the shear reinforcement [MPa]
    gamma_S  Partial factor for reinforcing steel [-]
    theta    Angle between the concrete compression strut and the beam axis [rad]
    """
    return A_sw / s * z * f_ywk / gamma_S * cot(theta)


def V_Rd_s_chain(A_sw, s, d, f_ywk, gamma_S, theta):
    """V_Rd,s from the primary inputs, through the objects it depends on."""
    z = _z(d)
    return V_Rd_s(A_sw, s, z, f_ywk, gamma_S, theta)
