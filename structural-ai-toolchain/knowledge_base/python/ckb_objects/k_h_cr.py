"""k - EN 1992-1-1 cl. 7.3.2(2).  Units: N, mm, MPa, rad."""
# ckb k_h_cr 6a44535fe1ab


def k_h_cr(h):
    """Coefficient for non-uniform self-equilibrating stresses (minimum reinforcement) [-]
    EN 1992-1-1 cl. 7.3.2(2)
    
    h  Overall depth of the cross-section [mm]
    """
    return 1 if h <= 300 else 0.65 if h >= 800 else 1 - 0.35 * (h - 300) / 500
