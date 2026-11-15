"""α_b - EN 1993-1-8 cl. 3.6.1(1), Table 3.4.  Units: N, mm, MPa, rad."""
# ckb alpha_b b0b2cb09ea5a
from .alpha_d import alpha_d as _alpha_d


def alpha_b(alpha_d, f_ub, f_u):
    """Factor for bearing in the direction of load transfer [-]
    EN 1993-1-8 cl. 3.6.1(1), Table 3.4
    
    alpha_d  Factor for the end distance (end bolts, bearing) [-]
    f_ub     Ultimate tensile strength of the bolt [MPa]
    f_u      Ultimate tensile strength of the steel (plate, section or stud material) [MPa]
    """
    return min(alpha_d, f_ub / f_u, 1)


def alpha_b_chain(e_1, d_0, f_ub, f_u):
    """α_b from the primary inputs."""
    alpha_d = _alpha_d(e_1, d_0)
    return alpha_b(alpha_d, f_ub, f_u)
