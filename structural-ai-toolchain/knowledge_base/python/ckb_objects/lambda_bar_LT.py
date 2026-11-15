"""λ̄_LT - EN 1993-1-1 cl. 6.3.2.2(1).  Units: N, mm, MPa, rad."""
# ckb lambda_bar_LT 8625f8ae4f0a
from math import sqrt


def lambda_bar_LT(W_y, f_y, M_cr):
    """Non-dimensional slenderness for lateral-torsional buckling [-]
    EN 1993-1-1 cl. 6.3.2.2(1)
    
    W_y   Section modulus for lateral-torsional buckling (W_pl [mm³]
    f_y   Nominal yield strength of structural steel [MPa]
    M_cr  Elastic critical moment for lateral-torsional buckling [Nmm]
    """
    return sqrt(W_y * f_y / M_cr)
