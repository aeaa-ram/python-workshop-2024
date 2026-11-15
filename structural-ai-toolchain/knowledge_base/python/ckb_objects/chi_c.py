"""χ - EN 1994-1-1 cl. 6.7.3.5(2).  Units: N, mm, MPa, rad."""
# ckb chi_c 34deb08f42d1
from math import sqrt
from .N_pl_Rk import N_pl_Rk as _N_pl_Rk
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .EI_eff import EI_eff as _EI_eff
from .N_cr_c import N_cr_c as _N_cr_c
from .lambda_bar_c import lambda_bar_c as _lambda_bar_c
from .Phi_c import Phi_c as _Phi_c


def chi_c(Phi_c, lambda_bar_c):
    """Reduction factor for flexural buckling of a composite column [-]
    EN 1994-1-1 cl. 6.7.3.5(2)
    
    Phi_c         Value to determine χ for a composite column [-]
    lambda_bar_c  Relative slenderness of a composite column [-]
    """
    return min(1 / (Phi_c + sqrt(Phi_c ** 2 - lambda_bar_c ** 2)), 1)


def chi_c_chain(alpha_imp, A_a, f_y, A_c, f_ck, A_s, f_yk, E_steel, I_a, I_s, K_e, I_conc, L_cr):
    """χ from the primary inputs."""
    N_pl_Rk = _N_pl_Rk(A_a, f_y, A_c, f_ck, A_s, f_yk)
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    EI_eff = _EI_eff(E_steel, I_a, I_s, K_e, E_cm, I_conc)
    N_cr_c = _N_cr_c(EI_eff, L_cr)
    lambda_bar_c = _lambda_bar_c(N_pl_Rk, N_cr_c)
    Phi_c = _Phi_c(alpha_imp, lambda_bar_c)
    return chi_c(Phi_c, lambda_bar_c)
