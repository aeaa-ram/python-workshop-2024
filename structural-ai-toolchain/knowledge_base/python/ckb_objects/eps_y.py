"""ε - EN 1993-1-1 cl. 5.5.2, Table 5.2.  Units: N, mm, MPa, rad."""
# ckb eps_y 422b3c56d0a7
from math import sqrt


def eps_y(f_y):
    """Material factor for the classification of cross-sections [-]
    EN 1993-1-1 cl. 5.5.2, Table 5.2
    
    f_y  Nominal yield strength of structural steel [MPa]
    """
    return sqrt(235 / f_y)
