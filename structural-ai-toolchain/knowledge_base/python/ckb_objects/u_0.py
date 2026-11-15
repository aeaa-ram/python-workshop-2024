"""u_0 - EN 1992-1-1 cl. 6.4.5(3).  Units: N, mm, MPa, rad."""
# ckb u_0 b13fb155d29a


def u_0(c_1, c_2):
    """Perimeter of a rectangular internal column [mm]
    EN 1992-1-1 cl. 6.4.5(3)
    
    c_1  Column dimension parallel to the eccentricity (punching) [mm]
    c_2  Column dimension perpendicular to the eccentricity (punching) [mm]
    """
    return 2 * (c_1 + c_2)
