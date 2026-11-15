"""N_cr - EN 1993-1-1 cl. 6.3.1.2(1).  Units: N, mm, MPa, rad."""
# ckb N_cr f0f4ea1b2764
from math import pi


def N_cr(E_steel, I_sec, L_cr):
    """Elastic critical force for flexural buckling [N]
    EN 1993-1-1 cl. 6.3.1.2(1)
    
    E_steel  Modulus of elasticity of structural steel [MPa]
    I_sec    Second moment of area of the steel section about the buckling axis [mm4]
    L_cr     Buckling length in the plane considered [mm]
    """
    return pi ** 2 * E_steel * I_sec / L_cr ** 2
