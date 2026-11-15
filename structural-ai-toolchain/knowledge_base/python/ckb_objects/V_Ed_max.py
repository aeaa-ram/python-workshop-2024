"""V_Ed,max - EN 1992-1-1 cl. 6.2.2(6), expr. (6.5).  Units: N, mm, MPa, rad."""
# ckb V_Ed_max 51affcebd681
from .nu import nu as _nu
from .f_cd import f_cd as _f_cd


def V_Ed_max(b_w, d, nu, f_cd):
    """Upper limit of the shear force in a member without shear reinforcement [N]
    EN 1992-1-1 cl. 6.2.2(6), expr. (6.5)
    
    b_w   Smallest width of the cross-section in the tensile area [mm]
    d     Effective depth of the cross-section [mm]
    nu    Strength reduction factor for concrete cracked in shear [-]
    f_cd  Design compressive strength of concrete [MPa]
    """
    return 0.5 * b_w * d * nu * f_cd


def V_Ed_max_chain(b_w, d, f_ck, alpha_cc, gamma_C):
    """V_Ed,max from the primary inputs."""
    nu = _nu(f_ck)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    return V_Ed_max(b_w, d, nu, f_cd)
