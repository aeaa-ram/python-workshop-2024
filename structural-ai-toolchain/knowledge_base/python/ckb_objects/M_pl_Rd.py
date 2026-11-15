"""M_pl,Rd - EN 1993-1-1 cl. 6.2.5(2), expr. (6.13).  Units: N, mm, MPa, rad."""
# ckb M_pl_Rd 252b7226be4a


def M_pl_Rd(W_pl, f_y, gamma_M0):
    """Design plastic moment resistance (class 1 and 2) [Nmm]
    EN 1993-1-1 cl. 6.2.5(2), expr. (6.13)
    
    W_pl      Plastic section modulus [mm³]
    f_y       Nominal yield strength of structural steel [MPa]
    gamma_M0  Partial factor for resistance of cross-sections [-]
    """
    return W_pl * f_y / gamma_M0
