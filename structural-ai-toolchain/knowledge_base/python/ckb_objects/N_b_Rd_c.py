"""χ N_pl,Rd - EN 1994-1-1 cl. 6.7.3.5(2), expr. (6.44).  Units: N, mm, MPa, rad."""
# ckb N_b_Rd_c 6e4f99869e81
from .N_pl_Rk import N_pl_Rk as _N_pl_Rk
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .EI_eff import EI_eff as _EI_eff
from .N_cr_c import N_cr_c as _N_cr_c
from .lambda_bar_c import lambda_bar_c as _lambda_bar_c
from .Phi_c import Phi_c as _Phi_c
from .chi_c import chi_c as _chi_c
from .f_yd_a import f_yd_a as _f_yd_a
from .f_cd import f_cd as _f_cd
from .f_yd import f_yd as _f_yd
from .N_pl_Rd import N_pl_Rd as _N_pl_Rd


def N_b_Rd_c(chi_c, N_pl_Rd):
    """Buckling resistance of a composite column in axial compression [N]
    EN 1994-1-1 cl. 6.7.3.5(2), expr. (6.44)
    
    chi_c    Reduction factor for flexural buckling of a composite column [-]
    N_pl_Rd  Plastic resistance to compression of a composite cross-section [N]
    α_cc = 1 in EN 1994-1-1
    """
    return chi_c * N_pl_Rd


def N_b_Rd_c_chain(alpha_imp, A_a, f_y, A_c, f_ck, A_s, f_yk, E_steel, I_a, I_s, K_e, I_conc, L_cr, gamma_M0, gamma_C, gamma_S):
    """χ N_pl,Rd from the primary inputs."""
    alpha_cc = 1
    N_pl_Rk = _N_pl_Rk(A_a, f_y, A_c, f_ck, A_s, f_yk)
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    EI_eff = _EI_eff(E_steel, I_a, I_s, K_e, E_cm, I_conc)
    N_cr_c = _N_cr_c(EI_eff, L_cr)
    lambda_bar_c = _lambda_bar_c(N_pl_Rk, N_cr_c)
    Phi_c = _Phi_c(alpha_imp, lambda_bar_c)
    chi_c = _chi_c(Phi_c, lambda_bar_c)
    f_yd_a = _f_yd_a(f_y, gamma_M0)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    f_yd = _f_yd(f_yk, gamma_S)
    N_pl_Rd = _N_pl_Rd(A_a, f_yd_a, A_c, f_cd, A_s, f_yd)
    return N_b_Rd_c(chi_c, N_pl_Rd)
