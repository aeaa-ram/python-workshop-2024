"""k - EN 1992-1-1 cl. 6.4.4(1).  Units: N, mm, MPa, rad."""
# ckb k_p 23ced03ca5ce
from math import sqrt
from .d_eff_p import d_eff_p as _d_eff_p


def k_p(d_eff_p):
    """Size factor for punching [-]
    EN 1992-1-1 cl. 6.4.4(1)
    
    d_eff_p  Effective depth of the slab for punching [mm]
    """
    return min(1 + sqrt(200 / d_eff_p), 2)


def k_p_chain(d_y, d_z):
    """k from the primary inputs."""
    d_eff_p = _d_eff_p(d_y, d_z)
    return k_p(d_eff_p)
