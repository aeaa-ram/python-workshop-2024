"""F_w,Rd - EN 1993-1-8 cl. 4.5.3.3(2), expr. (4.3).  Units: N, mm, MPa, rad."""
# ckb F_w_Rd 276a8fba08ab
from .f_vw_d import f_vw_d as _f_vw_d


def F_w_Rd(f_vw_d, a_weld):
    """Design resistance of a fillet weld per unit length (simplified method) [N/mm]
    EN 1993-1-8 cl. 4.5.3.3(2), expr. (4.3)
    
    f_vw_d  Design shear strength of a fillet weld [MPa]
    a_weld  Effective throat thickness of the fillet weld [mm]
    """
    return f_vw_d * a_weld


def F_w_Rd_chain(f_u, beta_w, gamma_M2, a_weld):
    """F_w,Rd from the primary inputs."""
    f_vw_d = _f_vw_d(f_u, beta_w, gamma_M2)
    return F_w_Rd(f_vw_d, a_weld)
