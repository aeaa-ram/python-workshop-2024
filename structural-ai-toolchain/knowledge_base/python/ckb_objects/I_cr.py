"""I_cr - EN 1992-1-1 cl. 7.3.4, 7.2.  Units: N, mm, MPa, rad."""
# ckb I_cr eafa05c2a139
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .alpha_e import alpha_e as _alpha_e
from .x_el import x_el as _x_el


def I_cr(b, x_el, alpha_e, A_s, d):
    """Second moment of area of the cracked section [mm4]
    EN 1992-1-1 cl. 7.3.4, 7.2
    
    b        Width of the cross-section [mm]
    x_el     Depth of the neutral axis of the cracked section (elastic) [mm]
    alpha_e  Modular ratio E_s / E_cm [-]
    A_s      Area of tension reinforcement [mm2]
    d        Effective depth of the cross-section [mm]
    """
    return b * x_el ** 3 / 3 + alpha_e * A_s * (d - x_el) ** 2


def I_cr_chain(b, E_s, f_ck, A_s, d):
    """I_cr from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    alpha_e = _alpha_e(E_s, E_cm)
    x_el = _x_el(alpha_e, A_s, b, d)
    return I_cr(b, x_el, alpha_e, A_s, d)
