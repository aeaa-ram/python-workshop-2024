"""ν - Strength reduction factor for concrete cracked in shear

EN 1992-1-1 cl. 6.2.2(6), expr. (6.6N)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.2 Members not requiring design shear reinforcement

Status: disagreement - 80 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 80 of 80 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 shear.v(fck) (200 samples).
WARNING: Sources disagree: 1 other formula(s) for this quantity could not be merged with the one
shown. The one shown has the most support; an engineer has to decide.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/nu.yaml (version 53e1b871d1ed) - do not edit by hand.
"""


def nu(f_ck):
    """Strength reduction factor for concrete cracked in shear [-]
    
    f_ck  Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    """
    return 0.6 * (1 - f_ck / 250)
