"""V_Rd,s - EN 1992-1-1 cl. 6.2.3(3), expr. (6.8).  Units: N, mm, MPa, rad."""
# ckb V_Rd_s 35938a61a10b
from math import tan
from .z_V import z_V as _z_V
from .f_ywd import f_ywd as _f_ywd


def cot(x):
    return 1.0 / tan(x)


def V_Rd_s(A_sw, s, z_V, f_ywd, theta):
    """Shear resistance governed by yielding of the shear reinforcement [N]
    EN 1992-1-1 cl. 6.2.3(3), expr. (6.8)
    
    A_sw   Cross-sectional area of the shear reinforcement [mm2]
    s      Spacing of the stirrups [mm]
    z_V    Inner lever arm for shear [mm]
    f_ywd  Design yield strength of the shear reinforcement [MPa]
    theta  Angle between the concrete strut and the member axis [rad]
    """
    return A_sw / s * z_V * f_ywd * cot(theta)


def V_Rd_s_chain(A_sw, s, d, f_ywk, gamma_S, theta):
    """V_Rd,s from the primary inputs."""
    z_V = _z_V(d)
    f_ywd = _f_ywd(f_ywk, gamma_S)
    return V_Rd_s(A_sw, s, z_V, f_ywd, theta)
