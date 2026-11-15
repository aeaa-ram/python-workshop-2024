"""k - EN 1992-1-1 cl. 6.2.2(1).  Units: N, mm, MPa, rad."""
# ckb k b0163741b699
from math import sqrt


def k(d):
    """Size factor for shear [-]
    EN 1992-1-1 cl. 6.2.2(1)
    
    d  Effective depth of the cross-section [mm]
    """
    return min(1 + sqrt(200 / d), 2)
