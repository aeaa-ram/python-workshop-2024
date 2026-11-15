"""C_Rd,c - EN 1992-1-1 cl. 6.2.2(1).  Units: N, mm, MPa, rad."""
# ckb C_Rd_c 6a4e22c4e444


def C_Rd_c(gamma_C):
    """Coefficient for the shear resistance of concrete [-]
    EN 1992-1-1 cl. 6.2.2(1)
    
    gamma_C  Partial factor for concrete [-]
    """
    return 0.18 / gamma_C
