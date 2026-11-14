"""s_r,max - Maximum crack spacing

EN 1992-1-1 cl. 7.3.4(3), expr. (7.11)
7 Serviceability limit states (SLS) > 7.3 Crack control > 7.3.4 Calculation of crack widths

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 2 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 sr_max_close(c, phi, rho_p_eff, k1, k2, k3, k4) (200 samples).
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.
Note: Valid where the bar spacing is not larger than 5(c + ϕ/2); otherwise 7.3.4(3) expression
(7.14) applies.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/s_r_max.yaml (version 4137d2d88b8f) - do not edit by hand.
"""
from .x import x as _x
from .h_c_ef import h_c_ef as _h_c_ef
from .A_c_eff import A_c_eff as _A_c_eff
from .rho_p_eff import rho_p_eff as _rho_p_eff


def s_r_max(k_3, c, k_1, k_2, k_4, phi, rho_p_eff):
    """Maximum crack spacing [mm]
    
    k_3        Coefficient k3 for crack spacing [-]
    c          Cover to the longitudinal reinforcement [mm]
    k_1        Coefficient for the bond properties of the reinforcement [-]
    k_2        Coefficient for the distribution of strain [-]
    k_4        Coefficient k4 for crack spacing [-]
    phi        Bar diameter (equivalent diameter for a mix of sizes) [mm]
    rho_p_eff  Effective reinforcement ratio [-]
    """
    return k_3 * c + k_1 * k_2 * k_4 * phi / rho_p_eff


def s_r_max_chain(k_3, c, k_1, k_2, k_4, phi, A_s, h, d, f_yk, gamma_S, gamma_C, lam, b, alpha_cc, f_ck):
    """s_r,max from the primary inputs, through the objects it depends on."""
    x = _x(f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck)
    h_c_ef = _h_c_ef(h, d, x)
    A_c_eff = _A_c_eff(h_c_ef, b)
    rho_p_eff = _rho_p_eff(A_s, A_c_eff)
    return s_r_max(k_3, c, k_1, k_2, k_4, phi, rho_p_eff)
