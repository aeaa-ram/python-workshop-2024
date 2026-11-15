"""λ_lim - EN 1992-1-1 cl. 5.8.3.1(1), expr. (5.13N).  Units: N, mm, MPa, rad."""
# ckb lambda_lim 0fa19bb5a12b
from math import sqrt
from .f_cd import f_cd as _f_cd
from .n_rel import n_rel as _n_rel


def lambda_lim(A_phi, B_omega, C_rm, n_rel):
    """Slenderness below which second order effects may be ignored [-]
    EN 1992-1-1 cl. 5.8.3.1(1), expr. (5.13N)
    
    A_phi    Factor A for creep (1/(1 + 0.2 φ_ef)) [-]
    B_omega  Factor B for the mechanical reinforcement ratio (√(1 + 2ω)) [-]
    C_rm     Factor C for the moment ratio (1.7 − r_m) [-]
    n_rel    Relative normal force [-]
    """
    return 20 * A_phi * B_omega * C_rm / sqrt(n_rel)


def lambda_lim_chain(A_phi, B_omega, C_rm, N_Ed, A_c, alpha_cc, f_ck, gamma_C):
    """λ_lim from the primary inputs."""
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    n_rel = _n_rel(N_Ed, A_c, f_cd)
    return lambda_lim(A_phi, B_omega, C_rm, n_rel)
