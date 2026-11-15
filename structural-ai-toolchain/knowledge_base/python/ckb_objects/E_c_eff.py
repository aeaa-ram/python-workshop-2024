"""E_c,eff - EN 1992-1-1 cl. 7.4.3(5), expr. (7.20).  Units: N, mm, MPa, rad."""
# ckb E_c_eff e82fc8c21992
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm


def E_c_eff(E_cm, phi_t):
    """Effective modulus of elasticity of concrete (creep) [MPa]
    EN 1992-1-1 cl. 7.4.3(5), expr. (7.20)
    
    E_cm   Secant modulus of elasticity of concrete [MPa]
    phi_t  Final creep coefficient [-]
    """
    return E_cm / (1 + phi_t)


def E_c_eff_chain(f_ck, phi_t):
    """E_c,eff from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    return E_c_eff(E_cm, phi_t)
