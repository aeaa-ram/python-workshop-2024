"""k_t - EN 1994-1-1 cl. 6.6.4.2(1), expr. (6.23).  Units: N, mm, MPa, rad."""
# ckb k_t_rib 1b348077f4e0
from math import sqrt


def k_t_rib(n_r, b_0_rib, h_p, h_sc, k_t_max):
    """Reduction factor for studs in ribs transverse to the beam [-]
    EN 1994-1-1 cl. 6.6.4.2(1), expr. (6.23)
    
    n_r      Number of stud connectors in one rib at a beam intersection [-]
    b_0_rib  Width of a concrete-filled rib (mean width of a trapezoidal rib) [mm]
    h_p      Overall depth of the profiled steel sheeting [mm]
    h_sc     Overall nominal height of the stud [mm]
    k_t_max  Upper limit of the reduction factor k_t [-]
    """
    return min(0.7 / sqrt(n_r) * b_0_rib / h_p * (h_sc / h_p - 1), k_t_max)
