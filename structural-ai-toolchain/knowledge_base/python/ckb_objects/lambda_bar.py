"""λ̄ - EN 1993-1-1 cl. 6.3.1.2(1), expr. (6.50).  Units: N, mm, MPa, rad."""
# ckb lambda_bar d5c4bbeac05c
from math import sqrt
from .N_cr import N_cr as _N_cr


def lambda_bar(A_sec, f_y, N_cr):
    """Non-dimensional slenderness for flexural buckling (class 1 to 3) [-]
    EN 1993-1-1 cl. 6.3.1.2(1), expr. (6.50)
    
    A_sec  Cross-sectional area of the steel section [mm2]
    f_y    Nominal yield strength of structural steel [MPa]
    N_cr   Elastic critical force for flexural buckling [N]
    """
    return sqrt(A_sec * f_y / N_cr)


def lambda_bar_chain(A_sec, f_y, E_steel, I_sec, L_cr):
    """λ̄ from the primary inputs."""
    N_cr = _N_cr(E_steel, I_sec, L_cr)
    return lambda_bar(A_sec, f_y, N_cr)
