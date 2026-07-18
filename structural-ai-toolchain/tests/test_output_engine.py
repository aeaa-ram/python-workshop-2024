"""Output engine: the rendered report must show live, correct values."""

import pytest

from src.models.calculation import CalcSheet, CalcSheetError, fmt_number
from src.output_engine import render_html, render_latex, render_markdown


@pytest.fixture
def sheet() -> CalcSheet:
    s = CalcSheet(
        title="Demo Section Check",
        reference="EN 1990",
        project="Unit Tests",
    )
    s.section("Inputs")
    s.define("b", 300, unit="mm", description="Width")
    s.define("h", 500, unit="mm", description="Depth")
    s.define("sigma_lim", 12, unit="MPa", description="Stress limit")
    s.section("Calculation")
    s.calc("A", "b*h", unit="mm^2", description="Cross-section area")
    s.calc("W", "b*h**2/6", unit="mm^3", description="Section modulus")
    s.calc("sigma", "45*10**6/W", unit="MPa", description="Bending stress")
    s.check("sigma <= sigma_lim", "Stress within limit")
    return s


def test_values_are_computed(sheet):
    results = sheet.results()
    assert results["A"] == 150000.0
    assert results["W"] == pytest.approx(12.5e6)
    assert results["sigma"] == pytest.approx(3.6)
    assert sheet.all_passed()


def test_markdown_contains_three_line_math(sheet):
    md = render_markdown(sheet)
    # symbolic form, substituted form and result all present
    assert "b \\cdot h" in md
    assert "300 \\cdot 500" in md
    assert "\\mathbf{150000}" in md
    assert "OK" in md


def test_check_failure_is_visible():
    s = CalcSheet(title="Failing")
    s.define("a", 10)
    s.define("limit", 5)
    s.check("a <= limit")
    assert not s.all_passed()
    assert "NOT OK" in render_markdown(s)
    assert "calccheckfail" in render_latex(s)
    assert 'check no' in render_html(s)


def test_html_and_latex_render(sheet):
    html = render_html(sheet)
    assert "@page" in html and "A4" in html  # print stylesheet present
    # math is pre-rendered to inline SVG -> report works offline
    assert "<svg" in html
    tex = render_latex(sheet)
    assert tex.startswith("\\documentclass")
    assert "\\end{document}" in tex
    assert "align*" in tex


def test_undefined_variable_rejected():
    s = CalcSheet(title="Bad")
    s.define("a", 1)
    with pytest.raises(CalcSheetError):
        s.calc("x", "a + missing_var")


def test_min_max_sqrt():
    s = CalcSheet(title="Fns")
    s.define("a", 9)
    s.define("b", 4)
    assert s.calc("r", "sqrt(a)").value == 3
    assert s.calc("m", "min(a, b, 100)").value == 4
    assert s.calc("M", "max(a, b)").value == 9


def test_fmt_number():
    assert fmt_number(150000.0) == "150000"
    assert fmt_number(0.000552) == "0.000552"
    assert fmt_number(3.14159) == "3.142"
    assert fmt_number(0) == "0"
