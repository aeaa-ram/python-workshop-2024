"""M_b,Rd - EN 1993-1-1 cl. 6.3.2.1(3), expr. (6.55).  Units: N, mm, MPa, rad."""
# ckb M_b_Rd 2546e59b0a0b
from .lambda_bar_LT import lambda_bar_LT as _lambda_bar_LT
from .Phi_LT import Phi_LT as _Phi_LT
from .chi_LT import chi_LT as _chi_LT


def M_b_Rd(chi_LT, W_y, f_y, gamma_M1):
    """Design buckling resistance moment (lateral-torsional buckling) [Nmm]
    EN 1993-1-1 cl. 6.3.2.1(3), expr. (6.55)
    
    chi_LT    Reduction factor for lateral-torsional buckling (general case) [-]
    W_y       Section modulus for lateral-torsional buckling (W_pl [mm³]
    f_y       Nominal yield strength of structural steel [MPa]
    gamma_M1  Partial factor for resistance of members to instability [-]
    """
    return chi_LT * W_y * f_y / gamma_M1


def M_b_Rd_chain(alpha_LT, W_y, f_y, M_cr, gamma_M1):
    """M_b,Rd from the primary inputs."""
    lambda_bar_LT = _lambda_bar_LT(W_y, f_y, M_cr)
    Phi_LT = _Phi_LT(alpha_LT, lambda_bar_LT)
    chi_LT = _chi_LT(Phi_LT, lambda_bar_LT)
    return M_b_Rd(chi_LT, W_y, f_y, gamma_M1)
