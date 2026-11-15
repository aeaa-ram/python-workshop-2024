"""b_eff - EN 1992-1-1 cl. 5.3.2.1(3), expr. (5.7), (5.7a), (5.7b).  Units: N, mm, MPa, rad."""
# ckb b_eff 3cbfd5e71f4e


def b_eff(b_1, l_0_b, b_2, b_w, b_fl):
    """Effective width of a T-beam flange [mm]
    EN 1992-1-1 cl. 5.3.2.1(3), expr. (5.7), (5.7a), (5.7b)
    
    b_1    Half the clear distance to the next web (or the flange outstand) on side 1 [mm]
    l_0_b  Distance between points of zero moment (effective flange width) [mm]
    b_2    Half the clear distance to the next web (or the flange outstand) on side 2 [mm]
    b_w    Smallest width of the cross-section in the tensile area [mm]
    b_fl   Total width of the flange [mm]
    """
    return min(min(0.2 * b_1 + 0.1 * l_0_b, 0.2 * l_0_b, b_1) + min(0.2 * b_2 + 0.1 * l_0_b, 0.2 * l_0_b, b_2) + b_w, b_fl)
