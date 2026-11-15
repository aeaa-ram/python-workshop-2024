"""η_T+V - EN 1992-1-1 cl. 6.3.2(4), expr. (6.29).  Units: N, mm, MPa, rad."""
# ckb util_TV cbe15cffdfe3
from .nu import nu as _nu
from .f_cd import f_cd as _f_cd
from .alpha_cw import alpha_cw as _alpha_cw
from .t_ef_i import t_ef_i as _t_ef_i
from .A_k import A_k as _A_k
from .T_Rd_max import T_Rd_max as _T_Rd_max
from .z_V import z_V as _z_V
from .nu_1 import nu_1 as _nu_1
from .V_Rd_max import V_Rd_max as _V_Rd_max


def util_TV(T_Ed, T_Rd_max, V_Ed, V_Rd_max):
    """Utilisation of the concrete struts under torsion and shear [-]
    EN 1992-1-1 cl. 6.3.2(4), expr. (6.29)
    
    T_Ed      Design torsional moment [Nmm]
    T_Rd_max  Design torsional resistance moment (strut crushing) [Nmm]
    V_Ed      Design shear force [N]
    V_Rd_max  Shear resistance governed by crushing of the compression struts [N]
    """
    return T_Ed / T_Rd_max + V_Ed / V_Rd_max


def util_TV_chain(T_Ed, f_ck, sigma_cp, alpha_cc, gamma_C, b, A_tor, u_out, h, theta, V_Ed, b_w, d):
    """η_T+V from the primary inputs."""
    nu = _nu(f_ck)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    alpha_cw = _alpha_cw(sigma_cp, f_cd)
    t_ef_i = _t_ef_i(A_tor, u_out)
    A_k = _A_k(b, t_ef_i, h)
    T_Rd_max = _T_Rd_max(nu, alpha_cw, f_cd, A_k, t_ef_i, theta)
    z_V = _z_V(d)
    nu_1 = _nu_1(nu)
    V_Rd_max = _V_Rd_max(alpha_cw, b_w, z_V, nu_1, f_cd, theta)
    return util_TV(T_Ed, T_Rd_max, V_Ed, V_Rd_max)
