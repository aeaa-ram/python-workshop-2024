"""ρ_l - Longitudinal reinforcement ratio

EN 1992-1-1 cl. 6.2.2(1)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.2 Members not requiring design shear reinforcement

Status: disagreement - 86 formula instance(s) in 2 independent source(s), 2 variant(s) merged.
Benchmarks: 88 of 88 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 shear._rho_L(Asl, bw, d) (200 samples).
WARNING: Sources disagree: 1 other formula(s) for this quantity could not be merged with the one
shown. The one shown has the most support; an engineer has to decide.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/rho_l.yaml (version 42da2ccdd6b3) - do not edit by hand.
"""


def rho_l(A_sl, d, b_w):
    """Longitudinal reinforcement ratio [-]
    
    A_sl  Area of tensile reinforcement extending at least l_bd + d beyond the section [mm2]
    d     Effective depth of the cross-section [mm]
    b_w   Smallest width of the cross-section in the tensile area [mm]
    """
    return min(A_sl / (d * b_w), 0.02)
