"""Seed atoms — EN 1994-1-1 (Eurocode 4), headed stud shear connectors.

Same rules as ``atoms_ec2``: each formula exists once, carries its clause
and equation number, and code coefficients live in ``params`` so a
National Annex can override them (gamma_V is NDP: recommended 1.25).

NOTE: transcribed for a working prototype; formal QA pending
(docs/PITFALLS.md). Verify before production use.
"""

from src.library.registry import Atom, register

CODE = "EN 1994-1-1"
CH6 = "6 Ultimate limit states"

register(Atom(
    atom_id="ec4.stud.P_Rd_shank",
    concept="stud.resistance_shank",
    result="P_Rd_1",
    expression="0.8*f_u*pi*d**2/4/gamma_V",
    clause="EN 1994-1-1:2004 §6.6.3.1(1), Eq. (6.18)",
    code=CODE, chapter=CH6,
    description="Design shear resistance of a headed stud — shank failure",
    units={"P_Rd_1": "kN", "f_u": "MPa", "d": "mm", "gamma_V": "-"},
    latex_names={"P_Rd_1": "P_{Rd,1}", "gamma_V": r"\gamma_V"},
    params={"gamma_V": 1.25},
    notes="f_u <= 500 MPa; 16 mm <= d <= 25 mm.",
))
register(Atom(
    atom_id="ec4.stud.P_Rd_concrete",
    concept="stud.resistance_concrete",
    result="P_Rd_2",
    expression="0.29*alpha*d**2*sqrt(f_ck*E_cm)/gamma_V",
    clause="EN 1994-1-1:2004 §6.6.3.1(1), Eq. (6.19)",
    code=CODE, chapter=CH6,
    description="Design shear resistance of a headed stud — concrete "
                "crushing",
    units={"P_Rd_2": "kN", "alpha": "-", "d": "mm", "f_ck": "MPa",
           "E_cm": "MPa", "gamma_V": "-"},
    latex_names={"P_Rd_2": "P_{Rd,2}", "gamma_V": r"\gamma_V"},
    params={"gamma_V": 1.25},
))
register(Atom(
    atom_id="ec4.stud.alpha",
    concept="stud.alpha",
    result="alpha",
    expression="Piecewise((1, h_sc/d >= 4), (0.2*(h_sc/d + 1), True))",
    clause="EN 1994-1-1:2004 §6.6.3.1(1), Eqs. (6.20)-(6.21)",
    code=CODE, chapter=CH6,
    description="Stud height factor",
    units={"alpha": "-", "h_sc": "mm", "d": "mm"},
    notes="Valid for 3 <= h_sc/d; below 3 the rules do not apply.",
))
