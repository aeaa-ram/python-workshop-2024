"""Φ_LT - EN 1993-1-1 cl. 6.3.2.2(1), expr. (6.56).  Units: N, mm, MPa, rad."""
# ckb Phi_LT 62ae43bb3350
from .lambda_bar_LT import lambda_bar_LT as _lambda_bar_LT


def Phi_LT(alpha_LT, lambda_bar_LT):
    """Value to determine the reduction factor χ_LT (general case) [-]
    EN 1993-1-1 cl. 6.3.2.2(1), expr. (6.56)
    
    alpha_LT       Imperfection factor for lateral-torsional buckling [-]
    lambda_bar_LT  Non-dimensional slenderness for lateral-torsional buckling [-]
    """
    return 0.5 * (1 + alpha_LT * (lambda_bar_LT - 0.2) + lambda_bar_LT ** 2)


def Phi_LT_chain(alpha_LT, W_y, f_y, M_cr):
    """Φ_LT from the primary inputs."""
    lambda_bar_LT = _lambda_bar_LT(W_y, f_y, M_cr)
    return Phi_LT(alpha_LT, lambda_bar_LT)
