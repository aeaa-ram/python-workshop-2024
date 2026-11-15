"""n - EN 1992-1-1 cl. 5.8.3.1(1).  Units: N, mm, MPa, rad."""
# ckb n_rel ad8ab7846c4a
from .f_cd import f_cd as _f_cd


def n_rel(N_Ed, A_c, f_cd):
    """Relative normal force [-]
    EN 1992-1-1 cl. 5.8.3.1(1)
    
    N_Ed  Design axial force [N]
    A_c   Cross-sectional area of concrete [mm2]
    f_cd  Design compressive strength of concrete [MPa]
    """
    return N_Ed / (A_c * f_cd)


def n_rel_chain(N_Ed, A_c, alpha_cc, f_ck, gamma_C):
    """n from the primary inputs."""
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    return n_rel(N_Ed, A_c, f_cd)
