"""v_Rd,cs - EN 1992-1-1 cl. 6.4.5(1), expr. (6.52).  Units: N, mm, MPa, rad."""
# ckb v_Rd_cs b396740c525a
from math import sin
from .C_Rd_c import C_Rd_c as _C_Rd_c
from .d_eff_p import d_eff_p as _d_eff_p
from .k_p import k_p as _k_p
from .rho_l_p import rho_l_p as _rho_l_p
from .v_min_p import v_min_p as _v_min_p
from .v_Rd_c_p import v_Rd_c_p as _v_Rd_c_p
from .f_ywd import f_ywd as _f_ywd
from .f_ywd_ef import f_ywd_ef as _f_ywd_ef
from .u_1 import u_1 as _u_1


def v_Rd_cs(v_Rd_c_p, d_eff_p, s_r, A_sw_p, f_ywd_ef, u_1, alpha):
    """Punching shear resistance of a slab with shear reinforcement [MPa]
    EN 1992-1-1 cl. 6.4.5(1), expr. (6.52)
    
    v_Rd_c_p  Punching shear resistance of a slab without shear reinforcement [MPa]
    d_eff_p   Effective depth of the slab for punching [mm]
    s_r       Radial spacing of the perimeters of punching shear reinforcement [mm]
    A_sw_p    Area of punching shear reinforcement in one perimeter around the column [mm2]
    f_ywd_ef  Effective design strength of the punching shear reinforcement [MPa]
    u_1       Basic control perimeter at 2d from a rectangular internal column [mm]
    alpha     Angle between the shear reinforcement and the member axis [rad]
    """
    return 0.75 * v_Rd_c_p + 1.5 * d_eff_p / s_r * A_sw_p * f_ywd_ef / (u_1 * d_eff_p) * sin(alpha)


def v_Rd_cs_chain(gamma_C, d_y, d_z, rho_ly, rho_lz, f_ck, k_1_p, sigma_cp, s_r, A_sw_p, f_ywk, gamma_S, c_1, c_2, alpha):
    """v_Rd,cs from the primary inputs."""
    C_Rd_c = _C_Rd_c(gamma_C)
    d_eff_p = _d_eff_p(d_y, d_z)
    k_p = _k_p(d_eff_p)
    rho_l_p = _rho_l_p(rho_ly, rho_lz)
    v_min_p = _v_min_p(k_p, f_ck)
    v_Rd_c_p = _v_Rd_c_p(C_Rd_c, k_p, rho_l_p, f_ck, k_1_p, sigma_cp, v_min_p)
    f_ywd = _f_ywd(f_ywk, gamma_S)
    f_ywd_ef = _f_ywd_ef(d_eff_p, f_ywd)
    u_1 = _u_1(c_1, c_2, d_eff_p)
    return v_Rd_cs(v_Rd_c_p, d_eff_p, s_r, A_sw_p, f_ywd_ef, u_1, alpha)
