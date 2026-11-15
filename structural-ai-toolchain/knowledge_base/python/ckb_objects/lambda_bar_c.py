"""λ̄ - EN 1994-1-1 cl. 6.7.3.3(2), expr. (6.39).  Units: N, mm, MPa, rad."""
# ckb lambda_bar_c 2b39d6b65e9b
from math import sqrt
from .N_pl_Rk import N_pl_Rk as _N_pl_Rk
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .EI_eff import EI_eff as _EI_eff
from .N_cr_c import N_cr_c as _N_cr_c


def lambda_bar_c(N_pl_Rk, N_cr_c):
    """Relative slenderness of a composite column [-]
    EN 1994-1-1 cl. 6.7.3.3(2), expr. (6.39)
    
    N_pl_Rk  Characteristic plastic resistance to compression of a composite section [N]
    N_cr_c   Elastic critical normal force of a composite column [N]
    """
    return sqrt(N_pl_Rk / N_cr_c)


def lambda_bar_c_chain(A_a, f_y, A_c, f_ck, A_s, f_yk, E_steel, I_a, I_s, K_e, I_conc, L_cr):
    """λ̄ from the primary inputs."""
    N_pl_Rk = _N_pl_Rk(A_a, f_y, A_c, f_ck, A_s, f_yk)
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    EI_eff = _EI_eff(E_steel, I_a, I_s, K_e, E_cm, I_conc)
    N_cr_c = _N_cr_c(EI_eff, L_cr)
    return lambda_bar_c(N_pl_Rk, N_cr_c)
