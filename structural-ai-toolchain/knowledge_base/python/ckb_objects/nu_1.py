"""ν_1 - EN 1992-1-1 cl. 6.2.3(3), expr. (6.6N).  Units: N, mm, MPa, rad."""
# ckb nu_1 8b3136a8b148
from .nu import nu as _nu


def nu_1(nu):
    """Strength reduction factor for concrete cracked in shear (strut) [-]
    EN 1992-1-1 cl. 6.2.3(3), expr. (6.6N)
    
    nu  Strength reduction factor for concrete cracked in shear [-]
    """
    return nu


def nu_1_chain(f_ck):
    """ν_1 from the primary inputs."""
    nu = _nu(f_ck)
    return nu_1(nu)
