"""V_Rd,c - EN 1992-1-1 cl. 6.2.2(1), expr. (6.2.a), (6.2.b).  Units: N, mm, MPa, rad."""
# ckb V_Rd_c 5b3fb119fcd5
from .C_Rd_c import C_Rd_c as _C_Rd_c
from .k import k as _k
from .rho_l import rho_l as _rho_l
from .v_min import v_min as _v_min
from .V_Rd_c_min import V_Rd_c_min as _V_Rd_c_min


def V_Rd_c(C_Rd_c, k, rho_l, f_ck, k_1, sigma_cp, b_w, d, V_Rd_c_min):
    """Shear resistance of a member without shear reinforcement [N]
    EN 1992-1-1 cl. 6.2.2(1), expr. (6.2.a), (6.2.b)
    
    C_Rd_c      Coefficient for the shear resistance of concrete [-]
    k           Size factor for shear [-]
    rho_l       Longitudinal reinforcement ratio [-]
    f_ck        Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    k_1         Coefficient for the effect of axial stress on shear resistance [-]
    sigma_cp    Concrete stress from axial load or prestress (compression positive) [MPa]
    b_w         Smallest width of the cross-section in the tensile area [mm]
    d           Effective depth of the cross-section [mm]
    V_Rd_c_min  Minimum shear resistance of a member without shear reinforcement [N]
    """
    return max((C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d, V_Rd_c_min)


def V_Rd_c_chain(gamma_C, d, A_sl, b_w, f_ck, k_1, sigma_cp):
    """V_Rd,c from the primary inputs."""
    C_Rd_c = _C_Rd_c(gamma_C)
    k = _k(d)
    rho_l = _rho_l(A_sl, b_w, d)
    v_min = _v_min(k, f_ck)
    V_Rd_c_min = _V_Rd_c_min(v_min, k_1, sigma_cp, b_w, d)
    return V_Rd_c(C_Rd_c, k, rho_l, f_ck, k_1, sigma_cp, b_w, d, V_Rd_c_min)
