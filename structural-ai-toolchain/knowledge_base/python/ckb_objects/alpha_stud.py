"""α - EN 1994-1-1 cl. 6.6.3.1(1), expr. (6.20), (6.21).  Units: N, mm, MPa, rad."""
# ckb alpha_stud 4502d988ffdc


def alpha_stud(h_sc, d_s):
    """Factor for the stud height in the concrete failure mode [-]
    EN 1994-1-1 cl. 6.6.3.1(1), expr. (6.20), (6.21)
    
    h_sc  Overall nominal height of the stud [mm]
    d_s   Diameter of the shank of the stud [mm]
    """
    return min(0.2 * (h_sc / d_s + 1), 1)
