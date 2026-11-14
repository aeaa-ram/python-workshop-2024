"""v_min - Minimum shear strength

EN 1992-1-1 cl. 6.2.2(1), expr. (6.3N)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.2 Members not requiring design shear reinforcement

Status: consensus - 86 formula instance(s) in 2 independent source(s), 1 variant(s) merged.
Benchmarks: 88 of 88 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 shear.vmin(fck, d) (200 samples).

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/v_min.yaml (version b505f90d4a09) - do not edit by hand.
"""
from .k import k as _k


def v_min(k, f_ck):
    """Minimum shear strength [MPa]
    
    k     Size factor for shear [-]
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 0.035 * k ** (3 / 2) * f_ck ** (1 / 2)


def v_min_chain(d, f_ck):
    """v_min from the primary inputs, through the objects it depends on."""
    k = _k(d)
    return v_min(k, f_ck)
