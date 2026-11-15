"""z - EN 1992-1-1 cl. 6.2.3(1).  Units: N, mm, MPa, rad."""
# ckb z_V 151e8beb1771


def z_V(d):
    """Inner lever arm for shear [mm]
    EN 1992-1-1 cl. 6.2.3(1)
    
    d  Effective depth of the cross-section [mm]
    """
    return 0.9 * d
