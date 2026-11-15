"""s_l,max - EN 1992-1-1 cl. 9.2.2(6), expr. (9.6N).  Units: N, mm, MPa, rad."""
# ckb s_l_max 3e20eec2a6a1
from math import tan


def cot(x):
    return 1.0 / tan(x)


def s_l_max(d, alpha):
    """Maximum longitudinal spacing of shear assemblies [mm]
    EN 1992-1-1 cl. 9.2.2(6), expr. (9.6N)
    
    d      Effective depth of the cross-section [mm]
    alpha  Angle between the shear reinforcement and the member axis [rad]
    """
    return 0.75 * d * (1 + cot(alpha))
