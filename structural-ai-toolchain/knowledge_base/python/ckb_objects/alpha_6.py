"""α_6 - EN 1992-1-1 cl. 8.7.3(1), Table 8.3.  Units: N, mm, MPa, rad."""
# ckb alpha_6 12b6a2c6412d
from math import sqrt


def alpha_6(rho_1_lap):
    """Coefficient for the percentage of lapped bars [-]
    EN 1992-1-1 cl. 8.7.3(1), Table 8.3
    
    rho_1_lap  Percentage of reinforcement lapped within 0.65 l_0 of the centre of the lap considered [-]
    """
    return min(max(sqrt(rho_1_lap / 0.25), 1), 1.5)
