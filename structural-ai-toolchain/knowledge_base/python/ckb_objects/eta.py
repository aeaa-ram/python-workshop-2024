"""η - EN 1992-1-1 cl. 3.1.7(3), expr. (3.21), (3.22).  Units: N, mm, MPa, rad."""
# ckb eta fd8bcf2287d8


def eta(f_ck):
    """Factor for the effective strength of the compression zone [-]
    EN 1992-1-1 cl. 3.1.7(3), expr. (3.21), (3.22)
    
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 1 if f_ck <= 50 else 1 - (f_ck - 50) / 200
