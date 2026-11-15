"""χ_LT - EN 1993-1-1 cl. 6.3.2.2(1), expr. (6.56).  Units: N, mm, MPa, rad."""
# ckb chi_LT fe3f5ade3090
from math import sqrt
from .lambda_bar_LT import lambda_bar_LT as _lambda_bar_LT
from .Phi_LT import Phi_LT as _Phi_LT


def chi_LT(Phi_LT, lambda_bar_LT):
    """Reduction factor for lateral-torsional buckling (general case) [-]
    EN 1993-1-1 cl. 6.3.2.2(1), expr. (6.56)
    
    Phi_LT         Value to determine the reduction factor χ_LT (general case) [-]
    lambda_bar_LT  Non-dimensional slenderness for lateral-torsional buckling [-]
    """
    return min(1 / (Phi_LT + sqrt(Phi_LT ** 2 - lambda_bar_LT ** 2)), 1)


def chi_LT_chain(alpha_LT, W_y, f_y, M_cr):
    """χ_LT from the primary inputs."""
    lambda_bar_LT = _lambda_bar_LT(W_y, f_y, M_cr)
    Phi_LT = _Phi_LT(alpha_LT, lambda_bar_LT)
    return chi_LT(Phi_LT, lambda_bar_LT)
