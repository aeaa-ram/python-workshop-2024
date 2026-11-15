"""N_cr - EN 1994-1-1 cl. 6.7.3.3(2).  Units: N, mm, MPa, rad."""
# ckb N_cr_c 6b66dc528855
from math import pi
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm
from .EI_eff import EI_eff as _EI_eff


def N_cr_c(EI_eff, L_cr):
    """Elastic critical normal force of a composite column [N]
    EN 1994-1-1 cl. 6.7.3.3(2)
    
    EI_eff  Effective flexural stiffness of a composite column [N·mm²]
    L_cr    Buckling length in the plane considered [mm]
    """
    return pi ** 2 * EI_eff / L_cr ** 2


def N_cr_c_chain(E_steel, I_a, I_s, K_e, f_ck, I_conc, L_cr):
    """N_cr from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    EI_eff = _EI_eff(E_steel, I_a, I_s, K_e, E_cm, I_conc)
    return N_cr_c(EI_eff, L_cr)
