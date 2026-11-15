"""λ - EN 1992-1-1 cl. 3.1.7(3), expr. (3.19), (3.20).  Units: N, mm, MPa, rad."""
# ckb lam d1e2ea6ba204


def lam(f_ck):
    """Factor for the effective height of the compression zone [-]
    EN 1992-1-1 cl. 3.1.7(3), expr. (3.19), (3.20)
    
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 0.8 if f_ck <= 50 else 0.8 - (f_ck - 50) / 400
