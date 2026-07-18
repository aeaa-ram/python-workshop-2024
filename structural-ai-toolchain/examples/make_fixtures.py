"""Generate dummy legacy files for trials and tests.

- ``crack_width_ec2.xlsx``  — EN 1992-1-1 §7.3.4 crack width check, built
  with *real Excel formulas* so the Grinder's formula translation is
  exercised for real.
- ``beam_bending_check.ipynb`` — simple notebook following the line
  conventions (``name = expr  # unit | description``).

Run directly (``python examples/make_fixtures.py``) or via
``python main.py demo``.
"""

from __future__ import annotations

from pathlib import Path


def make_crack_width_xlsx(out_dir: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Crack Width"
    ws["A1"] = "Crack Width Verification - RC Slab (EN 1992-1-1 7.3.4)"
    ws["A2"] = (
        "Characteristic crack width for a reinforced concrete slab under "
        "quasi-permanent loading."
    )

    ws["A4"] = "INPUTS"
    ws.append([])  # keep row math simple: write cells explicitly below
    headers = ["Name", "Value", "Unit", "Description"]
    for col, header in enumerate(headers, start=1):
        ws.cell(row=5, column=col, value=header)
    inputs = [
        # (name, value, unit, description) — rows 6..21
        ("b", 1000, "mm", "Section width (per metre strip)"),
        ("h", 300, "mm", "Section depth"),
        ("d", 260, "mm", "Effective depth"),
        ("c_nom", 30, "mm", "Nominal concrete cover"),
        ("phi", 16, "mm", "Bar diameter"),
        ("A_s", 1005, "mm^2", "Tension reinforcement area (5 H16)"),
        ("M_qp", 45, "kNm", "Quasi-permanent bending moment"),
        ("E_s", 200000, "MPa", "Steel modulus of elasticity"),
        ("E_cm", 33000, "MPa", "Concrete secant modulus"),
        ("f_ct_eff", 2.9, "MPa", "Effective concrete tensile strength"),
        ("k_t", 0.4, "-", "Load duration factor (long term)"),
        ("k_1", 0.8, "-", "Bond factor (high-bond bars)"),
        ("k_2", 0.5, "-", "Strain distribution factor (bending)"),
        ("k_3", 3.4, "-", "Code coefficient"),
        ("k_4", 0.425, "-", "Code coefficient"),
        ("w_max", 0.3, "mm", "Allowable crack width (XC exposure)"),
    ]
    for offset, (name, value, unit, desc) in enumerate(inputs):
        row = 6 + offset
        ws.cell(row=row, column=1, value=name)
        ws.cell(row=row, column=2, value=value)
        ws.cell(row=row, column=3, value=unit)
        ws.cell(row=row, column=4, value=desc)

    ws.cell(row=23, column=1, value="CALCULATIONS")
    for col, header in enumerate(headers, start=1):
        ws.cell(row=24, column=col, value=header)
    # Input value cells: b=B6 h=B7 d=B8 c_nom=B9 phi=B10 A_s=B11 M_qp=B12
    # E_s=B13 E_cm=B14 f_ct_eff=B15 k_t=B16 k_1=B17 k_2=B18 k_3=B19
    # k_4=B20 w_max=B21. Calc cells start at B25.
    calcs = [
        ("alpha_e", "=B13/B14", "-", "Modular ratio E_s/E_cm"),
        (
            "x",
            "=(B25*B11/B6)*(SQRT(1+2*B6*B8/(B25*B11))-1)",
            "mm",
            "Neutral axis depth (cracked section)",
        ),
        ("z", "=B8-B26/3", "mm", "Internal lever arm"),
        (
            "sigma_s",
            "=B12*1000000/(B27*B11)",
            "MPa",
            "Steel stress under quasi-permanent loads",
        ),
        (
            "h_c_eff",
            "=MIN(2.5*(B7-B8),(B7-B26)/3,B7/2)",
            "mm",
            "Effective tension zone height",
        ),
        ("rho_p_eff", "=B11/(B6*B29)", "-", "Effective reinforcement ratio"),
        (
            "s_r_max",
            "=B19*B9+B17*B18*B20*B10/B30",
            "mm",
            "Maximum crack spacing",
        ),
        (
            "eps_diff",
            "=MAX((B28-B16*B15/B30*(1+B25*B30))/B13,0.6*B28/B13)",
            "-",
            "Mean strain difference (eps_sm - eps_cm)",
        ),
        ("w_k", "=B31*B32", "mm", "Characteristic crack width"),
    ]
    for offset, (name, formula, unit, desc) in enumerate(calcs):
        row = 25 + offset
        ws.cell(row=row, column=1, value=name)
        ws.cell(row=row, column=2, value=formula)
        ws.cell(row=row, column=3, value=unit)
        ws.cell(row=row, column=4, value=desc)

    ws.cell(row=35, column=1, value="CHECKS")
    ws.cell(row=36, column=1, value="Expression")
    ws.cell(row=36, column=2, value="Description")
    ws.cell(row=37, column=1, value="w_k <= w_max")
    ws.cell(row=37, column=2, value="Crack width within allowable limit")

    out_path = out_dir / "crack_width_ec2.xlsx"
    wb.save(out_path)
    return out_path


def make_beam_notebook(out_dir: Path) -> Path:
    import nbformat

    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell(
            "# Rectangular Beam Bending Check\n"
            "Elastic bending stress verification for a simply supported "
            "rectangular timber beam under uniform load."
        ),
        nbformat.v4.new_code_cell(
            "b = 200  # mm | Section width\n"
            "h = 400  # mm | Section depth\n"
            "L = 5000  # mm | Span\n"
            "q = 4.5  # kN/m | Distributed load (design)\n"
            "f_m = 24  # MPa | Design bending strength"
        ),
        nbformat.v4.new_code_cell(
            "M_max = q*(L/1000)**2/8  # kNm | Maximum bending moment\n"
            "W = b*h**2/6  # mm^3 | Elastic section modulus\n"
            "sigma_m = M_max*1000000/W  # MPa | Maximum bending stress"
        ),
        nbformat.v4.new_code_cell(
            "# CHECKS\n"
            "sigma_m <= f_m"
        ),
    ]
    out_path = out_dir / "beam_bending_check.ipynb"
    nbformat.write(nb, str(out_path))
    return out_path


def make_all(out_dir: str | Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        make_crack_width_xlsx(out_dir),
        make_beam_notebook(out_dir),
    ]


if __name__ == "__main__":
    for path in make_all(Path(__file__).parent):
        print(path)
