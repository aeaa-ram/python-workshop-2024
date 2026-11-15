"""(c/t)_lim,3 - EN 1993-1-1 cl. 5.5.2, Table 5.2.  Units: N, mm, MPa, rad."""
# ckb ct_int_b3 ecb500ef2980
from .eps_y import eps_y as _eps_y


def ct_int_b3(eps_y):
    """Class 3 limit of c/t, internal part in bending [-]
    EN 1993-1-1 cl. 5.5.2, Table 5.2
    
    eps_y  Material factor for the classification of cross-sections [-]
    """
    return 124 * eps_y


def ct_int_b3_chain(f_y):
    """(c/t)_lim,3 from the primary inputs."""
    eps_y = _eps_y(f_y)
    return ct_int_b3(eps_y)
