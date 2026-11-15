"""d_eff - EN 1992-1-1 cl. 6.4.2(1), expr. (6.32).  Units: N, mm, MPa, rad."""
# ckb d_eff_p 64261f0241d7


def d_eff_p(d_y, d_z):
    """Effective depth of the slab for punching [mm]
    EN 1992-1-1 cl. 6.4.2(1), expr. (6.32)
    
    d_y  Effective depth in the y direction [mm]
    d_z  Effective depth in the z direction [mm]
    """
    return (d_y + d_z) / 2
