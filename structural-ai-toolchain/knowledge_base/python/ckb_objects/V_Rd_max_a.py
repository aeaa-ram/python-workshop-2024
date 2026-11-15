"""V_Rd,max - EN 1992-1-1 cl. 6.2.3(4), expr. (6.14).  Units: N, mm, MPa, rad."""
# ckb V_Rd_max_a c323c9a90950
from math import tan
from .f_cd import f_cd as _f_cd
from .alpha_cw import alpha_cw as _alpha_cw
from .z_V import z_V as _z_V
from .nu import nu as _nu
from .nu_1 import nu_1 as _nu_1


def cot(x):
    return 1.0 / tan(x)


def V_Rd_max_a(alpha_cw, b_w, z_V, nu_1, f_cd, theta, alpha):
    """Strut crushing resistance with inclined shear reinforcement [N]
    EN 1992-1-1 cl. 6.2.3(4), expr. (6.14)
    
    alpha_cw  Coefficient for the state of stress in the compression chord [-]
    b_w       Smallest width of the cross-section in the tensile area [mm]
    z_V       Inner lever arm for shear [mm]
    nu_1      Strength reduction factor for concrete cracked in shear (strut) [-]
    f_cd      Design compressive strength of concrete [MPa]
    theta     Angle between the concrete strut and the member axis [rad]
    alpha     Angle between the shear reinforcement and the member axis [rad]
    """
    return alpha_cw * b_w * z_V * nu_1 * f_cd * (cot(theta) + cot(alpha)) / (1 + cot(theta) ** 2)


def V_Rd_max_a_chain(sigma_cp, alpha_cc, f_ck, gamma_C, b_w, d, theta, alpha):
    """V_Rd,max from the primary inputs."""
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    alpha_cw = _alpha_cw(sigma_cp, f_cd)
    z_V = _z_V(d)
    nu = _nu(f_ck)
    nu_1 = _nu_1(nu)
    return V_Rd_max_a(alpha_cw, b_w, z_V, nu_1, f_cd, theta, alpha)
