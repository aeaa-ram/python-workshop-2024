"""f_ctk,0.05 - EN 1992-1-1 cl. 3.1.2, Table 3.1.  Units: N, mm, MPa, rad."""
# ckb f_ctk_005 71c93a93007b
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm


def f_ctk_005(f_ctm):
    """Characteristic axial tensile strength of concrete (5 % fractile) [MPa]
    EN 1992-1-1 cl. 3.1.2, Table 3.1
    
    f_ctm  Mean axial tensile strength of concrete [MPa]
    """
    return 0.7 * f_ctm


def f_ctk_005_chain(f_ck):
    """f_ctk,0.05 from the primary inputs."""
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    return f_ctk_005(f_ctm)
