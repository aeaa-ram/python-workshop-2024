"""v_Ed,0 - EN 1992-1-1 cl. 6.4.5(3), expr. (6.53).  Units: N, mm, MPa, rad."""
# ckb v_Ed_0 f8be3f0fadc1
from .u_0 import u_0 as _u_0
from .d_eff_p import d_eff_p as _d_eff_p


def v_Ed_0(beta_p, V_Ed, u_0, d_eff_p):
    """Punching shear stress at the column face [MPa]
    EN 1992-1-1 cl. 6.4.5(3), expr. (6.53)
    
    beta_p   Factor for the eccentricity of the support reaction (punching) [-]
    V_Ed     Design shear force [N]
    u_0      Perimeter of a rectangular internal column [mm]
    d_eff_p  Effective depth of the slab for punching [mm]
    """
    return beta_p * V_Ed / (u_0 * d_eff_p)


def v_Ed_0_chain(beta_p, V_Ed, c_1, c_2, d_y, d_z):
    """v_Ed,0 from the primary inputs."""
    u_0 = _u_0(c_1, c_2)
    d_eff_p = _d_eff_p(d_y, d_z)
    return v_Ed_0(beta_p, V_Ed, u_0, d_eff_p)
