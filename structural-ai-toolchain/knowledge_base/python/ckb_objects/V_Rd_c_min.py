"""V_Rd,c,min - EN 1992-1-1 cl. 6.2.2(1), expr. (6.2.b).  Units: N, mm, MPa, rad."""
# ckb V_Rd_c_min 7e0ae2bd7cc8
from .k import k as _k
from .v_min import v_min as _v_min


def V_Rd_c_min(v_min, k_1, sigma_cp, b_w, d):
    """Minimum shear resistance of a member without shear reinforcement [N]
    EN 1992-1-1 cl. 6.2.2(1), expr. (6.2.b)
    
    v_min     Minimum shear strength [MPa]
    k_1       Coefficient for the effect of axial stress on shear resistance [-]
    sigma_cp  Concrete stress from axial load or prestress (compression positive) [MPa]
    b_w       Smallest width of the cross-section in the tensile area [mm]
    d         Effective depth of the cross-section [mm]
    """
    return (v_min + k_1 * sigma_cp) * b_w * d


def V_Rd_c_min_chain(d, f_ck, k_1, sigma_cp, b_w):
    """V_Rd,c,min from the primary inputs."""
    k = _k(d)
    v_min = _v_min(k, f_ck)
    return V_Rd_c_min(v_min, k_1, sigma_cp, b_w, d)
