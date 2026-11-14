"""V_Rd,c - Design shear resistance of a member without shear reinforcement

EN 1992-1-1 cl. 6.2.2(1), expr. (6.2.a)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.2 Members not requiring design shear reinforcement

Status: unified - 86 formula instance(s) in 2 independent source(s), 3 variant(s) merged.
Benchmarks: 64 of 88 source values reproduced, 24 deviation(s).
Reference: agrees with structuralcodes 0.7.3 VRdc(fck, d, Asl, bw, NEd, Ac, fcd, k1, gamma_c) (200 samples).
Finding: 24 source value(s) differ from the unified logic: the lower bound V_Rd,c,min governs
here; the source formula does not apply it.
Note: σ_cp is positive for compression and limited to 0.2 f_cd (6.2.2(1)); the limit is not part
of the distilled logic.
Note: A_sl only counts bars anchored at least l_bd + d beyond the section considered.
Note: Close to supports (0.5d ≤ a_v ≤ 2d) the load may be reduced by β = a_v/2d (6.2.2(6)); not
included.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/V_Rd_c.yaml (version 3eac6dff6d29) - do not edit by hand.
"""
from .C_Rd_c import C_Rd_c as _C_Rd_c
from .k import k as _k
from .rho_l import rho_l as _rho_l
from .v_min import v_min as _v_min
from .V_Rd_c_min import V_Rd_c_min as _V_Rd_c_min


def V_Rd_c(C_Rd_c, k, rho_l, f_ck, k_1, sigma_cp, b_w, d, V_Rd_c_min):
    """Design shear resistance of a member without shear reinforcement [N]
    
    C_Rd_c      Coefficient for the shear resistance of concrete [-]
    k           Size factor for shear [-]
    rho_l       Longitudinal reinforcement ratio [-]
    f_ck        Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    k_1         Coefficient for the effect of axial stress on shear resistance [-]
    sigma_cp    Concrete compressive stress from axial load or prestress (compression positive) [MPa]
    b_w         Smallest width of the cross-section in the tensile area [mm]
    d           Effective depth of the cross-section [mm]
    V_Rd_c_min  Minimum design shear resistance without shear reinforcement [N]
    """
    return max((C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d, V_Rd_c_min)


def V_Rd_c_chain(gamma_C, d, A_sl, b_w, f_ck, k_1, sigma_cp):
    """V_Rd,c from the primary inputs, through the objects it depends on."""
    C_Rd_c = _C_Rd_c(gamma_C)
    k = _k(d)
    rho_l = _rho_l(A_sl, d, b_w)
    v_min = _v_min(k, f_ck)
    V_Rd_c_min = _V_Rd_c_min(v_min, k_1, sigma_cp, b_w, d)
    return V_Rd_c(C_Rd_c, k, rho_l, f_ck, k_1, sigma_cp, b_w, d, V_Rd_c_min)
