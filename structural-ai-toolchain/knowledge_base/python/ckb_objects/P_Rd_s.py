"""P_Rd,s - EN 1994-1-1 cl. 6.6.3.1(1), expr. (6.18).  Units: N, mm, MPa, rad."""
# ckb P_Rd_s 163816a4aa57
from math import pi


def P_Rd_s(f_u, d_s, gamma_V):
    """Design shear resistance of a headed stud, failure of the shank [N]
    EN 1994-1-1 cl. 6.6.3.1(1), expr. (6.18)
    
    f_u      Ultimate tensile strength of the steel (plate, section or stud material) [MPa]
    d_s      Diameter of the shank of the stud [mm]
    gamma_V  Partial factor for design shear resistance of a headed stud [-]
    """
    return 0.8 * f_u * pi * d_s ** 2 / 4 / gamma_V
