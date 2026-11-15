"""f_ctd - EN 1992-1-1 cl. 3.1.6(2), expr. (3.16).  Units: N, mm, MPa, rad."""
# ckb f_ctd b70ac2223e44
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm
from .f_ctk_005 import f_ctk_005 as _f_ctk_005


def f_ctd(alpha_ct, f_ctk_005, gamma_C):
    """Design tensile strength of concrete [MPa]
    EN 1992-1-1 cl. 3.1.6(2), expr. (3.16)
    
    alpha_ct   Coefficient for long-term effects on the tensile strength [-]
    f_ctk_005  Characteristic axial tensile strength of concrete (5 % fractile) [MPa]
    gamma_C    Partial factor for concrete [-]
    """
    return alpha_ct * f_ctk_005 / gamma_C


def f_ctd_chain(alpha_ct, f_ck, gamma_C):
    """f_ctd from the primary inputs."""
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ctk_005 = _f_ctk_005(f_ctm)
    return f_ctd(alpha_ct, f_ctk_005, gamma_C)
