"""η_2 - EN 1992-1-1 cl. 8.4.2(2).  Units: N, mm, MPa, rad."""
# ckb eta_2 92327bafcdba


def eta_2(phi):
    """Coefficient for the bar diameter (bond) [-]
    EN 1992-1-1 cl. 8.4.2(2)
    
    phi  Bar diameter (equivalent diameter for mixed sizes) [mm]
    """
    return 1 if phi <= 32 else (132 - phi) / 100
