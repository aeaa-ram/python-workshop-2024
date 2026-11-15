"""v_min - EN 1992-1-1 cl. 6.2.2(1), expr. (6.3N).  Units: N, mm, MPa, rad."""
# ckb v_min d9d868be83be
from .k import k as _k


def v_min(k, f_ck):
    """Minimum shear strength [MPa]
    EN 1992-1-1 cl. 6.2.2(1), expr. (6.3N)
    
    k     Size factor for shear [-]
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 0.035 * k ** 1.5 * f_ck ** 0.5


def v_min_chain(d, f_ck):
    """v_min from the primary inputs."""
    k = _k(d)
    return v_min(k, f_ck)
