"""(c/t)_lim,2 - EN 1993-1-1 cl. 5.5.2, Table 5.2.  Units: N, mm, MPa, rad."""
# ckb ct_out_c2 bef3022a54bf
from .eps_y import eps_y as _eps_y


def ct_out_c2(eps_y):
    """Class 2 limit of c/t, outstand flange in compression [-]
    EN 1993-1-1 cl. 5.5.2, Table 5.2
    
    eps_y  Material factor for the classification of cross-sections [-]
    """
    return 10 * eps_y


def ct_out_c2_chain(f_y):
    """(c/t)_lim,2 from the primary inputs."""
    eps_y = _eps_y(f_y)
    return ct_out_c2(eps_y)
