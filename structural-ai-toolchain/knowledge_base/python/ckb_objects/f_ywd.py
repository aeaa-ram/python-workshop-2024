"""f_ywd - EN 1992-1-1 cl. 6.2.3(3).  Units: N, mm, MPa, rad."""
# ckb f_ywd 8b0400fbf168


def f_ywd(f_ywk, gamma_S):
    """Design yield strength of the shear reinforcement [MPa]
    EN 1992-1-1 cl. 6.2.3(3)
    
    f_ywk    Characteristic yield strength of the shear reinforcement [MPa]
    gamma_S  Partial factor for reinforcing steel [-]
    """
    return f_ywk / gamma_S
