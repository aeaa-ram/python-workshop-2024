"""ρ_w,min - EN 1992-1-1 cl. 9.2.2(5), expr. (9.5N).  Units: N, mm, MPa, rad."""
# ckb rho_w_min be39127a538c
from math import sqrt


def rho_w_min(f_ck, f_yk):
    """Minimum shear reinforcement ratio [-]
    EN 1992-1-1 cl. 9.2.2(5), expr. (9.5N)
    
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    f_yk  Characteristic yield strength of reinforcement [MPa]
    """
    return 0.08 * sqrt(f_ck) / f_yk
