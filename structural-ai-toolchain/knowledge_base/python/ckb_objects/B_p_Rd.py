"""B_p,Rd - EN 1993-1-8 cl. 3.6.1(1), Table 3.4.  Units: N, mm, MPa, rad."""
# ckb B_p_Rd 3bf128b5527c
from math import pi


def B_p_Rd(d_m, t_plate, f_u, gamma_M2):
    """Punching shear resistance of the plate under the bolt head or nut [N]
    EN 1993-1-8 cl. 3.6.1(1), Table 3.4
    
    d_m       Mean of the across-points and across-flats dimensions of the bolt head or nut [mm]
    t_plate   Thickness of the connected part [mm]
    f_u       Ultimate tensile strength of the steel (plate, section or stud material) [MPa]
    gamma_M2  Partial factor for resistance of cross-sections in tension to fracture, and of bolts and welds [-]
    """
    return 0.6 * pi * d_m * t_plate * f_u / gamma_M2
