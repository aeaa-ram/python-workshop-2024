"""σ_c - EN 1992-1-1 cl. 7.2(2), 7.2(3).  Units: N, mm, MPa, rad."""
# ckb sigma_c 3a62c3cc11fe
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .alpha_e import alpha_e as _alpha_e
from .x_el import x_el as _x_el
from .I_cr import I_cr as _I_cr


def sigma_c(M_SLS, x_el, I_cr):
    """Compressive stress in the concrete assuming a cracked section [MPa]
    EN 1992-1-1 cl. 7.2(2), 7.2(3)
    
    M_SLS  Bending moment in the serviceability combination considered [Nmm]
    x_el   Depth of the neutral axis of the cracked section (elastic) [mm]
    I_cr   Second moment of area of the cracked section [mm4]
    """
    return M_SLS * x_el / I_cr


def sigma_c_chain(M_SLS, E_s, f_ck, A_s, b, d):
    """σ_c from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    alpha_e = _alpha_e(E_s, E_cm)
    x_el = _x_el(alpha_e, A_s, b, d)
    I_cr = _I_cr(b, x_el, alpha_e, A_s, d)
    return sigma_c(M_SLS, x_el, I_cr)
