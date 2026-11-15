"""N_pl,Rd - EN 1993-1-1 cl. 6.2.3(2), 6.2.4(2), expr. (6.6), (6.10).  Units: N, mm, MPa, rad."""
# ckb N_pl_Rd_a 330d436ac46d


def N_pl_Rd_a(A_sec, f_y, gamma_M0):
    """Design plastic resistance of the gross steel section (tension; compression of class 1 to 3) [N]
    EN 1993-1-1 cl. 6.2.3(2), 6.2.4(2), expr. (6.6), (6.10)
    
    A_sec     Cross-sectional area of the steel section [mm2]
    f_y       Nominal yield strength of structural steel [MPa]
    gamma_M0  Partial factor for resistance of cross-sections [-]
    """
    return A_sec * f_y / gamma_M0
