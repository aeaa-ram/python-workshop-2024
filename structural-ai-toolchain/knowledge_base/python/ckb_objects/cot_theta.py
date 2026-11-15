"""cot θ - .  Units: N, mm, MPa, rad."""
# ckb cot_theta 84e570e2de92
from math import tan


def cot(x):
    return 1.0 / tan(x)


def cot_theta(theta):
    """Cotangent of the strut angle [-]
    
    
    theta  Angle between the concrete strut and the member axis [rad]
    """
    return cot(theta)
