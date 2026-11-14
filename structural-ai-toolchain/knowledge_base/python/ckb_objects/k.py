"""k - Size factor for shear

EN 1992-1-1 cl. 6.2.2(1)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.2 Members not requiring design shear reinforcement

Status: consensus - 86 formula instance(s) in 2 independent source(s), 1 variant(s) merged.
Benchmarks: 88 of 88 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 shear._k(d) (200 samples).

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/k.yaml (version 3f4078a78ea5) - do not edit by hand.
"""
from math import sqrt


def k(d):
    """Size factor for shear [-]
    
    d  Effective depth of the cross-section [mm]
    """
    return min(1 + sqrt(200 / d), 2)
