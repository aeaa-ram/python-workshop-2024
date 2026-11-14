"""C_Rd,c - Coefficient for the shear resistance of concrete

EN 1992-1-1 cl. 6.2.2(1)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.2 Members not requiring design shear reinforcement

Status: consensus - 82 formula instance(s) in 2 independent source(s), 1 variant(s) merged.
Benchmarks: 84 of 84 source values reproduced.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/C_Rd_c.yaml (version 36d3631268f3) - do not edit by hand.
"""


def C_Rd_c(gamma_C):
    """Coefficient for the shear resistance of concrete [-]
    
    gamma_C  Partial factor for concrete [-]
    """
    return 0.18 / gamma_C
