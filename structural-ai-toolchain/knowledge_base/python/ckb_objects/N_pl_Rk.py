"""N_pl,Rk - EN 1994-1-1 cl. 6.7.3.3(2).  Units: N, mm, MPa, rad."""
# ckb N_pl_Rk 180efcd4e164


def N_pl_Rk(A_a, f_y, A_c, f_ck, A_s, f_yk):
    """Characteristic plastic resistance to compression of a composite section [N]
    EN 1994-1-1 cl. 6.7.3.3(2)
    
    A_a   Cross-sectional area of the structural steel section [mm2]
    f_y   Nominal yield strength of structural steel [MPa]
    A_c   Cross-sectional area of concrete [mm2]
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    A_s   Area of tension reinforcement [mm2]
    f_yk  Characteristic yield strength of reinforcement [MPa]
    """
    return A_a * f_y + 0.85 * A_c * f_ck + A_s * f_yk
