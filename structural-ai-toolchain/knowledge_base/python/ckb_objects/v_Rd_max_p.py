"""v_Rd,max - EN 1992-1-1 cl. 6.4.5(3).  Units: N, mm, MPa, rad."""
# ckb v_Rd_max_p cca7abea2010
from .nu import nu as _nu
from .f_cd import f_cd as _f_cd


def v_Rd_max_p(nu, f_cd):
    """Maximum punching shear stress at the column face [MPa]
    EN 1992-1-1 cl. 6.4.5(3)
    
    nu    Strength reduction factor for concrete cracked in shear [-]
    f_cd  Design compressive strength of concrete [MPa]
    """
    return 0.4 * nu * f_cd


def v_Rd_max_p_chain(f_ck, alpha_cc, gamma_C):
    """v_Rd,max from the primary inputs."""
    nu = _nu(f_ck)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    return v_Rd_max_p(nu, f_cd)
