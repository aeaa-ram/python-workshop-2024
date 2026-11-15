"""M_el,Rd - EN 1993-1-1 cl. 6.2.5(2), expr. (6.14).  Units: N, mm, MPa, rad."""
# ckb M_el_Rd 3a88e9bcdbd5


def M_el_Rd(W_el, f_y, gamma_M0):
    """Design elastic moment resistance (class 3) [Nmm]
    EN 1993-1-1 cl. 6.2.5(2), expr. (6.14)
    
    W_el      Elastic section modulus (the smaller value) [mm³]
    f_y       Nominal yield strength of structural steel [MPa]
    gamma_M0  Partial factor for resistance of cross-sections [-]
    """
    return W_el * f_y / gamma_M0
