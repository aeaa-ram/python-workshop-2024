"""ρ_p,eff - EN 1992-1-1 cl. 7.3.4(2), expr. (7.10).  Units: N, mm, MPa, rad."""
# ckb rho_p_eff c186a6a688b7
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .alpha_e import alpha_e as _alpha_e
from .x_el import x_el as _x_el
from .h_c_ef import h_c_ef as _h_c_ef
from .A_c_eff import A_c_eff as _A_c_eff


def rho_p_eff(A_s, A_c_eff):
    """Effective reinforcement ratio [-]
    EN 1992-1-1 cl. 7.3.4(2), expr. (7.10)
    
    A_s      Area of tension reinforcement [mm2]
    A_c_eff  Effective area of concrete in tension around the reinforcement [mm2]
    """
    return A_s / A_c_eff


def rho_p_eff_chain(A_s, h, d, E_s, f_ck, b):
    """ρ_p,eff from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    alpha_e = _alpha_e(E_s, E_cm)
    x_el = _x_el(alpha_e, A_s, b, d)
    h_c_ef = _h_c_ef(h, d, x_el)
    A_c_eff = _A_c_eff(h_c_ef, b)
    return rho_p_eff(A_s, A_c_eff)
