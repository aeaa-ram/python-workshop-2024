"""c_nom - EN 1992-1-1 cl. 4.4.1.1(2), expr. (4.1).  Units: N, mm, MPa, rad."""
# ckb cover_nom 617b4d98dc97
from .c_min import c_min as _c_min


def cover_nom(c_min, dc_dev):
    """Nominal cover [mm]
    EN 1992-1-1 cl. 4.4.1.1(2), expr. (4.1)
    
    c_min   Minimum cover [mm]
    dc_dev  Allowance in design for deviation (cover) [mm]
    """
    return c_min + dc_dev


def cover_nom_chain(phi, c_min_dur, dc_dev):
    """c_nom from the primary inputs."""
    c_min = _c_min(phi, c_min_dur)
    return cover_nom(c_min, dc_dev)
