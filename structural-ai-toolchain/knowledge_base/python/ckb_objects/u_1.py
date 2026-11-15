"""u_1 - EN 1992-1-1 cl. 6.4.2(1).  Units: N, mm, MPa, rad."""
# ckb u_1 47d68a402424
from math import pi
from .d_eff_p import d_eff_p as _d_eff_p


def u_1(c_1, c_2, d_eff_p):
    """Basic control perimeter at 2d from a rectangular internal column [mm]
    EN 1992-1-1 cl. 6.4.2(1)
    
    c_1      Column dimension parallel to the eccentricity (punching) [mm]
    c_2      Column dimension perpendicular to the eccentricity (punching) [mm]
    d_eff_p  Effective depth of the slab for punching [mm]
    """
    return 2 * (c_1 + c_2) + 4 * pi * d_eff_p


def u_1_chain(c_1, c_2, d_y, d_z):
    """u_1 from the primary inputs."""
    d_eff_p = _d_eff_p(d_y, d_z)
    return u_1(c_1, c_2, d_eff_p)
