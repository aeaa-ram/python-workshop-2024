"""Seed atom database — EN 1992-1-1 (Eurocode 2) + general mechanics.

Each formula exists here exactly once and is reused everywhere via
``sheet.apply()`` or ``custom.<name>()``. Atoms carry a taxonomy
(code / chapter / clause) so they can be browsed as a tree and searched,
and separate ``params`` (code coefficients, National-Annex overridable)
from user inputs.

Growth strategy: the fib/university ``structuralcodes`` project
(Eurocode & fib Model Code clauses in Python, Apache-2.0) is the intended
bulk source — copy/adapt its clause functions into atoms, keeping the
clause references. National-annex parameter tables become
``national_annex(...)`` entries; genuinely different methods become a new
atom sharing the same ``concept`` with a different ``jurisdiction``.

NOTE: values transcribed for a working prototype; formal QA is pending
(see docs/PITFALLS.md). Verify before production use.
"""

from src.library.registry import Atom, national_annex, register

# ================================================================== #
# Chapter 3 — Materials
# ================================================================== #
CH3 = "3 Materials"

register(Atom(
    atom_id="ec2.concrete.f_cm",
    concept="concrete.mean_strength",
    result="f_cm",
    expression="f_ck + 8",
    clause="EN 1992-1-1:2004 §3.1.2, Table 3.1",
    chapter=CH3,
    description="Mean concrete compressive strength from characteristic",
    units={"f_cm": "MPa", "f_ck": "MPa"},
))
register(Atom(
    atom_id="ec2.concrete.f_ctm",
    concept="concrete.tensile_strength",
    result="f_ctm",
    expression="0.30*f_ck**(2/3)",
    clause="EN 1992-1-1:2004 §3.1.2, Table 3.1",
    chapter=CH3,
    description="Mean axial tensile strength (concrete <= C50/60)",
    units={"f_ctm": "MPa", "f_ck": "MPa"},
    notes="For >= C55/67 use 2.12*ln(1+f_cm/10).",
))
register(Atom(
    atom_id="ec2.concrete.E_cm",
    concept="concrete.elastic_modulus",
    result="E_cm",
    expression="22000*(f_cm/10)**0.3",
    clause="EN 1992-1-1:2004 §3.1.3, Table 3.1",
    chapter=CH3,
    description="Secant modulus of elasticity at 28 days",
    units={"E_cm": "MPa", "f_cm": "MPa"},
))
register(Atom(
    atom_id="ec2.concrete.beta_cc_t",
    concept="concrete.strength_development",
    result="beta_cc_t",
    expression="exp(s_cem*(1 - sqrt(28/t)))",
    clause="EN 1992-1-1:2004 §3.1.2(6), Eq. (3.2)",
    chapter=CH3,
    description="Concrete strength development coefficient at age t",
    units={"beta_cc_t": "-", "s_cem": "-", "t": "days"},
    latex_names={"beta_cc_t": r"\beta_{cc}(t)", "s_cem": "s"},
    params={"s_cem": 0.25},
    notes="s_cem: 0.20 class R, 0.25 class N, 0.38 class S cement.",
))
register(Atom(
    atom_id="ec2.concrete.f_cm_t",
    concept="concrete.mean_strength_t",
    result="f_cm_t",
    expression="beta_cc_t * f_cm",
    clause="EN 1992-1-1:2004 §3.1.2(6), Eq. (3.1)",
    chapter=CH3,
    description="Mean concrete compressive strength at age t",
    units={"f_cm_t": "MPa", "beta_cc_t": "-", "f_cm": "MPa"},
    latex_names={"f_cm_t": r"f_{cm}(t)", "beta_cc_t": r"\beta_{cc}(t)"},
))
register(Atom(
    atom_id="ec2.concrete.E_cm_t",
    concept="concrete.elastic_modulus_t",
    result="E_cm_t",
    expression="(f_cm_t / f_cm)**0.3 * E_cm",
    clause="EN 1992-1-1:2004 §3.1.3(3), Eq. (3.5)",
    chapter=CH3,
    description="Secant modulus of elasticity at age t",
    units={"E_cm_t": "MPa", "f_cm_t": "MPa", "f_cm": "MPa", "E_cm": "MPa"},
    latex_names={"E_cm_t": r"E_{cm}(t)", "f_cm_t": r"f_{cm}(t)"},
))
register(Atom(
    atom_id="ec2.concrete.epsilon_cu3",
    concept="concrete.ultimate_strain",
    result="epsilon_cu3",
    expression="0.0035",
    clause="EN 1992-1-1:2004 §3.1.7, Table 3.1",
    chapter=CH3,
    description="Ultimate compressive strain (bilinear, <= C50/60)",
    units={"epsilon_cu3": "-"},
))
register(Atom(
    atom_id="ec2.general.alpha_e",
    concept="general.modular_ratio",
    result="alpha_e",
    expression="E_s / E_cm",
    clause="EN 1992-1-1 (modular ratio, short-term)",
    chapter=CH3,
    description="Modular ratio steel/concrete",
    units={"alpha_e": "-", "E_s": "MPa", "E_cm": "MPa"},
    latex_names={"alpha_e": r"\alpha_e"},
))

# ================================================================== #
# Chapter 6 — Ultimate limit states
# ================================================================== #
CH6 = "6 Ultimate limit states"

register(Atom(
    atom_id="ec2.bending.M_Rd_rect",
    concept="bending.moment_resistance_rect",
    result="M_Rd",
    expression="A_s*f_yd*(d - 0.4*x)",
    clause="EN 1992-1-1:2004 §6.1",
    chapter=CH6,
    description="Bending resistance, singly reinforced rectangular section",
    units={"M_Rd": "Nmm", "A_s": "mm^2", "f_yd": "MPa", "d": "mm", "x": "mm"},
))
register(Atom(
    atom_id="ec2.shear.V_Rd_c",
    concept="shear.resistance_without_links",
    result="V_Rd_c",
    expression="(C_Rd_c*k*(100*rho_l*f_ck)**(1/3) + k_1*sigma_cp)*b_w*d",
    clause="EN 1992-1-1:2004 §6.2.2(1), Eq. (6.2a)",
    chapter=CH6,
    description="Shear resistance of members without shear reinforcement",
    units={"V_Rd_c": "N", "f_ck": "MPa", "b_w": "mm", "d": "mm",
           "sigma_cp": "MPa", "rho_l": "-", "k": "-"},
    params={"C_Rd_c": 0.12, "k_1": 0.15},
    notes="C_Rd_c = 0.18/gamma_c (=0.12 recommended); k_1 NA-dependent.",
))
register(Atom(
    atom_id="ec2.shear.v_min",
    concept="shear.minimum_resistance",
    result="v_min",
    expression="0.035*k**(3/2)*f_ck**(1/2)",
    clause="EN 1992-1-1:2004 §6.2.2(1), Eq. (6.3N)",
    chapter=CH6,
    description="Minimum shear stress resistance",
    units={"v_min": "MPa", "k": "-", "f_ck": "MPa"},
))
register(Atom(
    atom_id="ec2.shear.k_depth",
    concept="shear.size_factor",
    result="k",
    expression="min(1 + sqrt(200/d), 2.0)",
    clause="EN 1992-1-1:2004 §6.2.2(1)",
    chapter=CH6,
    description="Size (depth) factor for shear",
    units={"k": "-", "d": "mm"},
))

# ================================================================== #
# Chapter 7 — Serviceability limit states
# ================================================================== #
CH7 = "7 Serviceability limit states"

register(Atom(
    atom_id="ec2.crack.rho_p_eff",
    concept="crack.effective_reinf_ratio",
    result="rho_p_eff",
    expression="A_s / A_c_eff",
    clause="EN 1992-1-1:2004 §7.3.2(3)",
    chapter=CH7,
    description="Effective reinforcement ratio",
    units={"rho_p_eff": "-", "A_s": "mm^2", "A_c_eff": "mm^2"},
    latex_names={"rho_p_eff": r"\rho_{p,eff}"},
))
register(Atom(
    atom_id="ec2.crack.s_r_max",
    concept="crack.max_spacing",
    result="s_r_max",
    expression="k_3*c + k_1*k_2*k_4*phi/rho_p_eff",
    clause="EN 1992-1-1:2004 §7.3.4(3), Eq. (7.11)",
    chapter=CH7,
    description="Maximum crack spacing",
    units={"s_r_max": "mm", "c": "mm", "phi": "mm", "rho_p_eff": "-"},
    latex_names={"s_r_max": r"s_{r,max}", "phi": r"\phi",
                 "rho_p_eff": r"\rho_{p,eff}"},
    params={"k_1": 0.8, "k_2": 0.5, "k_3": 3.4, "k_4": 0.425},
    notes="k_1 bond (0.8 high-bond), k_2 strain (0.5 bending), "
          "k_3/k_4 NA-dependent (3.4 / 0.425 recommended).",
))
register(Atom(
    atom_id="ec2.crack.w_k",
    concept="crack.characteristic_width",
    result="w_k",
    expression="s_r_max * eps_diff",
    clause="EN 1992-1-1:2004 §7.3.4(1), Eq. (7.8)",
    chapter=CH7,
    description="Characteristic crack width",
    units={"w_k": "mm", "s_r_max": "mm", "eps_diff": "-"},
    latex_names={"w_k": "w_{k}", "s_r_max": r"s_{r,max}",
                 "eps_diff": r"(\varepsilon_{sm}-\varepsilon_{cm})"},
))

# ---- National Annex examples (parameter overrides, SAME formula) ---- #
# The crack-spacing coefficient k_3 differs by National Annex; k_3 is
# still k_3 and still fits Eq. (7.11) — nothing is duplicated. Only the
# coefficient VALUE changes per jurisdiction.
national_annex(
    "crack.max_spacing", "EN-GB", {"k_3": 3.4, "k_4": 0.425},
    clause="UK NA to EN 1992-1-1, NA.2.20 (recommended values)",
)
# Illustrative jurisdiction with a deliberately DIFFERENT k_3, so the
# mechanism is unmistakable in demos/tests. Not a real NA value.
national_annex(
    "crack.max_spacing", "XX-DEMO", {"k_3": 1.0},
    clause="Illustrative National Annex (demo only — not a real value)",
    note="Shows a coefficient override changing the result; k_3 3.4 -> 1.0.",
)

# ---- Full-alternative example (DIFFERENT approach, same concept) ---- #
# Some jurisdictions/standards use a wholly different crack-width model
# with different inputs. Registered under the same concept but a distinct
# jurisdiction so resolve('crack.characteristic_width', 'ALT-DIRECT')
# returns THIS instead of the EC2 spacing*strain form.
register(Atom(
    atom_id="alt.crack.w_k_direct",
    concept="crack.characteristic_width",
    jurisdiction="ALT-DIRECT",
    result="w_k",
    expression="beta * s_rm * (sigma_s/E_s)",
    clause="Alternative direct model (illustrative, different inputs)",
    code="Alternative",
    chapter="Crack control",
    description="Crack width via mean spacing and steel strain directly",
    units={"w_k": "mm", "s_rm": "mm", "sigma_s": "MPa", "E_s": "MPa"},
    params={"beta": 1.7},
    notes="Demonstrates a different-approach variant sharing the concept.",
))

# ================================================================== #
# General mechanics (not code-specific)
# ================================================================== #
GEN = "Mechanics"

register(Atom(
    atom_id="mech.section.W_el_rect",
    concept="section.elastic_modulus_rect",
    result="W_el",
    expression="b*h**2/6",
    clause="Elastic section modulus, rectangle",
    code="Mechanics", chapter=GEN,
    description="Elastic section modulus of a rectangular section",
    units={"W_el": "mm^3", "b": "mm", "h": "mm"},
    latex_names={"W_el": "W_{el}"},
))
register(Atom(
    atom_id="mech.section.I_rect",
    concept="section.second_moment_rect",
    result="I",
    expression="b*h**3/12",
    clause="Second moment of area, rectangle",
    code="Mechanics", chapter=GEN,
    description="Second moment of area of a rectangular section",
    units={"I": "mm^4", "b": "mm", "h": "mm"},
))
register(Atom(
    atom_id="mech.statics.M_max_udl",
    concept="statics.moment_ss_udl",
    result="M_max",
    expression="q*L**2/8",
    clause="Simply supported beam, uniform load",
    code="Mechanics", chapter=GEN,
    description="Max bending moment, simply supported beam under UDL",
    units={"M_max": "kNm", "q": "kN/m", "L": "m"},
    latex_names={"M_max": "M_{max}"},
))
register(Atom(
    atom_id="mech.statics.delta_max_udl",
    concept="statics.deflection_ss_udl",
    result="delta_max",
    expression="5*q*L**4/(384*E*I)",
    clause="Simply supported beam, uniform load",
    code="Mechanics", chapter=GEN,
    description="Max deflection, simply supported beam under UDL",
    units={"delta_max": "mm", "q": "N/mm", "L": "mm", "E": "MPa", "I": "mm^4"},
    latex_names={"delta_max": r"\delta_{max}"},
))
