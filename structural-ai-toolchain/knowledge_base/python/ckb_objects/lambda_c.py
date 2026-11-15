"""λ - EN 1992-1-1 cl. 5.8.3.2(1), expr. (5.14).  Units: N, mm, MPa, rad."""
# ckb lambda_c 5519345f64be
from .i_c import i_c as _i_c


def lambda_c(l_0, i_c):
    """Slenderness ratio of the column [-]
    EN 1992-1-1 cl. 5.8.3.2(1), expr. (5.14)
    
    l_0  Effective length of the column [mm]
    i_c  Radius of gyration of the uncracked concrete section [mm]
    """
    return l_0 / i_c


def lambda_c_chain(l_0, I_conc, A_c):
    """λ from the primary inputs."""
    i_c = _i_c(I_conc, A_c)
    return lambda_c(l_0, i_c)
