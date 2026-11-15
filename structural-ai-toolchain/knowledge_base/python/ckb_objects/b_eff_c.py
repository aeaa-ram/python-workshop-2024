"""b_eff - EN 1994-1-1 cl. 5.4.1.2(5), expr. (5.3).  Units: N, mm, MPa, rad."""
# ckb b_eff_c f475b6ae34db


def b_eff_c(b_0, L_e, b_1, b_2):
    """Effective width of the concrete flange of a composite beam (mid-span, internal support) [mm]
    EN 1994-1-1 cl. 5.4.1.2(5), expr. (5.3)
    
    b_0  Distance between the centres of the outstand shear connectors [mm]
    L_e  Equivalent span (distance between points of zero bending moment) [mm]
    b_1  Half the clear distance to the next web (or the flange outstand) on side 1 [mm]
    b_2  Half the clear distance to the next web (or the flange outstand) on side 2 [mm]
    """
    return b_0 + min(L_e / 8, b_1) + min(L_e / 8, b_2)
