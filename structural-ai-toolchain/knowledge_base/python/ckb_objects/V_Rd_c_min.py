"""V_Rd,c,min - Minimum design shear resistance without shear reinforcement

EN 1992-1-1 cl. 6.2.2(1), expr. (6.2.b)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.2 Members not requiring design shear reinforcement

Status: unified - 86 formula instance(s) in 2 independent source(s), 3 variant(s) merged.
Benchmarks: 80 of 88 source values reproduced, 8 deviation(s).
Reference: agrees with structuralcodes 0.7.3 (shear.vmin(fck, d) + k1·σcp)·bw·d (200 samples).
Finding: 8 source value(s) differ from the unified logic: the source formula leaves out k_1 ·
σ_cp, which is not zero here.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/V_Rd_c_min.yaml (version 74021ebb23cb) - do not edit by hand.
"""
from .k import k as _k
from .v_min import v_min as _v_min


def V_Rd_c_min(v_min, k_1, sigma_cp, b_w, d):
    """Minimum design shear resistance without shear reinforcement [N]
    
    v_min     Minimum shear strength [MPa]
    k_1       Coefficient for the effect of axial stress on shear resistance [-]
    sigma_cp  Concrete compressive stress from axial load or prestress (compression positive) [MPa]
    b_w       Smallest width of the cross-section in the tensile area [mm]
    d         Effective depth of the cross-section [mm]
    """
    return (v_min + k_1 * sigma_cp) * b_w * d


def V_Rd_c_min_chain(d, f_ck, k_1, sigma_cp, b_w):
    """V_Rd,c,min from the primary inputs, through the objects it depends on."""
    k = _k(d)
    v_min = _v_min(k, f_ck)
    return V_Rd_c_min(v_min, k_1, sigma_cp, b_w, d)
