"""l_0 - EN 1992-1-1 cl. 8.7.3(1), expr. (8.10).  Units: N, mm, MPa, rad."""
# ckb l_lap fb94b0311568
from .alpha_6 import alpha_6 as _alpha_6
from .eta_2 import eta_2 as _eta_2
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm
from .f_ctk_005 import f_ctk_005 as _f_ctk_005
from .f_ctd import f_ctd as _f_ctd
from .f_bd import f_bd as _f_bd
from .l_b_rqd import l_b_rqd as _l_b_rqd
from .l_0_min import l_0_min as _l_0_min


def l_lap(alpha_anch, alpha_6, l_b_rqd, l_0_min):
    """Design lap length [mm]
    EN 1992-1-1 cl. 8.7.3(1), expr. (8.10)
    
    alpha_anch  Product of the anchorage coefficients α1 to α5 (Table 8.2) [-]
    alpha_6     Coefficient for the percentage of lapped bars [-]
    l_b_rqd     Basic required anchorage length [mm]
    l_0_min     Minimum lap length [mm]
    """
    return max(alpha_anch * alpha_6 * l_b_rqd, l_0_min)


def l_lap_chain(alpha_anch, rho_1_lap, phi, sigma_sd, eta_1, alpha_ct, f_ck, gamma_C):
    """l_0 from the primary inputs."""
    alpha_6 = _alpha_6(rho_1_lap)
    eta_2 = _eta_2(phi)
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ctk_005 = _f_ctk_005(f_ctm)
    f_ctd = _f_ctd(alpha_ct, f_ctk_005, gamma_C)
    f_bd = _f_bd(eta_1, eta_2, f_ctd)
    l_b_rqd = _l_b_rqd(phi, sigma_sd, f_bd)
    l_0_min = _l_0_min(alpha_6, l_b_rqd, phi)
    return l_lap(alpha_anch, alpha_6, l_b_rqd, l_0_min)
