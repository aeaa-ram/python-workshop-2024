"""x_pl - EN 1994-1-1 cl. 6.2.1.2(1).  Units: N, mm, MPa, rad."""
# ckb x_pl da5d40162b32
from .f_yd_a import f_yd_a as _f_yd_a
from .N_pl_a import N_pl_a as _N_pl_a
from .f_cd import f_cd as _f_cd
from .b_eff_c import b_eff_c as _b_eff_c


def x_pl(N_pl_a, f_cd, b_eff_c):
    """Depth of the plastic neutral axis below the top of the slab (neutral axis in the slab) [mm]
    EN 1994-1-1 cl. 6.2.1.2(1)
    
    N_pl_a   Plastic resistance of the structural steel section [N]
    f_cd     Design compressive strength of concrete [MPa]
    b_eff_c  Effective width of the concrete flange of a composite beam (mid-span, internal support) [mm]
    α_cc = 1 in EN 1994-1-1
    """
    return N_pl_a / (0.85 * f_cd * b_eff_c)


def x_pl_chain(A_a, f_y, gamma_M0, f_ck, gamma_C, b_0, L_e, b_1, b_2):
    """x_pl from the primary inputs."""
    alpha_cc = 1
    f_yd_a = _f_yd_a(f_y, gamma_M0)
    N_pl_a = _N_pl_a(A_a, f_yd_a)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    b_eff_c = _b_eff_c(b_0, L_e, b_1, b_2)
    return x_pl(N_pl_a, f_cd, b_eff_c)
