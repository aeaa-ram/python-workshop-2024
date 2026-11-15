"""f_cd - EN 1992-1-1 cl. 3.1.6(1), expr. (3.15).  Units: N, mm, MPa, rad."""
# ckb f_cd d67592c9a9f0


def f_cd(alpha_cc, f_ck, gamma_C):
    """Design compressive strength of concrete [MPa]
    EN 1992-1-1 cl. 3.1.6(1), expr. (3.15)
    
    alpha_cc  Coefficient for long-term effects on the compressive strength [-]
    f_ck      Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    gamma_C   Partial factor for concrete [-]
    """
    return alpha_cc * f_ck / gamma_C
