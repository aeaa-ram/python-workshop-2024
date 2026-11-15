"""F_b,Rd - EN 1993-1-8 cl. 3.6.1(1), Table 3.4.  Units: N, mm, MPa, rad."""
# ckb F_b_Rd 8a94dcfc548b
from .k_1_bolt import k_1_bolt as _k_1_bolt
from .alpha_d import alpha_d as _alpha_d
from .alpha_b import alpha_b as _alpha_b


def F_b_Rd(k_1_bolt, alpha_b, f_u, d_bolt, t_plate, gamma_M2):
    """Bearing resistance of a bolt [N]
    EN 1993-1-8 cl. 3.6.1(1), Table 3.4
    
    k_1_bolt  Factor for bearing perpendicular to the load transfer (edge bolts) [-]
    alpha_b   Factor for bearing in the direction of load transfer [-]
    f_u       Ultimate tensile strength of the steel (plate, section or stud material) [MPa]
    d_bolt    Nominal diameter of the bolt [mm]
    t_plate   Thickness of the connected part [mm]
    gamma_M2  Partial factor for resistance of cross-sections in tension to fracture, and of bolts and welds [-]
    """
    return k_1_bolt * alpha_b * f_u * d_bolt * t_plate / gamma_M2


def F_b_Rd_chain(e_2, d_0, p_2, e_1, f_ub, f_u, d_bolt, t_plate, gamma_M2):
    """F_b,Rd from the primary inputs."""
    k_1_bolt = _k_1_bolt(e_2, d_0, p_2)
    alpha_d = _alpha_d(e_1, d_0)
    alpha_b = _alpha_b(alpha_d, f_ub, f_u)
    return F_b_Rd(k_1_bolt, alpha_b, f_u, d_bolt, t_plate, gamma_M2)
