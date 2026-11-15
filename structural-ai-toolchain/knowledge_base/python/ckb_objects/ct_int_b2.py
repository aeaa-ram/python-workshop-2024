"""(c/t)_lim,2 - EN 1993-1-1 cl. 5.5.2, Table 5.2.  Units: N, mm, MPa, rad."""
# ckb ct_int_b2 4f5d6c5a702a
from .eps_y import eps_y as _eps_y


def ct_int_b2(eps_y):
    """Class 2 limit of c/t, internal part in bending [-]
    EN 1993-1-1 cl. 5.5.2, Table 5.2
    
    eps_y  Material factor for the classification of cross-sections [-]
    """
    return 83 * eps_y


def ct_int_b2_chain(f_y):
    """(c/t)_lim,2 from the primary inputs."""
    eps_y = _eps_y(f_y)
    return ct_int_b2(eps_y)
