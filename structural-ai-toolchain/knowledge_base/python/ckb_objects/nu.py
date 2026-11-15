"""ν - EN 1992-1-1 cl. 6.2.2(6), expr. (6.6N).  Units: N, mm, MPa, rad."""
# ckb nu 4b2658657817


def nu(f_ck):
    """Strength reduction factor for concrete cracked in shear [-]
    EN 1992-1-1 cl. 6.2.2(6), expr. (6.6N)
    
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 0.6 * (1 - f_ck / 250)
