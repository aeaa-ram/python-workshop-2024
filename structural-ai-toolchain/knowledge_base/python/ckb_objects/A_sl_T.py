"""ΣA_sl - EN 1992-1-1 cl. 6.3.2(3), expr. (6.28).  Units: N, mm, MPa, rad."""
# ckb A_sl_T e64cb745f714
from math import tan
from .t_ef_i import t_ef_i as _t_ef_i
from .u_k import u_k as _u_k
from .A_k import A_k as _A_k
from .f_yd import f_yd as _f_yd


def cot(x):
    return 1.0 / tan(x)


def A_sl_T(T_Ed, u_k, theta, A_k, f_yd):
    """Longitudinal reinforcement required for torsion [mm2]
    EN 1992-1-1 cl. 6.3.2(3), expr. (6.28)
    
    T_Ed   Design torsional moment [Nmm]
    u_k    Perimeter of the area A_k (rectangular section) [mm]
    theta  Angle between the concrete strut and the member axis [rad]
    A_k    Area enclosed by the centre-lines of the connecting walls (rectangular section) [mm2]
    f_yd   Design yield strength of reinforcement [MPa]
    """
    return T_Ed * u_k * cot(theta) / (2 * A_k * f_yd)


def A_sl_T_chain(T_Ed, b, A_tor, u_out, h, theta, f_yk, gamma_S):
    """ΣA_sl from the primary inputs."""
    t_ef_i = _t_ef_i(A_tor, u_out)
    u_k = _u_k(b, t_ef_i, h)
    A_k = _A_k(b, t_ef_i, h)
    f_yd = _f_yd(f_yk, gamma_S)
    return A_sl_T(T_Ed, u_k, theta, A_k, f_yd)
