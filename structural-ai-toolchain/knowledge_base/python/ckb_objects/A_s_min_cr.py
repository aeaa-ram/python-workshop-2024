"""A_s,min - EN 1992-1-1 cl. 7.3.2(2), expr. (7.1).  Units: N, mm, MPa, rad."""
# ckb A_s_min_cr ad9059d2bfbe
from .k_h_cr import k_h_cr as _k_h_cr
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm
from .f_ct_eff import f_ct_eff as _f_ct_eff


def A_s_min_cr(k_c, k_h_cr, f_ct_eff, A_ct, sigma_s_cr):
    """Minimum reinforcement area for crack control [mm2]
    EN 1992-1-1 cl. 7.3.2(2), expr. (7.1)
    
    k_c         Coefficient for the stress distribution in the section before cracking [-]
    k_h_cr      Coefficient for non-uniform self-equilibrating stresses (minimum reinforcement) [-]
    f_ct_eff    Mean tensile strength of the concrete when the first cracks may occur [MPa]
    A_ct        Area of concrete in the tensile zone before the first crack [mm2]
    sigma_s_cr  Stress permitted in the reinforcement immediately after cracking [MPa]
    """
    return k_c * k_h_cr * f_ct_eff * A_ct / sigma_s_cr


def A_s_min_cr_chain(k_c, h, f_ck, A_ct, sigma_s_cr):
    """A_s,min from the primary inputs."""
    k_h_cr = _k_h_cr(h)
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    f_ct_eff = _f_ct_eff(f_ctm)
    return A_s_min_cr(k_c, k_h_cr, f_ct_eff, A_ct, sigma_s_cr)
