"""η_min - EN 1994-1-1 cl. 6.6.1.2(1), expr. (6.12).  Units: N, mm, MPa, rad."""
# ckb eta_min_sc 9171f33ecdfc


def eta_min_sc(f_y, L_e):
    """Minimum degree of shear connection (steel sections with equal flanges) [-]
    EN 1994-1-1 cl. 6.6.1.2(1), expr. (6.12)
    
    f_y  Nominal yield strength of structural steel [MPa]
    L_e  Equivalent span (distance between points of zero bending moment) [mm]
    """
    return max(1 - 355 / f_y * (0.75 - 0.03 * L_e / 1000), 0.4)
