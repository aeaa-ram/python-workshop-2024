"""N_pl,a - EN 1994-1-1 cl. 6.2.1.2(1).  Units: N, mm, MPa, rad."""
# ckb N_pl_a 549cf6fb446e
from .f_yd_a import f_yd_a as _f_yd_a


def N_pl_a(A_a, f_yd_a):
    """Plastic resistance of the structural steel section [N]
    EN 1994-1-1 cl. 6.2.1.2(1)
    
    A_a     Cross-sectional area of the structural steel section [mm2]
    f_yd_a  Design yield strength of structural steel [MPa]
    """
    return A_a * f_yd_a


def N_pl_a_chain(A_a, f_y, gamma_M0):
    """N_pl,a from the primary inputs."""
    f_yd_a = _f_yd_a(f_y, gamma_M0)
    return N_pl_a(A_a, f_yd_a)
