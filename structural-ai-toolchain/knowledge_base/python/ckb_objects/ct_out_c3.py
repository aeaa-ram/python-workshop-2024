"""(c/t)_lim,3 - EN 1993-1-1 cl. 5.5.2, Table 5.2.  Units: N, mm, MPa, rad."""
# ckb ct_out_c3 5d2268d7d5c5
from .eps_y import eps_y as _eps_y


def ct_out_c3(eps_y):
    """Class 3 limit of c/t, outstand flange in compression [-]
    EN 1993-1-1 cl. 5.5.2, Table 5.2
    
    eps_y  Material factor for the classification of cross-sections [-]
    """
    return 14 * eps_y


def ct_out_c3_chain(f_y):
    """(c/t)_lim,3 from the primary inputs."""
    eps_y = _eps_y(f_y)
    return ct_out_c3(eps_y)
