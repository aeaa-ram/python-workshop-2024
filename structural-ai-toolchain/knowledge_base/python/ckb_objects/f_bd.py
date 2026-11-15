"""f_bd - EN 1992-1-1 cl. 8.4.2(2), expr. (8.2).  Units: N, mm, MPa, rad."""
# ckb f_bd 024e12c1116d
from .eta_2 import eta_2 as _eta_2
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm
from .f_ctk_005 import f_ctk_005 as _f_ctk_005
from .f_ctd import f_ctd as _f_ctd


def f_bd(eta_1, eta_2, f_ctd):
    """Design value of the ultimate bond stress [MPa]
    EN 1992-1-1 cl. 8.4.2(2), expr. (8.2)
    
    eta_1  Coefficient for the bond conditions [-]
    eta_2  Coefficient for the bar diameter (bond) [-]
    f_ctd  Design tensile strength of concrete [MPa]
    """
    return 2.25 * eta_1 * eta_2 * f_ctd


def f_bd_chain(eta_1, phi, alpha_ct, f_ck, gamma_C):
    """f_bd from the primary inputs."""
    eta_2 = _eta_2(phi)
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ctk_005 = _f_ctk_005(f_ctm)
    f_ctd = _f_ctd(alpha_ct, f_ctk_005, gamma_C)
    return f_bd(eta_1, eta_2, f_ctd)
