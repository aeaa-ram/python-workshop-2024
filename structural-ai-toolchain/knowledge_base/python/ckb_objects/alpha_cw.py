"""α_cw - Coefficient for the state of stress in the compression chord

EN 1992-1-1 cl. 6.2.3(3)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.3 Members requiring design shear reinforcement

Status: single source - 4 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 4 of 5 source values reproduced.
Reference: differs with structuralcodes 0.7.3 shear.alpha_cw(NEd, Ac, fcd) (200 samples).
WARNING: Seen in one source only: not yet confirmed by a second, independent calculation.
WARNING: Differs from the independent reference (structuralcodes 0.7.3, shear.alpha_cw(NEd, Ac,
fcd)) in 26 of 200 samples.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/alpha_cw.yaml (version 3c1d2c6d1f47) - do not edit by hand.
"""
from .f_cd import f_cd as _f_cd


def alpha_cw(sigma_cp, f_cd):
    """Coefficient for the state of stress in the compression chord [-]
    
    sigma_cp  Concrete compressive stress from axial load or prestress (compression positive) [MPa]
    f_cd      Design value of concrete compressive strength [MPa]
    """
    return 1 if sigma_cp < 1 else 1 + sigma_cp / f_cd if sigma_cp < f_cd / 4 else 1.25 if sigma_cp < f_cd / 2 else 2.5 - 2.5 * sigma_cp / f_cd if sigma_cp < f_cd else 'σcp too great'


def alpha_cw_chain(sigma_cp, f_ck, gamma_C):
    """α_cw from the primary inputs, through the objects it depends on."""
    f_cd = _f_cd(f_ck, gamma_C)
    return alpha_cw(sigma_cp, f_cd)
