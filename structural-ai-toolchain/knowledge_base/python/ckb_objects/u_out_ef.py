"""u_out,ef - EN 1992-1-1 cl. 6.4.5(4), expr. (6.54).  Units: N, mm, MPa, rad."""
# ckb u_out_ef b6f6d72a5f5b
from .C_Rd_c import C_Rd_c as _C_Rd_c
from .d_eff_p import d_eff_p as _d_eff_p
from .k_p import k_p as _k_p
from .rho_l_p import rho_l_p as _rho_l_p
from .v_min_p import v_min_p as _v_min_p
from .v_Rd_c_p import v_Rd_c_p as _v_Rd_c_p


def u_out_ef(beta_p, V_Ed, v_Rd_c_p, d_eff_p):
    """Control perimeter beyond which punching shear reinforcement is not needed [mm]
    EN 1992-1-1 cl. 6.4.5(4), expr. (6.54)
    
    beta_p    Factor for the eccentricity of the support reaction (punching) [-]
    V_Ed      Design shear force [N]
    v_Rd_c_p  Punching shear resistance of a slab without shear reinforcement [MPa]
    d_eff_p   Effective depth of the slab for punching [mm]
    """
    return beta_p * V_Ed / (v_Rd_c_p * d_eff_p)


def u_out_ef_chain(beta_p, V_Ed, gamma_C, d_y, d_z, rho_ly, rho_lz, f_ck, k_1_p, sigma_cp):
    """u_out,ef from the primary inputs."""
    C_Rd_c = _C_Rd_c(gamma_C)
    d_eff_p = _d_eff_p(d_y, d_z)
    k_p = _k_p(d_eff_p)
    rho_l_p = _rho_l_p(rho_ly, rho_lz)
    v_min_p = _v_min_p(k_p, f_ck)
    v_Rd_c_p = _v_Rd_c_p(C_Rd_c, k_p, rho_l_p, f_ck, k_1_p, sigma_cp, v_min_p)
    return u_out_ef(beta_p, V_Ed, v_Rd_c_p, d_eff_p)
