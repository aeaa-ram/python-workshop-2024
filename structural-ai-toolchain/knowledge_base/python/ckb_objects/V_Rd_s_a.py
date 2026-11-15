"""V_Rd,s - EN 1992-1-1 cl. 6.2.3(4), expr. (6.13).  Units: N, mm, MPa, rad."""
# ckb V_Rd_s_a 91f59b03c0f9
from math import sin, tan
from .z_V import z_V as _z_V
from .f_ywd import f_ywd as _f_ywd


def cot(x):
    return 1.0 / tan(x)


def V_Rd_s_a(A_sw, s, z_V, f_ywd, theta, alpha):
    """Shear resistance of inclined shear reinforcement [N]
    EN 1992-1-1 cl. 6.2.3(4), expr. (6.13)
    
    A_sw   Cross-sectional area of the shear reinforcement [mm2]
    s      Spacing of the stirrups [mm]
    z_V    Inner lever arm for shear [mm]
    f_ywd  Design yield strength of the shear reinforcement [MPa]
    theta  Angle between the concrete strut and the member axis [rad]
    alpha  Angle between the shear reinforcement and the member axis [rad]
    """
    return A_sw / s * z_V * f_ywd * (cot(theta) + cot(alpha)) * sin(alpha)


def V_Rd_s_a_chain(A_sw, s, d, f_ywk, gamma_S, theta, alpha):
    """V_Rd,s from the primary inputs."""
    z_V = _z_V(d)
    f_ywd = _f_ywd(f_ywk, gamma_S)
    return V_Rd_s_a(A_sw, s, z_V, f_ywd, theta, alpha)
