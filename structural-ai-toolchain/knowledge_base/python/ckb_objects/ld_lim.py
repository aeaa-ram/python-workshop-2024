"""l/d - EN 1992-1-1 cl. 7.4.2(2), expr. (7.16a), (7.16b).  Units: N, mm, MPa, rad."""
# ckb ld_lim a1c9b7cdf802
from math import sqrt
from .rho_0 import rho_0 as _rho_0


def ld_lim(rho_req, rho_0, K_sys, f_ck, rho_c):
    """Limiting span/depth ratio [-]
    EN 1992-1-1 cl. 7.4.2(2), expr. (7.16a), (7.16b)
    
    rho_req  Required tension reinforcement ratio at mid-span (at the support for cantilevers) [-]
    rho_0    Reference reinforcement ratio [-]
    K_sys    Factor for the structural system (span/depth ratio) [-]
    f_ck     Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    rho_c    Required compression reinforcement ratio at mid-span [-]
    """
    return K_sys * (11 + 1.5 * sqrt(f_ck) * rho_0 / rho_req + 3.2 * sqrt(f_ck) * (rho_0 / rho_req - 1) ** 1.5) if rho_req <= rho_0 else K_sys * (11 + 1.5 * sqrt(f_ck) * rho_0 / (rho_req - rho_c) + sqrt(f_ck) * sqrt(rho_c / rho_0) / 12)


def ld_lim_chain(rho_req, f_ck, K_sys, rho_c):
    """l/d from the primary inputs."""
    rho_0 = _rho_0(f_ck)
    return ld_lim(rho_req, rho_0, K_sys, f_ck, rho_c)
