"""ρ_l - EN 1992-1-1 cl. 6.4.4(1).  Units: N, mm, MPa, rad."""
# ckb rho_l_p 4a33cdc3032f
from math import sqrt


def rho_l_p(rho_ly, rho_lz):
    """Reinforcement ratio for punching [-]
    EN 1992-1-1 cl. 6.4.4(1)
    
    rho_ly  Bonded tension reinforcement ratio in the y direction (over the slab width c + 3d each side) [-]
    rho_lz  Bonded tension reinforcement ratio in the z direction [-]
    """
    return min(sqrt(rho_ly * rho_lz), 0.02)
