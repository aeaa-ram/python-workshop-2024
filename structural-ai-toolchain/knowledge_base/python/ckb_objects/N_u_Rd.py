"""N_u,Rd - EN 1993-1-1 cl. 6.2.3(2), expr. (6.7).  Units: N, mm, MPa, rad."""
# ckb N_u_Rd 779c9a2dc2b4


def N_u_Rd(A_net, f_u, gamma_M2):
    """Design ultimate resistance of the net section at holes [N]
    EN 1993-1-1 cl. 6.2.3(2), expr. (6.7)
    
    A_net     Net cross-sectional area at holes for fasteners [mm2]
    f_u       Ultimate tensile strength of the steel (plate, section or stud material) [MPa]
    gamma_M2  Partial factor for resistance of cross-sections in tension to fracture, and of bolts and welds [-]
    """
    return 0.9 * A_net * f_u / gamma_M2
