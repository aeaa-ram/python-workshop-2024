"""w_k - Calculated crack width

EN 1992-1-1 cl. 7.3.4(1), expr. (7.8)
7 Serviceability limit states (SLS) > 7.3 Crack control > 7.3.4 Calculation of crack widths

Status: single source - 1 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 2 of 2 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 wk(sr_max, eps_sm_eps_cm) (200 samples).
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/w_k.yaml (version 936ee924037d) - do not edit by hand.
"""
from .x import x as _x
from .h_c_ef import h_c_ef as _h_c_ef
from .A_c_eff import A_c_eff as _A_c_eff
from .rho_p_eff import rho_p_eff as _rho_p_eff
from .s_r_max import s_r_max as _s_r_max
from .alpha_e import alpha_e as _alpha_e
from .sigma_s import sigma_s as _sigma_s
from .eps_sm_cm import eps_sm_cm as _eps_sm_cm


def w_k(s_r_max, eps_sm_cm):
    """Calculated crack width [mm]
    
    s_r_max    Maximum crack spacing [mm]
    eps_sm_cm  Difference between the mean strains of reinforcement and concrete [-]
    """
    return s_r_max * eps_sm_cm


def w_k_chain(k_3, c, k_1, k_2, k_4, phi, A_s, h, d, f_yk, gamma_S, gamma_C, lam, b, alpha_cc, f_ck, E_s, E_cm, M_Ed, I_cr, k_t, f_ct_eff):
    """w_k from the primary inputs, through the objects it depends on."""
    x = _x(f_yk, gamma_S, A_s, gamma_C, lam, b, alpha_cc, f_ck)
    h_c_ef = _h_c_ef(h, d, x)
    A_c_eff = _A_c_eff(h_c_ef, b)
    rho_p_eff = _rho_p_eff(A_s, A_c_eff)
    s_r_max = _s_r_max(k_3, c, k_1, k_2, k_4, phi, rho_p_eff)
    alpha_e = _alpha_e(E_s, E_cm)
    sigma_s = _sigma_s(alpha_e, M_Ed, I_cr, d, x)
    eps_sm_cm = _eps_sm_cm(sigma_s, k_t, f_ct_eff, rho_p_eff, alpha_e, E_s)
    return w_k(s_r_max, eps_sm_cm)
