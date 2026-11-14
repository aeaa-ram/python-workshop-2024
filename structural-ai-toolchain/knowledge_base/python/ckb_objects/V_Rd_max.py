"""V_Rd,max - Design shear resistance governed by crushing of the compression struts

EN 1992-1-1 cl. 6.2.3(3), expr. (6.9)
6 Ultimate limit states (ULS) > 6.2 Shear > 6.2.3 Members requiring design shear reinforcement

Status: disagreement - 2 formula instance(s) in 1 independent source(s), 1 variant(s) merged.
Benchmarks: 4 of 4 source values reproduced.
Reference: agrees with structuralcodes 0.7.3 VRdmax(bw, z, fck, theta, NEd=0, Ac, fcd) (200 samples).
WARNING: Sources disagree: 1 other formula(s) for this quantity could not be merged with the one
shown. The one shown has the most support; an engineer has to decide.

Units: N, mm, MPa (N/mm2), rad.
Generated from objects/V_Rd_max.yaml (version aeba502c9bb0) - do not edit by hand.
"""
from math import tan
def cot(x):
    return 1.0 / tan(x)

from .f_cd import f_cd as _f_cd
from .alpha_cw import alpha_cw as _alpha_cw
from .z import z as _z


def V_Rd_max(alpha_cw, b_w, z, nu_1, f_ck, gamma_C, theta):
    """Design shear resistance governed by crushing of the compression struts [N]
    
    alpha_cw  Coefficient for the state of stress in the compression chord [-]
    b_w       Smallest width of the cross-section in the tensile area [mm]
    z         Lever arm of internal forces [mm]
    nu_1      Strength reduction factor for concrete cracked in shear (strut) [-]
    f_ck      Characteristic compressive cylinder strength of concrete at 28 days [MPa]
    gamma_C   Partial factor for concrete [-]
    theta     Angle between the concrete compression strut and the beam axis [rad]
    """
    return alpha_cw * b_w * z * nu_1 * f_ck / gamma_C / (cot(theta) + tan(theta))


def V_Rd_max_chain(sigma_cp, f_ck, gamma_C, b_w, d, nu_1, theta):
    """V_Rd,max from the primary inputs, through the objects it depends on."""
    f_cd = _f_cd(f_ck, gamma_C)
    alpha_cw = _alpha_cw(sigma_cp, f_cd)
    z = _z(d)
    return V_Rd_max(alpha_cw, b_w, z, nu_1, f_ck, gamma_C, theta)
