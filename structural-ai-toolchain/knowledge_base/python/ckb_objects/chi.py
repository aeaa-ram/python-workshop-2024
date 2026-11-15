"""χ - EN 1993-1-1 cl. 6.3.1.2(1), expr. (6.49).  Units: N, mm, MPa, rad."""
# ckb chi 648616e273ff
from math import sqrt
from .N_cr import N_cr as _N_cr
from .lambda_bar import lambda_bar as _lambda_bar
from .Phi import Phi as _Phi


def chi(Phi, lambda_bar):
    """Reduction factor for flexural buckling [-]
    EN 1993-1-1 cl. 6.3.1.2(1), expr. (6.49)
    
    Phi         Value to determine the reduction factor χ [-]
    lambda_bar  Non-dimensional slenderness for flexural buckling (class 1 to 3) [-]
    """
    return min(1 / (Phi + sqrt(Phi ** 2 - lambda_bar ** 2)), 1)


def chi_chain(alpha_imp, A_sec, f_y, E_steel, I_sec, L_cr):
    """χ from the primary inputs."""
    N_cr = _N_cr(E_steel, I_sec, L_cr)
    lambda_bar = _lambda_bar(A_sec, f_y, N_cr)
    Phi = _Phi(alpha_imp, lambda_bar)
    return chi(Phi, lambda_bar)
