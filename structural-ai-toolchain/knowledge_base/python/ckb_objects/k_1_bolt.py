"""k_1 - EN 1993-1-8 cl. 3.6.1(1), Table 3.4.  Units: N, mm, MPa, rad."""
# ckb k_1_bolt 6598e66ab1eb


def k_1_bolt(e_2, d_0, p_2):
    """Factor for bearing perpendicular to the load transfer (edge bolts) [-]
    EN 1993-1-8 cl. 3.6.1(1), Table 3.4
    
    e_2  Edge distance at right angles to the load [mm]
    d_0  Hole diameter [mm]
    p_2  Spacing of bolt lines at right angles to the load [mm]
    """
    return min(2.8 * e_2 / d_0 - 1.7, 1.4 * p_2 / d_0 - 1.7, 2.5)
