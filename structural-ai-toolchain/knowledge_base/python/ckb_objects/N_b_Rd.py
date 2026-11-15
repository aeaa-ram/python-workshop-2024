"""N_b,Rd - EN 1993-1-1 cl. 6.3.1.1(3), expr. (6.47).  Units: N, mm, MPa, rad."""
# ckb N_b_Rd 094cfbf0f943
from .N_cr import N_cr as _N_cr
from .lambda_bar import lambda_bar as _lambda_bar
from .Phi import Phi as _Phi
from .chi import chi as _chi


def N_b_Rd(chi, A_sec, f_y, gamma_M1):
    """Design buckling resistance of a compression member (class 1 to 3) [N]
    EN 1993-1-1 cl. 6.3.1.1(3), expr. (6.47)
    
    chi       Reduction factor for flexural buckling [-]
    A_sec     Cross-sectional area of the steel section [mm2]
    f_y       Nominal yield strength of structural steel [MPa]
    gamma_M1  Partial factor for resistance of members to instability [-]
    """
    return chi * A_sec * f_y / gamma_M1


def N_b_Rd_chain(alpha_imp, A_sec, f_y, E_steel, I_sec, L_cr, gamma_M1):
    """N_b,Rd from the primary inputs."""
    N_cr = _N_cr(E_steel, I_sec, L_cr)
    lambda_bar = _lambda_bar(A_sec, f_y, N_cr)
    Phi = _Phi(alpha_imp, lambda_bar)
    chi = _chi(Phi, lambda_bar)
    return N_b_Rd(chi, A_sec, f_y, gamma_M1)
