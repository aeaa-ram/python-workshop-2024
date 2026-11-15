"""T_Rd,max - EN 1992-1-1 cl. 6.3.2(4), expr. (6.30).  Units: N, mm, MPa, rad."""
# ckb T_Rd_max 9081699e3729
from math import cos, sin
from .nu import nu as _nu
from .f_cd import f_cd as _f_cd
from .alpha_cw import alpha_cw as _alpha_cw
from .t_ef_i import t_ef_i as _t_ef_i
from .A_k import A_k as _A_k


def T_Rd_max(nu, alpha_cw, f_cd, A_k, t_ef_i, theta):
    """Design torsional resistance moment (strut crushing) [Nmm]
    EN 1992-1-1 cl. 6.3.2(4), expr. (6.30)
    
    nu        Strength reduction factor for concrete cracked in shear [-]
    alpha_cw  Coefficient for the state of stress in the compression chord [-]
    f_cd      Design compressive strength of concrete [MPa]
    A_k       Area enclosed by the centre-lines of the connecting walls (rectangular section) [mm2]
    t_ef_i    Effective wall thickness for torsion [mm]
    theta     Angle between the concrete strut and the member axis [rad]
    """
    return 2 * nu * alpha_cw * f_cd * A_k * t_ef_i * sin(theta) * cos(theta)


def T_Rd_max_chain(f_ck, sigma_cp, alpha_cc, gamma_C, b, A_tor, u_out, h, theta):
    """T_Rd,max from the primary inputs."""
    nu = _nu(f_ck)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    alpha_cw = _alpha_cw(sigma_cp, f_cd)
    t_ef_i = _t_ef_i(A_tor, u_out)
    A_k = _A_k(b, t_ef_i, h)
    return T_Rd_max(nu, alpha_cw, f_cd, A_k, t_ef_i, theta)
