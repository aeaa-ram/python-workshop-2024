"""α_cw - EN 1992-1-1 cl. 6.2.3(3), expr. (6.11aN) to (6.11cN).  Units: N, mm, MPa, rad."""
# ckb alpha_cw a5f62d3f7bda
from .f_cd import f_cd as _f_cd


def alpha_cw(sigma_cp, f_cd):
    """Coefficient for the state of stress in the compression chord [-]
    EN 1992-1-1 cl. 6.2.3(3), expr. (6.11aN) to (6.11cN)
    
    sigma_cp  Concrete stress from axial load or prestress (compression positive) [MPa]
    f_cd      Design compressive strength of concrete [MPa]
    """
    return 1 if sigma_cp <= 0 else 1 + sigma_cp / f_cd if sigma_cp <= 0.25 * f_cd else 1.25 if sigma_cp <= 0.5 * f_cd else 2.5 * (1 - sigma_cp / f_cd)


def alpha_cw_chain(sigma_cp, alpha_cc, f_ck, gamma_C):
    """α_cw from the primary inputs."""
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    return alpha_cw(sigma_cp, f_cd)
