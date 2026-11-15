"""A_sw,max - EN 1992-1-1 cl. 6.2.3(3), expr. (6.12).  Units: N, mm, MPa, rad."""
# ckb A_sw_max 1e28e7a601b5
from .f_cd import f_cd as _f_cd
from .alpha_cw import alpha_cw as _alpha_cw
from .nu import nu as _nu
from .nu_1 import nu_1 as _nu_1
from .f_ywd import f_ywd as _f_ywd


def A_sw_max(alpha_cw, nu_1, f_cd, b_w, s, f_ywd):
    """Maximum effective area of vertical shear reinforcement (cot θ = 1) [mm2]
    EN 1992-1-1 cl. 6.2.3(3), expr. (6.12)
    
    alpha_cw  Coefficient for the state of stress in the compression chord [-]
    nu_1      Strength reduction factor for concrete cracked in shear (strut) [-]
    f_cd      Design compressive strength of concrete [MPa]
    b_w       Smallest width of the cross-section in the tensile area [mm]
    s         Spacing of the stirrups [mm]
    f_ywd     Design yield strength of the shear reinforcement [MPa]
    """
    return 0.5 * alpha_cw * nu_1 * f_cd * b_w * s / f_ywd


def A_sw_max_chain(sigma_cp, alpha_cc, f_ck, gamma_C, b_w, s, f_ywk, gamma_S):
    """A_sw,max from the primary inputs."""
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    alpha_cw = _alpha_cw(sigma_cp, f_cd)
    nu = _nu(f_ck)
    nu_1 = _nu_1(nu)
    f_ywd = _f_ywd(f_ywk, gamma_S)
    return A_sw_max(alpha_cw, nu_1, f_cd, b_w, s, f_ywd)
