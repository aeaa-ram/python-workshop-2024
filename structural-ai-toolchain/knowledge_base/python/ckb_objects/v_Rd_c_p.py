"""v_Rd,c - EN 1992-1-1 cl. 6.4.4(1), expr. (6.47).  Units: N, mm, MPa, rad."""
# ckb v_Rd_c_p d774aec8d1b2
from .C_Rd_c import C_Rd_c as _C_Rd_c
from .d_eff_p import d_eff_p as _d_eff_p
from .k_p import k_p as _k_p
from .rho_l_p import rho_l_p as _rho_l_p
from .v_min_p import v_min_p as _v_min_p


def v_Rd_c_p(C_Rd_c, k_p, rho_l_p, f_ck, k_1_p, sigma_cp, v_min_p):
    """Punching shear resistance of a slab without shear reinforcement [MPa]
    EN 1992-1-1 cl. 6.4.4(1), expr. (6.47)
    
    C_Rd_c    Coefficient for the shear resistance of concrete [-]
    k_p       Size factor for punching [-]
    rho_l_p   Reinforcement ratio for punching [-]
    f_ck      Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    k_1_p     Coefficient for the axial stress in punching [-]
    sigma_cp  Concrete stress from axial load or prestress (compression positive) [MPa]
    v_min_p   Minimum punching shear strength [MPa]
    """
    return max(C_Rd_c * k_p * (100 * rho_l_p * f_ck) ** (1 / 3) + k_1_p * sigma_cp, v_min_p + k_1_p * sigma_cp)


def v_Rd_c_p_chain(gamma_C, d_y, d_z, rho_ly, rho_lz, f_ck, k_1_p, sigma_cp):
    """v_Rd,c from the primary inputs."""
    C_Rd_c = _C_Rd_c(gamma_C)
    d_eff_p = _d_eff_p(d_y, d_z)
    k_p = _k_p(d_eff_p)
    rho_l_p = _rho_l_p(rho_ly, rho_lz)
    v_min_p = _v_min_p(k_p, f_ck)
    return v_Rd_c_p(C_Rd_c, k_p, rho_l_p, f_ck, k_1_p, sigma_cp, v_min_p)
