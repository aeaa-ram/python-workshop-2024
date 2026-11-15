"""v_min - EN 1992-1-1 cl. 6.4.4(1).  Units: N, mm, MPa, rad."""
# ckb v_min_p 147a74785531
from .d_eff_p import d_eff_p as _d_eff_p
from .k_p import k_p as _k_p


def v_min_p(k_p, f_ck):
    """Minimum punching shear strength [MPa]
    EN 1992-1-1 cl. 6.4.4(1)
    
    k_p   Size factor for punching [-]
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 0.035 * k_p ** 1.5 * f_ck ** 0.5


def v_min_p_chain(d_y, d_z, f_ck):
    """v_min from the primary inputs."""
    d_eff_p = _d_eff_p(d_y, d_z)
    k_p = _k_p(d_eff_p)
    return v_min_p(k_p, f_ck)
