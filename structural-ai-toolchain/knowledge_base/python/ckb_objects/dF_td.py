"""ΔF_td - EN 1992-1-1 cl. 6.2.3(7), expr. (6.18).  Units: N, mm, MPa, rad."""
# ckb dF_td 22ef6a39ce3e
from math import tan


def cot(x):
    return 1.0 / tan(x)


def dF_td(V_Ed, theta, alpha):
    """Additional tensile force in the longitudinal reinforcement due to shear [N]
    EN 1992-1-1 cl. 6.2.3(7), expr. (6.18)
    
    V_Ed   Design shear force [N]
    theta  Angle between the concrete strut and the member axis [rad]
    alpha  Angle between the shear reinforcement and the member axis [rad]
    """
    return 0.5 * V_Ed * (cot(theta) - cot(alpha))
