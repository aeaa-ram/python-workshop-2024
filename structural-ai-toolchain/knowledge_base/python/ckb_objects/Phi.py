"""Φ - EN 1993-1-1 cl. 6.3.1.2(1), expr. (6.49).  Units: N, mm, MPa, rad."""
# ckb Phi 46a763b12e81
from .N_cr import N_cr as _N_cr
from .lambda_bar import lambda_bar as _lambda_bar


def Phi(alpha_imp, lambda_bar):
    """Value to determine the reduction factor χ [-]
    EN 1993-1-1 cl. 6.3.1.2(1), expr. (6.49)
    
    alpha_imp   Imperfection factor of the buckling curve [-]
    lambda_bar  Non-dimensional slenderness for flexural buckling (class 1 to 3) [-]
    """
    return 0.5 * (1 + alpha_imp * (lambda_bar - 0.2) + lambda_bar ** 2)


def Phi_chain(alpha_imp, A_sec, f_y, E_steel, I_sec, L_cr):
    """Φ from the primary inputs."""
    N_cr = _N_cr(E_steel, I_sec, L_cr)
    lambda_bar = _lambda_bar(A_sec, f_y, N_cr)
    return Phi(alpha_imp, lambda_bar)
