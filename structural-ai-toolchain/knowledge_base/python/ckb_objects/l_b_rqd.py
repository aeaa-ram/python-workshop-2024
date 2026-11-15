"""l_b,rqd - EN 1992-1-1 cl. 8.4.3(2), expr. (8.3).  Units: N, mm, MPa, rad."""
# ckb l_b_rqd e0e809fae30f
from .eta_2 import eta_2 as _eta_2
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm
from .f_ctk_005 import f_ctk_005 as _f_ctk_005
from .f_ctd import f_ctd as _f_ctd
from .f_bd import f_bd as _f_bd


def l_b_rqd(phi, sigma_sd, f_bd):
    """Basic required anchorage length [mm]
    EN 1992-1-1 cl. 8.4.3(2), expr. (8.3)
    
    phi       Bar diameter (equivalent diameter for mixed sizes) [mm]
    sigma_sd  Design stress of the bar where the anchorage is measured from [MPa]
    f_bd      Design value of the ultimate bond stress [MPa]
    """
    return phi / 4 * sigma_sd / f_bd


def l_b_rqd_chain(phi, sigma_sd, eta_1, alpha_ct, f_ck, gamma_C):
    """l_b,rqd from the primary inputs."""
    eta_2 = _eta_2(phi)
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ctk_005 = _f_ctk_005(f_ctm)
    f_ctd = _f_ctd(alpha_ct, f_ctk_005, gamma_C)
    f_bd = _f_bd(eta_1, eta_2, f_ctd)
    return l_b_rqd(phi, sigma_sd, f_bd)
