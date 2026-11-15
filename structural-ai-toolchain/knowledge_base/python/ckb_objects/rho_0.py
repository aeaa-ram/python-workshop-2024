"""ρ_0 - EN 1992-1-1 cl. 7.4.2(2).  Units: N, mm, MPa, rad."""
# ckb rho_0 aff59a0d367c
from math import sqrt


def rho_0(f_ck):
    """Reference reinforcement ratio [-]
    EN 1992-1-1 cl. 7.4.2(2)
    
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 0.001 * sqrt(f_ck)
