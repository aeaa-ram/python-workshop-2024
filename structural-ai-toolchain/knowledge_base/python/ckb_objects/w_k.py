"""w_k - EN 1992-1-1 cl. 7.3.4(1), expr. (7.8).  Units: N, mm, MPa, rad."""
# ckb w_k 1c34e85ebf5c
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .alpha_e import alpha_e as _alpha_e
from .x_el import x_el as _x_el
from .h_c_ef import h_c_ef as _h_c_ef
from .A_c_eff import A_c_eff as _A_c_eff
from .rho_p_eff import rho_p_eff as _rho_p_eff
from .s_r_max import s_r_max as _s_r_max
from .I_cr import I_cr as _I_cr
from .sigma_s import sigma_s as _sigma_s
from .f_ctm import f_ctm as _f_ctm
from .f_ct_eff import f_ct_eff as _f_ct_eff
from .eps_sm_cm import eps_sm_cm as _eps_sm_cm


def w_k(s_r_max, eps_sm_cm):
    """Calculated crack width [mm]
    EN 1992-1-1 cl. 7.3.4(1), expr. (7.8)
    
    s_r_max    Maximum crack spacing [mm]
    eps_sm_cm  Difference between the mean strains of reinforcement and concrete [-]
    """
    return s_r_max * eps_sm_cm


def w_k_chain(k_3, c, k_1, k_2, k_4, phi, A_s, h, d, E_s, f_ck, b, M_SLS, k_t):
    """w_k from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    alpha_e = _alpha_e(E_s, E_cm)
    x_el = _x_el(alpha_e, A_s, b, d)
    h_c_ef = _h_c_ef(h, d, x_el)
    A_c_eff = _A_c_eff(h_c_ef, b)
    rho_p_eff = _rho_p_eff(A_s, A_c_eff)
    s_r_max = _s_r_max(k_3, c, k_1, k_2, k_4, phi, rho_p_eff)
    I_cr = _I_cr(b, x_el, alpha_e, A_s, d)
    sigma_s = _sigma_s(alpha_e, M_SLS, d, x_el, I_cr)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ct_eff = _f_ct_eff(f_ctm)
    eps_sm_cm = _eps_sm_cm(sigma_s, k_t, f_ct_eff, rho_p_eff, alpha_e, E_s)
    return w_k(s_r_max, eps_sm_cm)
