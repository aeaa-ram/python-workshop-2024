"""ρ_w - EN 1992-1-1 cl. 9.2.2(5), expr. (9.4).  Units: N, mm, MPa, rad."""
# ckb rho_w b81ed25a820b
from math import sin


def rho_w(A_sw, s, b_w, alpha):
    """Shear reinforcement ratio [-]
    EN 1992-1-1 cl. 9.2.2(5), expr. (9.4)
    
    A_sw   Cross-sectional area of the shear reinforcement [mm2]
    s      Spacing of the stirrups [mm]
    b_w    Smallest width of the cross-section in the tensile area [mm]
    alpha  Angle between the shear reinforcement and the member axis [rad]
    """
    return A_sw / (s * b_w * sin(alpha))
