"""u_k - EN 1992-1-1 cl. 6.3.2(3).  Units: N, mm, MPa, rad."""
# ckb u_k 5f362b46be24
from .t_ef_i import t_ef_i as _t_ef_i


def u_k(b, t_ef_i, h):
    """Perimeter of the area A_k (rectangular section) [mm]
    EN 1992-1-1 cl. 6.3.2(3)
    
    b       Width of the cross-section [mm]
    t_ef_i  Effective wall thickness for torsion [mm]
    h       Overall depth of the cross-section [mm]
    """
    return 2 * (b - t_ef_i + h - t_ef_i)


def u_k_chain(b, A_tor, u_out, h):
    """u_k from the primary inputs."""
    t_ef_i = _t_ef_i(A_tor, u_out)
    return u_k(b, t_ef_i, h)
