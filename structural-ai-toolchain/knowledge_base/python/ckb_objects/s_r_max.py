"""s_r,max - EN 1992-1-1 cl. 7.3.4(3), expr. (7.11).  Units: N, mm, MPa, rad."""
# ckb s_r_max 69bfc6b0a4e3
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .alpha_e import alpha_e as _alpha_e
from .x_el import x_el as _x_el
from .h_c_ef import h_c_ef as _h_c_ef
from .A_c_eff import A_c_eff as _A_c_eff
from .rho_p_eff import rho_p_eff as _rho_p_eff


def s_r_max(k_3, c, k_1, k_2, k_4, phi, rho_p_eff):
    """Maximum crack spacing [mm]
    EN 1992-1-1 cl. 7.3.4(3), expr. (7.11)
    
    k_3        Coefficient k3 for crack spacing [-]
    c          Clear cover to the longitudinal reinforcement [mm]
    k_1        Coefficient for the bond properties of the reinforcement [-]
    k_2        Coefficient for the distribution of strain [-]
    k_4        Coefficient k4 for crack spacing [-]
    phi        Bar diameter (equivalent diameter for mixed sizes) [mm]
    rho_p_eff  Effective reinforcement ratio [-]
    """
    return k_3 * c + k_1 * k_2 * k_4 * phi / rho_p_eff


def s_r_max_chain(k_3, c, k_1, k_2, k_4, phi, A_s, h, d, E_s, f_ck, b):
    """s_r,max from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    alpha_e = _alpha_e(E_s, E_cm)
    x_el = _x_el(alpha_e, A_s, b, d)
    h_c_ef = _h_c_ef(h, d, x_el)
    A_c_eff = _A_c_eff(h_c_ef, b)
    rho_p_eff = _rho_p_eff(A_s, A_c_eff)
    return s_r_max(k_3, c, k_1, k_2, k_4, phi, rho_p_eff)
