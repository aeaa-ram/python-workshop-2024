"""f_cm - EN 1992-1-1 cl. 3.1.2, Table 3.1.  Units: N, mm, MPa, rad."""
# ckb f_cm 2c2f6541846c


def f_cm(f_ck):
    """Mean compressive cylinder strength of concrete at 28 days [MPa]
    EN 1992-1-1 cl. 3.1.2, Table 3.1
    
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return f_ck + 8
