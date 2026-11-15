"""ε_sm−ε_cm - EN 1992-1-1 cl. 7.3.4(2), expr. (7.9).  Units: N, mm, MPa, rad."""
# ckb eps_sm_cm cba2d32d8697
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .alpha_e import alpha_e as _alpha_e
from .x_el import x_el as _x_el
from .I_cr import I_cr as _I_cr
from .sigma_s import sigma_s as _sigma_s
from .f_ctm import f_ctm as _f_ctm
from .f_ct_eff import f_ct_eff as _f_ct_eff
from .h_c_ef import h_c_ef as _h_c_ef
from .A_c_eff import A_c_eff as _A_c_eff
from .rho_p_eff import rho_p_eff as _rho_p_eff


def eps_sm_cm(sigma_s, k_t, f_ct_eff, rho_p_eff, alpha_e, E_s):
    """Difference between the mean strains of reinforcement and concrete [-]
    EN 1992-1-1 cl. 7.3.4(2), expr. (7.9)
    
    sigma_s    Stress in the tension reinforcement assuming a cracked section [MPa]
    k_t        Factor for the duration of the load [-]
    f_ct_eff   Mean tensile strength of the concrete when the first cracks may occur [MPa]
    rho_p_eff  Effective reinforcement ratio [-]
    alpha_e    Modular ratio E_s / E_cm [-]
    E_s        Design modulus of elasticity of reinforcing steel [MPa]
    """
    return max((sigma_s - k_t * f_ct_eff / rho_p_eff * (1 + alpha_e * rho_p_eff)) / E_s, 0.6 * sigma_s / E_s)


def eps_sm_cm_chain(E_s, f_ck, M_SLS, d, A_s, b, k_t, h):
    """ε_sm−ε_cm from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    alpha_e = _alpha_e(E_s, E_cm)
    x_el = _x_el(alpha_e, A_s, b, d)
    I_cr = _I_cr(b, x_el, alpha_e, A_s, d)
    sigma_s = _sigma_s(alpha_e, M_SLS, d, x_el, I_cr)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ct_eff = _f_ct_eff(f_ctm)
    h_c_ef = _h_c_ef(h, d, x_el)
    A_c_eff = _A_c_eff(h_c_ef, b)
    rho_p_eff = _rho_p_eff(A_s, A_c_eff)
    return eps_sm_cm(sigma_s, k_t, f_ct_eff, rho_p_eff, alpha_e, E_s)
