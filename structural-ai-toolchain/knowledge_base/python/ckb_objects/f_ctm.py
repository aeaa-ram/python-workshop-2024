"""f_ctm - EN 1992-1-1 cl. 3.1.2, Table 3.1.  Units: N, mm, MPa, rad."""
# ckb f_ctm dd3ccf4135da
from math import log as ln
from .f_cm import f_cm as _f_cm


def f_ctm(f_ck, f_cm):
    """Mean axial tensile strength of concrete [MPa]
    EN 1992-1-1 cl. 3.1.2, Table 3.1
    
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    f_cm  Mean compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 0.3 * f_ck ** (2 / 3) if f_ck <= 50 else 2.12 * ln(1 + f_cm / 10)


def f_ctm_chain(f_ck):
    """f_ctm from the primary inputs."""
    f_cm = _f_cm(f_ck)
    return f_ctm(f_ck, f_cm)
