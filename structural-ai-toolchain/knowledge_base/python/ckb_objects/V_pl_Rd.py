"""V_pl,Rd - EN 1993-1-1 cl. 6.2.6(2), expr. (6.18).  Units: N, mm, MPa, rad."""
# ckb V_pl_Rd f601d6fa6cd4
from math import sqrt


def V_pl_Rd(A_v, f_y, gamma_M0):
    """Design plastic shear resistance [N]
    EN 1993-1-1 cl. 6.2.6(2), expr. (6.18)
    
    A_v       Shear area of the steel section [mm2]
    f_y       Nominal yield strength of structural steel [MPa]
    gamma_M0  Partial factor for resistance of cross-sections [-]
    """
    return A_v * f_y / sqrt(3) / gamma_M0
