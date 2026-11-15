"""A_c,eff - EN 1992-1-1 cl. 7.3.2(3).  Units: N, mm, MPa, rad."""
# ckb A_c_eff 4a7da28af950
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .alpha_e import alpha_e as _alpha_e
from .x_el import x_el as _x_el
from .h_c_ef import h_c_ef as _h_c_ef


def A_c_eff(h_c_ef, b):
    """Effective area of concrete in tension around the reinforcement [mm2]
    EN 1992-1-1 cl. 7.3.2(3)
    
    h_c_ef  Effective height of the concrete tension zone [mm]
    b       Width of the cross-section [mm]
    """
    return h_c_ef * b


def A_c_eff_chain(h, d, E_s, f_ck, A_s, b):
    """A_c,eff from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    alpha_e = _alpha_e(E_s, E_cm)
    x_el = _x_el(alpha_e, A_s, b, d)
    h_c_ef = _h_c_ef(h, d, x_el)
    return A_c_eff(h_c_ef, b)
