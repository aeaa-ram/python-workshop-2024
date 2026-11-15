"""α_d - EN 1993-1-8 cl. 3.6.1(1), Table 3.4.  Units: N, mm, MPa, rad."""
# ckb alpha_d a5ba90ef9bb7


def alpha_d(e_1, d_0):
    """Factor for the end distance (end bolts, bearing) [-]
    EN 1993-1-8 cl. 3.6.1(1), Table 3.4
    
    e_1  End distance in the direction of load transfer [mm]
    d_0  Hole diameter [mm]
    """
    return e_1 / (3 * d_0)
