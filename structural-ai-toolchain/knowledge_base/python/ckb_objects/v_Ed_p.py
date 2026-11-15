"""v_Ed - EN 1992-1-1 cl. 6.4.3(3), expr. (6.38).  Units: N, mm, MPa, rad."""
# ckb v_Ed_p e840993bd7e7
from .d_eff_p import d_eff_p as _d_eff_p
from .u_1 import u_1 as _u_1


def v_Ed_p(beta_p, V_Ed, u_1, d_eff_p):
    """Punching shear stress at the basic control perimeter [MPa]
    EN 1992-1-1 cl. 6.4.3(3), expr. (6.38)
    
    beta_p   Factor for the eccentricity of the support reaction (punching) [-]
    V_Ed     Design shear force [N]
    u_1      Basic control perimeter at 2d from a rectangular internal column [mm]
    d_eff_p  Effective depth of the slab for punching [mm]
    """
    return beta_p * V_Ed / (u_1 * d_eff_p)


def v_Ed_p_chain(beta_p, V_Ed, c_1, c_2, d_y, d_z):
    """v_Ed from the primary inputs."""
    d_eff_p = _d_eff_p(d_y, d_z)
    u_1 = _u_1(c_1, c_2, d_eff_p)
    return v_Ed_p(beta_p, V_Ed, u_1, d_eff_p)
