"""η_v+t - EN 1993-1-8 cl. 3.6.1(1), Table 3.4.  Units: N, mm, MPa, rad."""
# ckb util_vt db86ef03fde3
from .F_v_Rd import F_v_Rd as _F_v_Rd
from .F_t_Rd import F_t_Rd as _F_t_Rd


def util_vt(F_v_Ed, F_v_Rd, F_t_Ed, F_t_Rd):
    """Utilisation of a bolt in combined shear and tension [-]
    EN 1993-1-8 cl. 3.6.1(1), Table 3.4
    
    F_v_Ed  Design shear force per bolt [N]
    F_v_Rd  Shear resistance of a bolt per shear plane [N]
    F_t_Ed  Design tensile force per bolt [N]
    F_t_Rd  Tension resistance of a bolt [N]
    """
    return F_v_Ed / F_v_Rd + F_t_Ed / (1.4 * F_t_Rd)


def util_vt_chain(F_v_Ed, alpha_v, f_ub, A_bolt, gamma_M2, F_t_Ed, k_2_bolt, A_s_bolt):
    """η_v+t from the primary inputs."""
    F_v_Rd = _F_v_Rd(alpha_v, f_ub, A_bolt, gamma_M2)
    F_t_Rd = _F_t_Rd(k_2_bolt, f_ub, A_s_bolt, gamma_M2)
    return util_vt(F_v_Ed, F_v_Rd, F_t_Ed, F_t_Rd)
