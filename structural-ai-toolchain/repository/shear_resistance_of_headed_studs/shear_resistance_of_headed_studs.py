"""Shear resistance of headed studs

Converted by the agentic ingestion workflow from stud_resistance_ec4.mcdx.
Full audit trail: casefile.json / JOURNAL.md alongside.
"""

from pathlib import Path

from src.models.calculation import CalcSheet


def build_sheet() -> CalcSheet:
    here = Path(__file__).resolve().parent
    sheet = CalcSheet(
        title='Shear resistance of headed studs',
        description='design resistance of a 19 mm headed stud welded through the deck, governed by stud shank failure or concrete crushing, checked against the design shear per stud.',
        reference='EN 1994-1-1 6.6.3.1',
        tool_id='shear_resistance_of_headed_studs',
        revision='0.1',
        unit_aware=True,
    )
    sheet.section('Input Parameters', intro='Given quantities as defined in the source document.')
    sheet.define('d', 19.0, unit='mm', description='Stud diameter', reference='')
    sheet.define('f_u', 450.0, unit='MPa', description='Ultimate tensile strength of the stud', reference='')
    sheet.define('h_sc', 100.0, unit='mm', description='', reference='')
    sheet.define('f_ck', 30.0, unit='MPa', description='', reference='')
    sheet.define('E_cm', 33.0, unit='GPa', description='', reference='')
    sheet.define('gamma_V', 1.25, unit='', description='', reference='')
    sheet.define('P_Ed', 57.2, unit='kN', description='', reference='')
    sheet.section('Calculation', intro='Derived step by step; each step cites its clause.')
    sheet.calc('alpha', 'Piecewise((1, (((h_sc)/(d)) >= (4))), (0.2*((h_sc)/(d)+1), True))', unit='', description='Stud height factor', reference='EN 1994-1-1:2004 §6.6.3.1(1), Eqs. (6.20)-(6.21)').atom_id = 'ec4.stud.alpha'
    sheet.calc('P_Rd_1', '(0.8*f_u*pi*((d)**(2))/(4))/(gamma_V)', unit='kN', description='Design shear resistance of a headed stud — shank failure', reference='EN 1994-1-1:2004 §6.6.3.1(1), Eq. (6.18)').atom_id = 'ec4.stud.P_Rd_shank'
    sheet.calc('P_Rd_2', '(0.29*alpha*(d)**(2)*sqrt(f_ck*E_cm))/(gamma_V)', unit='kN', description='Design shear resistance of a headed stud — concrete crushing', reference='EN 1994-1-1:2004 §6.6.3.1(1), Eq. (6.19)').atom_id = 'ec4.stud.P_Rd_concrete'
    sheet.calc('P_Rd', 'min(P_Rd_1,P_Rd_2)', unit='kN', description='', reference='EN 1994-1-1 6.6.3.1')
    sheet.calc('h_eff', '((h_sc)-(0.003*u__m))', unit='mm', description='', reference='EN 1994-1-1 6.6.3.1')
    sheet.calc('UR', '(P_Ed)/(P_Rd)', unit='', description='', reference='EN 1994-1-1 6.6.3.1')
    sheet.section('Verification', intro='Acceptance criteria for the governing results.')
    sheet.check('UR <= 1', description='', reference='')
    return sheet


if __name__ == "__main__":
    from src.output_engine import render_all
    print(render_all(build_sheet(), "reports"))
