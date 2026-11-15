"""f_vw,d - EN 1993-1-8 cl. 4.5.3.3(3), expr. (4.4).  Units: N, mm, MPa, rad."""
# ckb f_vw_d 87380314f729
from math import sqrt


def f_vw_d(f_u, beta_w, gamma_M2):
    """Design shear strength of a fillet weld [MPa]
    EN 1993-1-8 cl. 4.5.3.3(3), expr. (4.4)
    
    f_u       Ultimate tensile strength of the steel (plate, section or stud material) [MPa]
    beta_w    Correlation factor for fillet welds [-]
    gamma_M2  Partial factor for resistance of cross-sections in tension to fracture, and of bolts and welds [-]
    """
    return f_u / sqrt(3) / (beta_w * gamma_M2)
