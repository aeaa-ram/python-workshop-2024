"""M_Rd - Design moment resistance

EN 1992-1-1
6 Ultimate limit states (ULS) > 6.1 Bending with or without axial force

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 2 source values reproduced.
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/M_Rd.yaml (version 54a816402a91) - do not edit by hand.
"""
from .z import z as _z


def M_Rd(A_s, f_yk, gamma_S, z):
    """Design moment resistance [Nmm]
    
    A_s      Cross-sectional area of tension reinforcement [mm2]
    f_yk     Characteristic yield strength of reinforcement [MPa]
    gamma_S  Partial factor for reinforcing steel [-]
    z        Lever arm of internal forces [mm]
    """
    return A_s * f_yk / gamma_S * z


def M_Rd_chain(A_s, f_yk, gamma_S, d):
    """M_Rd from the primary inputs, through the objects it depends on."""
    z = _z(d)
    return M_Rd(A_s, f_yk, gamma_S, z)
