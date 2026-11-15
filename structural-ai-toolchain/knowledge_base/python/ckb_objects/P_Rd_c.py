"""P_Rd,c - EN 1994-1-1 cl. 6.6.3.1(1), expr. (6.19).  Units: N, mm, MPa, rad."""
# ckb P_Rd_c 6b0828cca936
from math import sqrt
from .alpha_stud import alpha_stud as _alpha_stud
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm


def P_Rd_c(alpha_stud, d_s, f_ck, E_cm, gamma_V):
    """Design shear resistance of a headed stud, failure of the concrete [N]
    EN 1994-1-1 cl. 6.6.3.1(1), expr. (6.19)
    
    alpha_stud  Factor for the stud height in the concrete failure mode [-]
    d_s         Diameter of the shank of the stud [mm]
    f_ck        Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    E_cm        Secant modulus of elasticity of concrete [MPa]
    gamma_V     Partial factor for design shear resistance of a headed stud [-]
    """
    return 0.29 * alpha_stud * d_s ** 2 * sqrt(f_ck * E_cm) / gamma_V


def P_Rd_c_chain(h_sc, d_s, f_ck, gamma_V):
    """P_Rd,c from the primary inputs."""
    alpha_stud = _alpha_stud(h_sc, d_s)
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    return P_Rd_c(alpha_stud, d_s, f_ck, E_cm, gamma_V)
