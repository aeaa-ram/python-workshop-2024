"""l_bd - EN 1992-1-1 cl. 8.4.4(1), expr. (8.4).  Units: N, mm, MPa, rad."""
# ckb l_bd a8e45a8b1bc9
from .eta_2 import eta_2 as _eta_2
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm
from .f_ctk_005 import f_ctk_005 as _f_ctk_005
from .f_ctd import f_ctd as _f_ctd
from .f_bd import f_bd as _f_bd
from .l_b_rqd import l_b_rqd as _l_b_rqd
from .l_b_min import l_b_min as _l_b_min


def l_bd(alpha_anch, l_b_rqd, l_b_min):
    """Design anchorage length [mm]
    EN 1992-1-1 cl. 8.4.4(1), expr. (8.4)
    
    alpha_anch  Product of the anchorage coefficients α1 to α5 (Table 8.2) [-]
    l_b_rqd     Basic required anchorage length [mm]
    l_b_min     Minimum anchorage length in tension [mm]
    """
    return max(alpha_anch * l_b_rqd, l_b_min)


def l_bd_chain(alpha_anch, phi, sigma_sd, eta_1, alpha_ct, f_ck, gamma_C):
    """l_bd from the primary inputs."""
    eta_2 = _eta_2(phi)
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ctk_005 = _f_ctk_005(f_ctm)
    f_ctd = _f_ctd(alpha_ct, f_ctk_005, gamma_C)
    f_bd = _f_bd(eta_1, eta_2, f_ctd)
    l_b_rqd = _l_b_rqd(phi, sigma_sd, f_bd)
    l_b_min = _l_b_min(l_b_rqd, phi)
    return l_bd(alpha_anch, l_b_rqd, l_b_min)
