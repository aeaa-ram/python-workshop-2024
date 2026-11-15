"""(c/t)_lim,1 - EN 1993-1-1 cl. 5.5.2, Table 5.2.  Units: N, mm, MPa, rad."""
# ckb ct_int_c1 92d7367716d7
from .eps_y import eps_y as _eps_y


def ct_int_c1(eps_y):
    """Class 1 limit of c/t, internal part in compression [-]
    EN 1993-1-1 cl. 5.5.2, Table 5.2
    
    eps_y  Material factor for the classification of cross-sections [-]
    """
    return 33 * eps_y


def ct_int_c1_chain(f_y):
    """(c/t)_lim,1 from the primary inputs."""
    eps_y = _eps_y(f_y)
    return ct_int_c1(eps_y)
