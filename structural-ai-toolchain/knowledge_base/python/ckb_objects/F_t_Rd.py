"""F_t,Rd - EN 1993-1-8 cl. 3.6.1(1), Table 3.4.  Units: N, mm, MPa, rad."""
# ckb F_t_Rd 03b0ce562807


def F_t_Rd(k_2_bolt, f_ub, A_s_bolt, gamma_M2):
    """Tension resistance of a bolt [N]
    EN 1993-1-8 cl. 3.6.1(1), Table 3.4
    
    k_2_bolt  Factor for the tension resistance of a bolt [-]
    f_ub      Ultimate tensile strength of the bolt [MPa]
    A_s_bolt  Tensile stress area of the bolt [mm2]
    gamma_M2  Partial factor for resistance of cross-sections in tension to fracture, and of bolts and welds [-]
    """
    return k_2_bolt * f_ub * A_s_bolt / gamma_M2
