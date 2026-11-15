"""f_ywd,ef - EN 1992-1-1 cl. 6.4.5(1).  Units: N, mm, MPa, rad."""
# ckb f_ywd_ef 7d4f451cddaa
from .d_eff_p import d_eff_p as _d_eff_p
from .f_ywd import f_ywd as _f_ywd


def f_ywd_ef(d_eff_p, f_ywd):
    """Effective design strength of the punching shear reinforcement [MPa]
    EN 1992-1-1 cl. 6.4.5(1)
    
    d_eff_p  Effective depth of the slab for punching [mm]
    f_ywd    Design yield strength of the shear reinforcement [MPa]
    """
    return min(250 + 0.25 * d_eff_p, f_ywd)


def f_ywd_ef_chain(d_y, d_z, f_ywk, gamma_S):
    """f_ywd,ef from the primary inputs."""
    d_eff_p = _d_eff_p(d_y, d_z)
    f_ywd = _f_ywd(f_ywk, gamma_S)
    return f_ywd_ef(d_eff_p, f_ywd)
