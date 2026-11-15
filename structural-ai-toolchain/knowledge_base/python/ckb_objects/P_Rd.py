"""P_Rd - EN 1994-1-1 cl. 6.6.3.1(1), expr. (6.18), (6.19).  Units: N, mm, MPa, rad."""
# ckb P_Rd cf8781dd56b1
from .P_Rd_s import P_Rd_s as _P_Rd_s
from .alpha_stud import alpha_stud as _alpha_stud
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .P_Rd_c import P_Rd_c as _P_Rd_c


def P_Rd(P_Rd_s, P_Rd_c):
    """Design shear resistance of a headed stud in a solid slab [N]
    EN 1994-1-1 cl. 6.6.3.1(1), expr. (6.18), (6.19)
    
    P_Rd_s  Design shear resistance of a headed stud, failure of the shank [N]
    P_Rd_c  Design shear resistance of a headed stud, failure of the concrete [N]
    """
    return min(P_Rd_s, P_Rd_c)


def P_Rd_chain(f_u, d_s, gamma_V, h_sc, f_ck):
    """P_Rd from the primary inputs."""
    P_Rd_s = _P_Rd_s(f_u, d_s, gamma_V)
    alpha_stud = _alpha_stud(h_sc, d_s)
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    P_Rd_c = _P_Rd_c(alpha_stud, d_s, f_ck, E_cm, gamma_V)
    return P_Rd(P_Rd_s, P_Rd_c)
