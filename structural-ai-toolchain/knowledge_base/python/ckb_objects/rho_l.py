"""ρ_l - EN 1992-1-1 cl. 6.2.2(1).  Units: N, mm, MPa, rad."""
# ckb rho_l 6a047f5ccfb6


def rho_l(A_sl, b_w, d):
    """Longitudinal reinforcement ratio [-]
    EN 1992-1-1 cl. 6.2.2(1)
    
    A_sl  Area of tensile reinforcement extending at least l_bd + d beyond the section [mm2]
    b_w   Smallest width of the cross-section in the tensile area [mm]
    d     Effective depth of the cross-section [mm]
    """
    return min(A_sl / (b_w * d), 0.02)
