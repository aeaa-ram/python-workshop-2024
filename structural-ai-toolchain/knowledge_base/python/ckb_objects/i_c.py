"""i - EN 1992-1-1 cl. 5.8.3.2(1).  Units: N, mm, MPa, rad."""
# ckb i_c b6466bef40c7
from math import sqrt


def i_c(I_conc, A_c):
    """Radius of gyration of the uncracked concrete section [mm]
    EN 1992-1-1 cl. 5.8.3.2(1)
    
    I_conc  Second moment of area of the concrete section [mm4]
    A_c     Cross-sectional area of concrete [mm2]
    """
    return sqrt(I_conc / A_c)
