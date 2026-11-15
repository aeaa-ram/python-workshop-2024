"""l_0,min - EN 1992-1-1 cl. 8.7.3(1), expr. (8.11).  Units: N, mm, MPa, rad."""
# ckb l_0_min ec47ebee398c
from .alpha_6 import alpha_6 as _alpha_6
from .eta_2 import eta_2 as _eta_2
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm
from .f_ctk_005 import f_ctk_005 as _f_ctk_005
from .f_ctd import f_ctd as _f_ctd
from .f_bd import f_bd as _f_bd
from .l_b_rqd import l_b_rqd as _l_b_rqd


def l_0_min(alpha_6, l_b_rqd, phi):
    """Minimum lap length [mm]
    EN 1992-1-1 cl. 8.7.3(1), expr. (8.11)
    
    alpha_6  Coefficient for the percentage of lapped bars [-]
    l_b_rqd  Basic required anchorage length [mm]
    phi      Bar diameter (equivalent diameter for mixed sizes) [mm]
    """
    return max(0.3 * alpha_6 * l_b_rqd, 15 * phi, 200)


def l_0_min_chain(rho_1_lap, phi, sigma_sd, eta_1, alpha_ct, f_ck, gamma_C):
    """l_0,min from the primary inputs."""
    alpha_6 = _alpha_6(rho_1_lap)
    eta_2 = _eta_2(phi)
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ctk_005 = _f_ctk_005(f_ctm)
    f_ctd = _f_ctd(alpha_ct, f_ctk_005, gamma_C)
    f_bd = _f_bd(eta_1, eta_2, f_ctd)
    l_b_rqd = _l_b_rqd(phi, sigma_sd, f_bd)
    return l_0_min(alpha_6, l_b_rqd, phi)
