"""h_c,ef - EN 1992-1-1 cl. 7.3.2(3).  Units: N, mm, MPa, rad."""
# ckb h_c_ef a75fff138f75
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .alpha_e import alpha_e as _alpha_e
from .x_el import x_el as _x_el


def h_c_ef(h, d, x_el):
    """Effective height of the concrete tension zone [mm]
    EN 1992-1-1 cl. 7.3.2(3)
    
    h     Overall depth of the cross-section [mm]
    d     Effective depth of the cross-section [mm]
    x_el  Depth of the neutral axis of the cracked section (elastic) [mm]
    """
    return min(2.5 * (h - d), (h - x_el) / 3, h / 2)


def h_c_ef_chain(h, d, E_s, f_ck, A_s, b):
    """h_c,ef from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    alpha_e = _alpha_e(E_s, E_cm)
    x_el = _x_el(alpha_e, A_s, b, d)
    return h_c_ef(h, d, x_el)
