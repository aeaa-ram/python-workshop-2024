"""N_pl,Rd - EN 1994-1-1 cl. 6.7.3.2(1), expr. (6.30).  Units: N, mm, MPa, rad."""
# ckb N_pl_Rd 94097259d69f
from .f_yd_a import f_yd_a as _f_yd_a
from .f_cd import f_cd as _f_cd
from .f_yd import f_yd as _f_yd


def N_pl_Rd(A_a, f_yd_a, A_c, f_cd, A_s, f_yd):
    """Plastic resistance to compression of a composite cross-section [N]
    EN 1994-1-1 cl. 6.7.3.2(1), expr. (6.30)
    
    A_a     Cross-sectional area of the structural steel section [mm2]
    f_yd_a  Design yield strength of structural steel [MPa]
    A_c     Cross-sectional area of concrete [mm2]
    f_cd    Design compressive strength of concrete [MPa]
    A_s     Area of tension reinforcement [mm2]
    f_yd    Design yield strength of reinforcement [MPa]
    α_cc = 1 in EN 1994-1-1
    """
    return A_a * f_yd_a + 0.85 * A_c * f_cd + A_s * f_yd


def N_pl_Rd_chain(A_a, f_y, gamma_M0, A_c, f_ck, gamma_C, A_s, f_yk, gamma_S):
    """N_pl,Rd from the primary inputs."""
    alpha_cc = 1
    f_yd_a = _f_yd_a(f_y, gamma_M0)
    f_cd = _f_cd(alpha_cc, f_ck, gamma_C)
    f_yd = _f_yd(f_yk, gamma_S)
    return N_pl_Rd(A_a, f_yd_a, A_c, f_cd, A_s, f_yd)
