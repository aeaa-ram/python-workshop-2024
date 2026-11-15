"""A_sw/s - EN 1992-1-1 cl. 6.3.2(2), expr. (6.26).  Units: N, mm, MPa, rad."""
# ckb asw_s_T f6f1e8732588
from math import tan
from .t_ef_i import t_ef_i as _t_ef_i
from .A_k import A_k as _A_k
from .f_ywd import f_ywd as _f_ywd


def cot(x):
    return 1.0 / tan(x)


def asw_s_T(T_Ed, A_k, f_ywd, theta):
    """Area of closed links per unit length required for torsion [mm]
    EN 1992-1-1 cl. 6.3.2(2), expr. (6.26)
    
    T_Ed   Design torsional moment [Nmm]
    A_k    Area enclosed by the centre-lines of the connecting walls (rectangular section) [mm2]
    f_ywd  Design yield strength of the shear reinforcement [MPa]
    theta  Angle between the concrete strut and the member axis [rad]
    """
    return T_Ed / (2 * A_k * f_ywd * cot(theta))


def asw_s_T_chain(T_Ed, b, A_tor, u_out, h, f_ywk, gamma_S, theta):
    """A_sw/s from the primary inputs."""
    t_ef_i = _t_ef_i(A_tor, u_out)
    A_k = _A_k(b, t_ef_i, h)
    f_ywd = _f_ywd(f_ywk, gamma_S)
    return asw_s_T(T_Ed, A_k, f_ywd, theta)
