"""(EI)_eff - EN 1994-1-1 cl. 6.7.3.3(3), expr. (6.40).  Units: N, mm, MPa, rad."""
# ckb EI_eff f67896ecf78e
from .f_cm import f_cm as _f_cm
from .E_cm import E_cm as _E_cm


def EI_eff(E_steel, I_a, I_s, K_e, E_cm, I_conc):
    """Effective flexural stiffness of a composite column [N·mm²]
    EN 1994-1-1 cl. 6.7.3.3(3), expr. (6.40)
    
    E_steel  Modulus of elasticity of structural steel [MPa]
    I_a      Second moment of area of the structural steel section [mm4]
    I_s      Second moment of area of the reinforcement [mm4]
    K_e      Correction factor for the effective flexural stiffness of a composite column [-]
    E_cm     Secant modulus of elasticity of concrete [MPa]
    I_conc   Second moment of area of the concrete section [mm4]
    """
    return E_steel * (I_a + I_s) + K_e * E_cm * I_conc


def EI_eff_chain(E_steel, I_a, I_s, K_e, f_ck, I_conc):
    """(EI)_eff from the primary inputs."""
    f_cm = _f_cm(f_ck)
    E_cm = _E_cm(f_cm)
    return EI_eff(E_steel, I_a, I_s, K_e, E_cm, I_conc)
