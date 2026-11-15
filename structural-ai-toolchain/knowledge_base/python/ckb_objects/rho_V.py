"""ρ - EN 1993-1-1 cl. 6.2.8(3), expr. (6.29).  Units: N, mm, MPa, rad."""
# ckb rho_V e3c9ac7cf71e
from .V_pl_Rd import V_pl_Rd as _V_pl_Rd


def rho_V(V_Ed, V_pl_Rd):
    """Reduction factor for the yield strength in the shear area (bending and shear) [-]
    EN 1993-1-1 cl. 6.2.8(3), expr. (6.29)
    
    V_Ed     Design shear force [N]
    V_pl_Rd  Design plastic shear resistance [N]
    """
    return (2 * V_Ed / V_pl_Rd - 1) ** 2 if V_Ed > 0.5 * V_pl_Rd else 0


def rho_V_chain(V_Ed, A_v, f_y, gamma_M0):
    """ρ from the primary inputs."""
    V_pl_Rd = _V_pl_Rd(A_v, f_y, gamma_M0)
    return rho_V(V_Ed, V_pl_Rd)
