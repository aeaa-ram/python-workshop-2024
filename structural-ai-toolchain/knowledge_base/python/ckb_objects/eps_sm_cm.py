"""ε_sm−ε_cm - Difference between the mean strains of reinforcement and concrete

EN 1992-1-1 cl. 7.3.4(2), expr. (7.9)
7 Serviceability limit states (SLS) > 7.3 Crack control > 7.3.4 Calculation of crack widths

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 2 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 eps_sm_eps_cm(sigma_s, alpha_e, rho_p_eff, kt, fct_eff, Es) (200 samples).
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/eps_sm_cm.yaml (version 348d3d3f9bd8) - do not edit by hand.
"""
from .alpha_e import alpha_e as _alpha_e
from .x import x as _x
from .sigma_s import sigma_s as _sigma_s
from .h_c_ef import h_c_ef as _h_c_ef
from .A_c_eff import A_c_eff as _A_c_eff
from .rho_p_eff import rho_p_eff as _rho_p_eff


def eps_sm_cm(sigma_s, k_t, f_ct_eff, rho_p_eff, alpha_e, E_s):
    """Difference between the mean strains of reinforcement and concrete [-]
    
    sigma_s    Stress in the tension reinforcement assuming a cracked section [MPa]
    k_t        Factor dependent on the duration of the load [-]
    f_ct_eff   Mean tensile strength of the concrete effective at the time of cracking [MPa]
    rho_p_eff  Effective reinforcement ratio [-]
    alpha_e    Modular ratio E_s / E_c [-]
    E_s        Design value of modulus of elasticity of reinforcing steel [MPa]
    """
    return max((sigma_s - k_t * f_ct_eff / rho_p_eff * (1 + alpha_e * rho_p_eff)) / E_s, 0.6 * sigma_s / E_s)


def eps_sm_cm_chain(E_s, E_cm, M_Ed, I_cr, d, f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck, k_t, f_ct_eff, h):
    """ε_sm−ε_cm from the primary inputs, through the objects it depends on."""
    alpha_e = _alpha_e(E_s, E_cm)
    x = _x(f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck)
    sigma_s = _sigma_s(alpha_e, M_Ed, I_cr, d, x)
    h_c_ef = _h_c_ef(h, d, x)
    A_c_eff = _A_c_eff(h_c_ef, b)
    rho_p_eff = _rho_p_eff(A_s, A_c_eff)
    return eps_sm_cm(sigma_s, k_t, f_ct_eff, rho_p_eff, alpha_e, E_s)
