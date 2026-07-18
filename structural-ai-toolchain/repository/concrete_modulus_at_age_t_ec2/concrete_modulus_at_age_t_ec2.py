"""Concrete Modulus at Age t (EN 1992-1-1 §3.1.3)

Native example tool (authored directly, not ground from a legacy file).
It exists to demonstrate SINGLE SOURCE OF TRUTH: the whole
beta_cc(t) -> f_cm(t) -> E_cm(t) chain is pulled from the shared library
via sheet.apply(), so this tool, the crack-width tool and any future
deflection/bending tool all use the identical Eurocode formulas — edit
them once in src/library, every tool updates.

    python main.py register concrete_modulus_at_age_t_ec2
    python main.py qa       concrete_modulus_at_age_t_ec2
    python main.py render   concrete_modulus_at_age_t_ec2 --pdf
"""

from src.models.calculation import CalcSheet


def build_sheet() -> CalcSheet:
    sheet = CalcSheet(
        title="Concrete Modulus at Age t (EN 1992-1-1 3.1.3)",
        description="Time-development of the concrete secant modulus of "
                    "elasticity, from cement class and mean 28-day "
                    "strength. Shared upstream of crack-width, deflection "
                    "and bending-stiffness calculations.",
        reference="EN 1992-1-1:2004 §3.1.2, §3.1.3",
        author="Toolchain example",
        tool_id="concrete_modulus_at_age_t_ec2",
    )

    sheet.section("Input Parameters")
    sheet.define("s_cem", 0.25, unit="-",
                 description="Cement class coefficient (0.20 R / 0.25 N / "
                             "0.38 S)")
    sheet.define("t", 7, unit="days", description="Concrete age at loading")
    sheet.define("f_cm", 38, unit="MPa",
                 description="Mean compressive strength at 28 days (C30/37)")
    sheet.define("E_cm", 32837, unit="MPa",
                 description="Secant modulus at 28 days (C30/37)")

    sheet.section("Calculation (all formulas from the shared library)")
    # Single source of truth — no formula is typed here, each comes from
    # src/library/atoms_ec2.py and is reused wherever it is needed.
    sheet.apply("beta_cc_t", "ec2.concrete.beta_cc_t", unit="-")
    sheet.apply("f_cm_t", "ec2.concrete.f_cm_t", unit="MPa")
    sheet.apply("E_cm_t", "ec2.concrete.E_cm_t", unit="MPa")

    sheet.section("Verification")
    sheet.check("E_cm_t <= E_cm",
                "Modulus at early age does not exceed the 28-day value")
    return sheet


if __name__ == "__main__":
    from src.output_engine import render_all

    print(render_all(build_sheet(), "reports"))
