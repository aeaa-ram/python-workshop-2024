"""The agentic ingestion workflow: atomise → research → clarify inline →
reconstruct → verify → reflect, looping to convergence."""

import pytest

from examples.make_fixtures import make_crack_width_xlsx, make_messy_beam_xlsx
from src.ingestion.agent import ScriptedInteraction, ingest
from src.ingestion.agent.casefile import CaseFile, Fragment


# ---------------------------------------------------------------- casefile
def test_fragment_dependencies_and_casefile():
    case = CaseFile(source_path="x.xlsx", source_format="xlsx")
    case.add(Fragment(fid="F01", kind="input", name="b", value=100))
    case.add(Fragment(fid="F02", kind="input", name="h", value=200))
    case.add(Fragment(fid="F03", kind="derived", name="A", expression="b*h"))
    case.add(Fragment(fid="F04", kind="derived", name="W",
                      expression="A*h/6"))
    assert case.frag("A").depends_on() == {"b", "h"}
    assert case.dependency_errors() == []
    case.frag("b").status = "discarded"
    assert case.dependency_errors()  # A now misses b


# ------------------------------------------------------- end-to-end (tidy)
def test_agentic_ingest_tidy_sheet_converges(tmp_path):
    xlsx = make_crack_width_xlsx(tmp_path)
    res = ingest(xlsx, tmp_path / "repo",
                 answers={"final-result": "w_k"}, render_pdf=False)
    assert res.converged
    assert res.case.final_result == "w_k"
    # replicates the hand-checked EC2 numbers exactly
    import json

    data = json.loads(open(res.paths["json"]).read())
    assert data["results"]["w_k"] == pytest.approx(0.1807, abs=1e-3)
    # audit trail written
    assert (res.case.iterations >= 1)
    assert "journal" in res.paths and "manifest" in res.paths


# ------------------------------------------------- end-to-end (messy sheet)
def test_agentic_ingest_messy_sheet_asks_and_applies(tmp_path):
    xlsx = make_messy_beam_xlsx(tmp_path)
    channel_answers = {
        # magic numbers were surfaced by the parser; presentation Qs:
        "final-result": "Bending_stress_sigma",
        "acceptance-check": "yes",
        "layout": "compact",
    }
    res = ingest(xlsx, tmp_path / "repo", answers=channel_answers,
                 render_pdf=False)
    # decisions recorded in the case file (audit trail)
    qids = {d.qid for d in res.case.decisions}
    assert "final-result" in qids and "layout" in qids
    assert res.case.layout == "compact"
    # sigma is already governed by the sheet's own check (sigma <= fy),
    # so the agent must NOT bolt on a duplicate '<= 1.0' criterion
    checks = [f.expression for f in res.case.kept("check")]
    assert any("Bending_stress_sigma" in c for c in checks)
    assert not any("<= 1.0" in c for c in checks)


# ---------------------------------------------------- defer mode is honest
def test_defer_mode_never_fabricates(tmp_path):
    xlsx = make_messy_beam_xlsx(tmp_path)
    res = ingest(xlsx, tmp_path / "repo", interactive=False,
                 render_pdf=False)
    # deferred questions are surfaced, not silently answered
    assert isinstance(res.deferred, list)
    for d in res.case.decisions:
        assert d.answered_by in ("deferred", "default", "script", "user")


# ------------------------------------------------------- scripted channel
def test_scripted_interaction_matching():
    from src.ingestion.agent.interaction import Question

    chan = ScriptedInteraction({"q1": "42", "layout": "compact"})
    a1, by1 = chan.ask(Question(qid="q1", stage="s", prompt="value?"))
    assert (a1, by1) == ("42", "script")
    a2, by2 = chan.ask(Question(qid="zz", stage="s",
                                prompt="Report layout choice",
                                default="detailed"))
    assert a2 == "compact"      # matched by prompt substring
    a3, by3 = chan.ask(Question(qid="unknown", stage="s", prompt="??",
                                default="d"))
    assert (a3, by3) == ("d", "default")


# ------------------------------------------------------------- resolution
def test_resolution_answers():
    from src.ingestion.agent.stages import _apply_resolution

    case = CaseFile(source_path="x", source_format="x")
    f = case.add(Fragment(fid="U1", kind="derived", name="P_Rd_2",
                          status="unresolved"))
    _apply_resolution(case, f, "91.4 kN")
    assert f.kind == "input" and f.value == 91.4 and f.unit == "kN"
    assert f.status == "kept"

    g = case.add(Fragment(fid="U2", kind="derived", name="x",
                          status="unresolved"))
    _apply_resolution(case, g, "defer")
    assert g.status == "deferred"

    h = case.add(Fragment(fid="U3", kind="derived", name="junk",
                          status="unresolved"))
    _apply_resolution(case, h, "discard")
    assert h.status == "discarded"


# ---------------------------------------------------------- BMP conversion
def test_bmp_to_png_conversion():
    import struct

    from src.ingestion.agent.stages import _bmp_to_png

    # tiny 2x2 24-bit BMP (red, green / blue, white), rows padded to 4B
    width, height = 2, 2
    row = width * 3
    pad = (4 - row % 4) % 4
    pixels = (bytes([0, 0, 255]) + bytes([0, 255, 0]) + b"\x00" * pad +
              bytes([255, 0, 0]) + bytes([255, 255, 255]) + b"\x00" * pad)
    header = (b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54) +
              struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0,
                          len(pixels), 2835, 2835, 0, 0))
    png = _bmp_to_png(header + pixels)
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"
