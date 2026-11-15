"""z - EN 1992-1-1 cl. 3.1.7(3), 6.1.  Units: N, mm, MPa, rad."""
# ckb z e4f40cad8b9c
from .lam import lam as _lam
from .f_yd import f_yd as _f_yd
from .eta import eta as _eta
from .f_cd import f_cd as _f_cd
from .x import x as _x


def z(d, lam, x):
    """Lever arm of internal forces in bending [mm]
    EN 1992-1-1 cl. 3.1.7(3), 6.1
    
    d    Effective depth of the cross-section [mm]
    lam  Factor for the effective height of the compression zone [-]
    x    Depth of the neutral axis at the ultimate limit state [mm]
    """
    return d - lam * x / 2


def z_chain(d, f_ck, A_s, f_yk, gamma_S, alpha_cc, gamma_C, b):
    """z from the primary inputs."""
    lam = _lam(f_ck)
    f_yd = _f_yd(f_yk, gamma_S)
    eta = _eta(f_ck)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    x = _x(A_s, f_yd, eta, f_cd, lam, b)
    return z(d, lam, x)
