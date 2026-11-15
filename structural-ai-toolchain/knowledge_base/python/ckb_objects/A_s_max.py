"""A_s,max - EN 1992-1-1 cl. 9.2.1.1(3).  Units: N, mm, MPa, rad."""
# ckb A_s_max 34bd70409327


def A_s_max(A_c):
    """Maximum area of tension or compression reinforcement outside lap locations [mm2]
    EN 1992-1-1 cl. 9.2.1.1(3)
    
    A_c  Cross-sectional area of concrete [mm2]
    """
    return 0.04 * A_c
