"""M_pl,Rd - EN 1994-1-1 cl. 6.2.1.2(1).  Units: N, mm, MPa, rad."""
# ckb M_pl_Rd_c 03e8008f8201
from .f_yd_a import f_yd_a as _f_yd_a
from .N_pl_a import N_pl_a as _N_pl_a
from .f_cd import f_cd as _f_cd
from .b_eff_c import b_eff_c as _b_eff_c
from .x_pl import x_pl as _x_pl


def M_pl_Rd_c(N_pl_a, h_a, h_c_fl, x_pl):
    """Plastic moment resistance of a composite beam, sagging, neutral axis in a solid slab [Nmm]
    EN 1994-1-1 cl. 6.2.1.2(1)
    
    N_pl_a  Plastic resistance of the structural steel section [N]
    h_a     Depth of the steel section [mm]
    h_c_fl  Thickness of the concrete flange (above any sheeting) [mm]
    x_pl    Depth of the plastic neutral axis below the top of the slab (neutral axis in the slab) [mm]
    α_cc = 1 in EN 1994-1-1
    """
    return N_pl_a * (h_a / 2 + h_c_fl - x_pl / 2)


def M_pl_Rd_c_chain(A_a, f_y, gamma_M0, h_a, h_c_fl, f_ck, gamma_C, b_0, L_e, b_1, b_2):
    """M_pl,Rd from the primary inputs."""
    alpha_cc = 1
    f_yd_a = _f_yd_a(f_y, gamma_M0)
    N_pl_a = _N_pl_a(A_a, f_yd_a)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    b_eff_c = _b_eff_c(b_0, L_e, b_1, b_2)
    x_pl = _x_pl(N_pl_a, f_cd, b_eff_c)
    return M_pl_Rd_c(N_pl_a, h_a, h_c_fl, x_pl)
