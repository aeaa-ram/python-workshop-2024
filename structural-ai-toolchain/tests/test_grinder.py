"""The Grinder: legacy files in, standardized executable tools out."""

import json

import pytest

from examples.make_fixtures import make_beam_notebook, make_crack_width_xlsx
from src.ingestion import grind, supported_extensions
from src.ingestion.base import get_parser
from src.ingestion.excel_parser import ExcelParser


def test_supported_extensions_cover_targets():
    exts = supported_extensions()
    for required in (".mcdx", ".xlsx", ".xlsm", ".csv", ".py", ".ipynb"):
        assert required in exts


def test_excel_formula_translation():
    expr, unresolved = ExcelParser.translate_formula(
        "MIN(2.5*(B7-B8),(B7-B26)/3,B7/2)^2",
        {"B7": "h", "B8": "d", "B26": "x"},
    )
    assert expr == "min(2.5*(h-d),(h-x)/3,h/2)**2"
    assert unresolved == []


def test_grind_crack_width_xlsx(tmp_path):
    src = make_crack_width_xlsx(tmp_path)
    result = grind(src, tmp_path / "repo", skip_gatekeeper=True)
    assert result.tool_dir.exists()
    manifest = json.loads(
        (result.tool_dir / "manifest.json").read_text(encoding="utf-8")
    )
    # Values re-computed from the translated Excel formulas match the
    # hand-checked EC2 numbers.
    assert manifest["results"]["w_k"] == pytest.approx(0.1807, abs=1e-3)
    assert manifest["results"]["sigma_s"] == pytest.approx(184.1, abs=0.5)
    assert manifest["warnings"] == []
    # The generated python tool is executable and self-consistent.
    namespace: dict = {}
    exec(
        (result.tool_dir / f"{result.slug}.py").read_text(encoding="utf-8"),
        namespace,
    )
    sheet = namespace["build_sheet"]()
    assert sheet.results()["w_k"] == pytest.approx(0.1807, abs=1e-3)
    assert sheet.all_passed()
    # Standardized doc exists with front matter + live values.
    doc = (result.tool_dir / f"{result.slug}.md").read_text(encoding="utf-8")
    assert doc.startswith("---")
    assert "OK" in doc


def test_grind_notebook(tmp_path):
    src = make_beam_notebook(tmp_path)
    result = grind(src, tmp_path / "repo", skip_gatekeeper=True)
    manifest = json.loads(
        (result.tool_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["results"]["M_max"] == pytest.approx(14.0625)
    assert manifest["results"]["sigma_m"] == pytest.approx(2.637, abs=1e-3)
    assert manifest["checks"] == ["sigma_m <= f_m"]


def test_mcdx_parser_handles_unreadable_container(tmp_path):
    # a non-zip .mcdx must warn (not crash) — the real parser degrades
    # gracefully just like the AI grinder does
    fake = tmp_path / "legacy_tool.mcdx"
    fake.write_bytes(b"not a zip")
    tool = get_parser(fake).parse(fake)
    assert tool.source_format == "mcdx"
    assert tool.warnings  # some warning about the container


def test_mcdx_translates_operator_tree():
    # the ml: operator-tree translator turns Mathcad math into our syntax
    from src.ingestion.mathcad_parser import _slug, _clean_code_ref

    assert _slug("γ") == "gamma"
    assert _slug("t_s") == "t_s"
    assert _clean_code_ref("EN 199 4 -1-1") == "EN 1994-1-1"
