"""x_el - EN 1992-1-1 cl. 7.3.4, 7.2.  Units: N, mm, MPa, rad."""
# ckb x_el f3c9b7b30a95
from math import sqrt
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .alpha_e import alpha_e as _alpha_e


def x_el(alpha_e, A_s, b, d):
    """Depth of the neutral axis of the cracked section (elastic) [mm]
    EN 1992-1-1 cl. 7.3.4, 7.2
    
    alpha_e  Modular ratio E_s / E_cm [-]
    A_s      Area of tension reinforcement [mm2]
    b        Width of the cross-section [mm]
    d        Effective depth of the cross-section [mm]
    """
    return (sqrt((alpha_e * A_s) ** 2 + 2 * b * alpha_e * A_s * d) - alpha_e * A_s) / b


def x_el_chain(E_s, f_ck, A_s, b, d):
    """x_el from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    alpha_e = _alpha_e(E_s, E_cm)
    return x_el(alpha_e, A_s, b, d)
