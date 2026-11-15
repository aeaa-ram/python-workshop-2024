"""f_yd - EN 1994-1-1 cl. 2.4.1.2(4).  Units: N, mm, MPa, rad."""
# ckb f_yd_a b959c6a36037


def f_yd_a(f_y, gamma_M0):
    """Design yield strength of structural steel [MPa]
    EN 1994-1-1 cl. 2.4.1.2(4)
    
    f_y       Nominal yield strength of structural steel [MPa]
    gamma_M0  Partial factor for resistance of cross-sections [-]
    """
    return f_y / gamma_M0
