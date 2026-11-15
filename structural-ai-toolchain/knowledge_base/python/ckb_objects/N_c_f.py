"""N_c,f - EN 1994-1-1 cl. 6.2.1.2(1).  Units: N, mm, MPa, rad."""
# ckb N_c_f e6e6e129b733
from .f_cd import f_cd as _f_cd
from .b_eff_c import b_eff_c as _b_eff_c


def N_c_f(f_cd, b_eff_c, h_c_fl):
    """Compressive resistance of the concrete flange (full shear connection) [N]
    EN 1994-1-1 cl. 6.2.1.2(1)
    
    f_cd     Design compressive strength of concrete [MPa]
    b_eff_c  Effective width of the concrete flange of a composite beam (mid-span, internal support) [mm]
    h_c_fl   Thickness of the concrete flange (above any sheeting) [mm]
    α_cc = 1 in EN 1994-1-1
    """
    return 0.85 * f_cd * b_eff_c * h_c_fl


def N_c_f_chain(f_ck, gamma_C, b_0, L_e, b_1, b_2, h_c_fl):
    """N_c,f from the primary inputs."""
    alpha_cc = 1
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    b_eff_c = _b_eff_c(b_0, L_e, b_1, b_2)
    return N_c_f(f_cd, b_eff_c, h_c_fl)
