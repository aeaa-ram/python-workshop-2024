"""M_Rd - EN 1992-1-1 cl. 6.1.  Units: N, mm, MPa, rad."""
# ckb M_Rd 29a325f104fd
from .f_yd import f_yd as _f_yd
from .lam import lam as _lam
from .eta import eta as _eta
from .f_cd import f_cd as _f_cd
from .x import x as _x
from .z import z as _z


def M_Rd(A_s, f_yd, z):
    """Design moment resistance [Nmm]
    EN 1992-1-1 cl. 6.1
    
    A_s   Area of tension reinforcement [mm2]
    f_yd  Design yield strength of reinforcement [MPa]
    z     Lever arm of internal forces in bending [mm]
    """
    return A_s * f_yd * z


def M_Rd_chain(A_s, f_yk, gamma_S, d, f_ck, alpha_cc, gamma_C, b):
    """M_Rd from the primary inputs."""
    f_yd = _f_yd(f_yk, gamma_S)
    lam = _lam(f_ck)
    eta = _eta(f_ck)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    x = _x(A_s, f_yd, eta, f_cd, lam, b)
    z = _z(d, lam, x)
    return M_Rd(A_s, f_yd, z)
