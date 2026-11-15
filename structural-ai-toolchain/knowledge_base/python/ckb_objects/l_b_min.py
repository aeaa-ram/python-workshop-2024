"""l_b,min - EN 1992-1-1 cl. 8.4.4(1), expr. (8.6).  Units: N, mm, MPa, rad."""
# ckb l_b_min 9720ca2e3fa5
from .eta_2 import eta_2 as _eta_2
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm
from .f_ctk_005 import f_ctk_005 as _f_ctk_005
from .f_ctd import f_ctd as _f_ctd
from .f_bd import f_bd as _f_bd
from .l_b_rqd import l_b_rqd as _l_b_rqd


def l_b_min(l_b_rqd, phi):
    """Minimum anchorage length in tension [mm]
    EN 1992-1-1 cl. 8.4.4(1), expr. (8.6)
    
    l_b_rqd  Basic required anchorage length [mm]
    phi      Bar diameter (equivalent diameter for mixed sizes) [mm]
    """
    return max(0.3 * l_b_rqd, 10 * phi, 100)


def l_b_min_chain(phi, sigma_sd, eta_1, alpha_ct, f_ck, gamma_C):
    """l_b,min from the primary inputs."""
    eta_2 = _eta_2(phi)
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ctk_005 = _f_ctk_005(f_ctm)
    f_ctd = _f_ctd(alpha_ct, f_ctk_005, gamma_C)
    f_bd = _f_bd(eta_1, eta_2, f_ctd)
    l_b_rqd = _l_b_rqd(phi, sigma_sd, f_bd)
    return l_b_min(l_b_rqd, phi)
