"""N_t,Rd - EN 1993-1-1 cl. 6.2.3(2), expr. (6.6), (6.7).  Units: N, mm, MPa, rad."""
# ckb N_t_Rd d23d88ff1a10
from .N_pl_Rd_a import N_pl_Rd_a as _N_pl_Rd_a
from .N_u_Rd import N_u_Rd as _N_u_Rd


def N_t_Rd(N_pl_Rd_a, N_u_Rd):
    """Design tension resistance [N]
    EN 1993-1-1 cl. 6.2.3(2), expr. (6.6), (6.7)
    
    N_pl_Rd_a  Design plastic resistance of the gross steel section (tension; compression of class 1 to 3) [N]
    N_u_Rd     Design ultimate resistance of the net section at holes [N]
    """
    return min(N_pl_Rd_a, N_u_Rd)


def N_t_Rd_chain(A_sec, f_y, gamma_M0, A_net, f_u, gamma_M2):
    """N_t,Rd from the primary inputs."""
    N_pl_Rd_a = _N_pl_Rd_a(A_sec, f_y, gamma_M0)
    N_u_Rd = _N_u_Rd(A_net, f_u, gamma_M2)
    return N_t_Rd(N_pl_Rd_a, N_u_Rd)
