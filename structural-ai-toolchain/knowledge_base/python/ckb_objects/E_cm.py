"""E_cm - EN 1992-1-1 cl. 3.1.3, Table 3.1.  Units: N, mm, MPa, rad."""
# ckb E_cm 8eb579a02ecf
from .f_cm import f_cm as _f_cm


def E_cm(f_cm):
    """Secant modulus of elasticity of concrete [MPa]
    EN 1992-1-1 cl. 3.1.3, Table 3.1
    
    f_cm  Mean compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 22000 * (f_cm / 10) ** 0.3


def E_cm_chain(f_ck):
    """E_cm from the primary inputs."""
    f_cm = _f_cm(f_ck)
    return E_cm(f_cm)
