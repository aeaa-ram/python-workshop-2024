"""z - Lever arm of internal forces

EN 1992-1-1 cl. 6.2.3(1)
6 Ultimate limit states (ULS) > 6.1 Bending with or without axial force

Status: disagreement - 3 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 3 of 5 source values reproduced.
WARNING: Sources disagree: 2 other formula(s) for this quantity could not be merged with the one
shown. The one shown has the most support; an engineer has to decide.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/z.yaml (version 52ff47b6b953) - do not edit by hand.
"""


def z(d):
    """Lever arm of internal forces [mm]
    
    d  Effective depth of the cross-section [mm]
    """
    return 0.9 * d
