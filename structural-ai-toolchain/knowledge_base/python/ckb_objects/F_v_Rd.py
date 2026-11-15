"""F_v,Rd - EN 1993-1-8 cl. 3.6.1(1), Table 3.4.  Units: N, mm, MPa, rad."""
# ckb F_v_Rd 7e02e4da3dc2


def F_v_Rd(alpha_v, f_ub, A_bolt, gamma_M2):
    """Shear resistance of a bolt per shear plane [N]
    EN 1993-1-8 cl. 3.6.1(1), Table 3.4
    
    alpha_v   Factor for the shear resistance of a bolt [-]
    f_ub      Ultimate tensile strength of the bolt [MPa]
    A_bolt    Bolt area in the shear plane (A_s if the plane passes through the thread [mm2]
    gamma_M2  Partial factor for resistance of cross-sections in tension to fracture, and of bolts and welds [-]
    """
    return alpha_v * f_ub * A_bolt / gamma_M2
