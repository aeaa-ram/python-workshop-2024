"""c_min - EN 1992-1-1 cl. 4.4.1.2(2), expr. (4.2).  Units: N, mm, MPa, rad."""
# ckb c_min e1096505d7c0


def c_min(phi, c_min_dur):
    """Minimum cover [mm]
    EN 1992-1-1 cl. 4.4.1.2(2), expr. (4.2)
    
    phi        Bar diameter (equivalent diameter for mixed sizes) [mm]
    c_min_dur  Minimum cover for the exposure class (durability) [mm]
    """
    return max(phi, c_min_dur, 10)
