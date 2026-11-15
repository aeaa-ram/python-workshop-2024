"""α_e - EN 1992-1-1 cl. 7.3.4(2).  Units: N, mm, MPa, rad."""
# ckb alpha_e 22ba74086a34
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm


def alpha_e(E_s, E_cm):
    """Modular ratio E_s / E_cm [-]
    EN 1992-1-1 cl. 7.3.4(2)
    
    E_s   Design modulus of elasticity of reinforcing steel [MPa]
    E_cm  Secant modulus of elasticity of concrete [MPa]
    """
    return E_s / E_cm


def alpha_e_chain(E_s, f_ck):
    """α_e from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    return alpha_e(E_s, E_cm)
