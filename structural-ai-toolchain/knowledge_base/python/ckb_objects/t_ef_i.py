"""t_ef,i - EN 1992-1-1 cl. 6.3.2(1).  Units: N, mm, MPa, rad."""
# ckb t_ef_i f1222de51adb


def t_ef_i(A_tor, u_out):
    """Effective wall thickness for torsion [mm]
    EN 1992-1-1 cl. 6.3.2(1)
    
    A_tor  Area within the outer circumference of the section (torsion; hollow areas included) [mm2]
    u_out  Outer circumference of the cross-section [mm]
    """
    return A_tor / u_out
