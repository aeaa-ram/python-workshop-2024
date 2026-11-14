"""Fixtures: small invented calculations in every supported file type.

None of the numbers come from a project.  The Excel fixture reproduces the
three sheet layouts met in practice (label column with case columns, label /
symbol / value triples, a value one row below its label) and two habits that
matter for consolidation: working per metre width, and leaving out the lower
bound of the shear resistance.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def make_excel(path: Path) -> Path:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Slab shear"
    ws["D3"] = "Shear capacity check (EN 1992-1-1 6.2.2 (1))"
    ws["E5"], ws["F5"] = "Section A", "Section B"
    rows = [
        ("tslab (mm)", 300, 250),
        ("γc", "=1.5", "=1.5"),
        ("CRd.c", "=0.18/{c}7", "=0.18/{c}7"),
        ("d (mm)", "={c}6-40-16/2", "={c}6-40-12/2"),
        ("σcp (Mpa)", 0, 0.5),
        ("k1", 0.15, 0.15),
        ("ν", "=0.6*(1-{c}17/250)", "=0.6*(1-{c}17/250)"),
        ("k", "=MIN(1+(200/{c}9)^0.5,2)", "=MIN(1+(200/{c}9)^0.5,2)"),
    ]
    r = 6
    for label, a, b in rows:
        ws[f"D{r}"] = label
        ws[f"E{r}"] = a.format(c="E") if isinstance(a, str) else a
        ws[f"F{r}"] = b.format(c="F") if isinstance(b, str) else b
        r += 1
    ws["D14"], ws["E14"], ws["F14"] = "As (mm2/m)", "B16/150", "B10/200"     # the value is one row below
    ws["E15"], ws["F15"] = 1340, 393
    tail = [
        ("ρ", "=MIN({c}15/(1000*{c}9),0.02)"),
        ("fck (MPa)", 30),
        ("νmin", "=0.035*{c}13^1.5*{c}17^0.5"),
        ("VRd.c.min (kN/m)", "={c}18*1000*{c}9/1000"),
        ("VRd.c (kN/m)", "=({c}8*{c}13*(100*{c}16*{c}17)^(1/3)+{c}11*{c}10)*1000*{c}9/1000"),
        ("VEd (kN/m)", 120),
        ("Utilization", "={c}21/{c}20"),
        ("Verified?", '=IF({c}22>1,"NO","YES")'),
    ]
    r = 16
    for label, f in tail:
        ws[f"D{r}"] = label
        for c in "EF":
            ws[f"{c}{r}"] = f.format(c=c) if isinstance(f, str) else f
        r += 1

    t = wb.create_sheet("Template")
    t["B2"] = "Cl. 6.2.2"
    triples = [
        ("Eff. depth", "d", 342.5), ("Width", "bw", 1000), ("Asl(tensile)", "Asl", 2454),
        ("Ned/(bwD)", "σcp", -0.4), ("fck", "fck", 40), ("γc", None, 1.5), ("k1", None, 0.15),
        ("CRd,c", None, "=0.18/D8"), ("k", None, "=MIN((1+SQRT(200/D3)),2)"),
        ("vmin", None, "=0.035*D11^1.5*D7^0.5"), ("Asl/(bwd)", "ρ1", "=+MIN(D5/D3/D4,0.02)"),
        ("VRd.c min (KN)", None, "=+(D12+D9*D6)*D3*D4/1000"),
        ("VRd.c (KN)", None, "=+(D10*D11*(100*D13*D7)^(1/3)+D9*D6)*D4*D3/1000"),
        ("lever arm", "z", "=0.9*D3"),
    ]
    for i, (label, sym, val) in enumerate(triples, 3):
        t[f"B{i}"] = label
        if sym:
            t[f"C{i}"] = sym
        t[f"D{i}"] = val
    wb.save(path)
    return path


PINT_SCRIPT = '''"""Beam check written with units."""
import math
from pint import UnitRegistry

ureg = UnitRegistry()

# === Material and geometry ===
gamma_c = 1.5
f_ck = 30 * ureg.MPa
b_w = 300 * ureg.mm
d = 450 * ureg.mm
A_sl = 942 * ureg.mm**2

# === Shear resistance (EN 1992-1-1 cl. 6.2.2) ===
# Size factor, cl. 6.2.2(1)
k = min(1 + (200 * ureg.mm / d) ** 0.5, 2)
rho_l = min(A_sl / (b_w * d), 0.02)
C_Rd_c = 0.18 / gamma_c
v_min = 0.035 * k ** 1.5 * (f_ck / ureg.MPa) ** 0.5 * ureg.MPa
V_Rd_c_min = v_min * b_w * d
# Design shear resistance, eq. (6.2.a)
V_Rd_c = max(C_Rd_c * k * (100 * rho_l * f_ck / ureg.MPa) ** (1 / 3) * ureg.MPa * b_w * d, V_Rd_c_min)
# lever arm from the stress block
lam = 0.8
x = 95 * ureg.mm
z = d - lam * x / 2
'''

PLAIN_SCRIPT = '''
import math
# --- Shear without links ---
gamma_c = 1.5
f_ck = 30      # MPa, concrete strength
b_w = 300      # [mm] web width
d = 450        # mm
A_sl = 942     # mm2


def k_factor(d):
    """size factor, cl. 6.2.2(1)"""
    return min(1 + math.sqrt(200 / d), 2.0)


k = k_factor(d)
rho_l = min(A_sl / (b_w * d), 0.02)
C_Rdc = 0.18 / gamma_c
v_min = 0.035 * k ** 1.5 * f_ck ** 0.5
# design shear resistance, EN 1992-1-1 cl. 6.2.2(1)
V_Rdc = max(C_Rdc * k * (100 * rho_l * f_ck) ** (1 / 3), v_min) * b_w * d / 1000   # kN
'''


def make_notebook(path: Path) -> Path:
    cells = [
        {"cell_type": "markdown", "metadata": {}, "source": ["# Crack width\n", "Quasi-permanent combination"]},
        {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
         "source": ["%matplotlib inline\n", "s_r_max = 310   # mm\n", "eps_sm_cm = 0.0006\n"]},
        {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
         "source": ["# crack width, EN 1992-1-1 eq. (7.8)\n", "w_k = s_r_max * eps_sm_cm   # mm\n"]},
    ]
    path.write_text(json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
    return path


def make_docx(path: Path) -> Path:
    import docx
    doc = docx.Document()
    doc.add_heading("Shear resistance", level=1)
    doc.add_paragraph("According to EN 1992-1-1 cl. 6.2.2(1) the size factor is k = 1.67.")
    doc.add_paragraph("d = 450 mm; bw = 300 mm")
    doc.add_paragraph("vmin = 0.412 MPa")
    doc.add_paragraph("VRd,c,min = vmin * bw * d = 55.6 kN")
    table = doc.add_table(rows=2, cols=3)
    for j, text in enumerate(("fck", "30", "MPa")):
        table.rows[0].cells[j].text = text
    for j, text in enumerate(("VRd,c", "74.4", "kN")):
        table.rows[1].cells[j].text = text
    doc.save(str(path))
    return path


def make_pdf(path: Path) -> Path | None:
    """A text PDF printed by a browser; None when no browser is installed."""
    from ckb.use.report import find_browser
    browser = find_browser()
    if not browser:
        return None
    html = path.with_suffix(".html")
    html.write_text("<html><body style='font:14px Arial'><h2>Shear</h2><p>EN 1992-1-1 cl. 6.2.2(1)</p>"
                    "<p>d = 450 mm</p><p>k = 1.67</p><p>VRd,c = 74.4 kN</p></body></html>", encoding="utf-8")
    subprocess.run([browser, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={path}", html.as_uri()], capture_output=True, timeout=120, check=False)
    return path if path.exists() else None


def recalculated(path: Path) -> Path | None:
    """The workbook after LibreOffice calculated it (so it holds cached values)."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    out = Path(tempfile.mkdtemp(prefix="ckb_test_"))
    subprocess.run([soffice, "--headless", f"-env:UserInstallation=file://{out}/profile", "--convert-to",
                    "xlsx:Calc MS Excel 2007 XML", "--outdir", str(out), str(path)],
                   capture_output=True, timeout=180, check=False)
    result = out / path.name
    return result if result.exists() else None


@pytest.fixture(scope="session")
def inbox(tmp_path_factory) -> Path:
    box = tmp_path_factory.mktemp("inbox")
    make_excel(box / "slab_shear.xlsx")
    (box / "beam_check.py").write_text(PINT_SCRIPT, encoding="utf-8")
    shutil.copy(box / "beam_check.py", box / "beam_check_copy.py")       # an exact duplicate
    (box / "notes.txt").write_text("not a calculation", encoding="utf-8")
    return box


@pytest.fixture(scope="session")
def built(inbox, tmp_path_factory):
    """The whole pipeline run once on the synthetic inbox."""
    from ckb.pipeline import build
    root = tmp_path_factory.mktemp("run")
    out = build(inbox, root / "workspace", root / "knowledge_base", log=lambda *_: None)
    out.root = root
    return out


@pytest.fixture(scope="session")
def kb(built):
    from ckb.kb.objects import KnowledgeBase
    return KnowledgeBase.load(built.root / "knowledge_base")
