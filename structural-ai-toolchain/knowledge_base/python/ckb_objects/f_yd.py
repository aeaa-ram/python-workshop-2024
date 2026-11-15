"""f_yd - EN 1992-1-1 cl. 3.2.7(2).  Units: N, mm, MPa, rad."""
# ckb f_yd 2c14c7053dd1


def f_yd(f_yk, gamma_S):
    """Design yield strength of reinforcement [MPa]
    EN 1992-1-1 cl. 3.2.7(2)
    
    f_yk     Characteristic yield strength of reinforcement [MPa]
    gamma_S  Partial factor for reinforcing steel [-]
    """
    return f_yk / gamma_S
