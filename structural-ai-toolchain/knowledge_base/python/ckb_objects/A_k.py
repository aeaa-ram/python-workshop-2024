"""A_k - EN 1992-1-1 cl. 6.3.2(1).  Units: N, mm, MPa, rad."""
# ckb A_k e88c5dc793a4
from .t_ef_i import t_ef_i as _t_ef_i


def A_k(b, t_ef_i, h):
    """Area enclosed by the centre-lines of the connecting walls (rectangular section) [mm2]
    EN 1992-1-1 cl. 6.3.2(1)
    
    b       Width of the cross-section [mm]
    t_ef_i  Effective wall thickness for torsion [mm]
    h       Overall depth of the cross-section [mm]
    """
    return (b - t_ef_i) * (h - t_ef_i)


def A_k_chain(b, A_tor, u_out, h):
    """A_k from the primary inputs."""
    t_ef_i = _t_ef_i(A_tor, u_out)
    return A_k(b, t_ef_i, h)
