"""A_s,min - EN 1992-1-1 cl. 9.2.1.1(1), expr. (9.1N).  Units: N, mm, MPa, rad."""
# ckb A_s_min 92bb66569379
from .f_cm import f_cm as _f_cm
from .f_ctm import f_ctm as _f_ctm


def A_s_min(f_ctm, f_yk, b_t, d):
    """Minimum area of longitudinal tension reinforcement in beams [mm2]
    EN 1992-1-1 cl. 9.2.1.1(1), expr. (9.1N)
    
    f_ctm  Mean axial tensile strength of concrete [MPa]
    f_yk   Characteristic yield strength of reinforcement [MPa]
    b_t    Mean width of the tension zone [mm]
    d      Effective depth of the cross-section [mm]
    """
    return max(0.26 * f_ctm / f_yk * b_t * d, 0.0013 * b_t * d)


def A_s_min_chain(f_ck, f_yk, b_t, d):
    """A_s,min from the primary inputs."""
    f_cm = _f_cm(f_ck)
    f_ctm = _f_ctm(f_ck, f_cm)
    return A_s_min(f_ctm, f_yk, b_t, d)
