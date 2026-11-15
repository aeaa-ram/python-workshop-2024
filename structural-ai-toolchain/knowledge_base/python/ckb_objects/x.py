"""x - EN 1992-1-1 cl. 3.1.7(3), 6.1.  Units: N, mm, MPa, rad."""
# ckb x 8ab0e3e4e36e
from .f_yd import f_yd as _f_yd
from .eta import eta as _eta
from .f_cd import f_cd as _f_cd
from .lam import lam as _lam


def x(A_s, f_yd, eta, f_cd, lam, b):
    """Depth of the neutral axis at the ultimate limit state [mm]
    EN 1992-1-1 cl. 3.1.7(3), 6.1
    
    A_s   Area of tension reinforcement [mm2]
    f_yd  Design yield strength of reinforcement [MPa]
    eta   Factor for the effective strength of the compression zone [-]
    f_cd  Design compressive strength of concrete [MPa]
    lam   Factor for the effective height of the compression zone [-]
    b     Width of the cross-section [mm]
    """
    return A_s * f_yd / (eta * f_cd * lam * b)


def x_chain(A_s, f_yk, gamma_S, f_ck, alpha_cc, gamma_C, b):
    """x from the primary inputs."""
    f_yd = _f_yd(f_yk, gamma_S)
    eta = _eta(f_ck)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    lam = _lam(f_ck)
    return x(A_s, f_yd, eta, f_cd, lam, b)
