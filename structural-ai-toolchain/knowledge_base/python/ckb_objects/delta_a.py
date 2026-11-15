"""δ - EN 1994-1-1 cl. 6.7.1(4), expr. (6.38).  Units: N, mm, MPa, rad."""
# ckb delta_a 3bf329c2ad4e
from .f_yd_a import f_yd_a as _f_yd_a
from .f_cd import f_cd as _f_cd
from .f_yd import f_yd as _f_yd
from .N_pl_Rd import N_pl_Rd as _N_pl_Rd


def delta_a(A_a, f_yd_a, N_pl_Rd):
    """Steel contribution ratio of a composite column [-]
    EN 1994-1-1 cl. 6.7.1(4), expr. (6.38)
    
    A_a      Cross-sectional area of the structural steel section [mm2]
    f_yd_a   Design yield strength of structural steel [MPa]
    N_pl_Rd  Plastic resistance to compression of a composite cross-section [N]
    α_cc = 1 in EN 1994-1-1
    """
    return A_a * f_yd_a / N_pl_Rd


def delta_a_chain(A_a, f_y, gamma_M0, A_c, f_ck, gamma_C, A_s, f_yk, gamma_S):
    """δ from the primary inputs."""
    alpha_cc = 1
    f_yd_a = _f_yd_a(f_y, gamma_M0)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    f_yd = _f_yd(f_yk, gamma_S)
    N_pl_Rd = _N_pl_Rd(A_a, f_yd_a, A_c, f_cd, A_s, f_yd)
    return delta_a(A_a, f_yd_a, N_pl_Rd)
