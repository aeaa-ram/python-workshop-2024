"""f_ct,eff - EN 1992-1-1 cl. 7.3.4(2).  Units: N, mm, MPa, rad."""
# ckb f_ct_eff 1e41d7990909
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm


def f_ct_eff(f_ctm):
    """Mean tensile strength of the concrete when the first cracks may occur [MPa]
    EN 1992-1-1 cl. 7.3.4(2)
    
    f_ctm  Mean axial tensile strength of concrete [MPa]
    """
    return f_ctm


def f_ct_eff_chain(f_ck):
    """f_ct,eff from the primary inputs."""
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    return f_ct_eff(f_ctm)
