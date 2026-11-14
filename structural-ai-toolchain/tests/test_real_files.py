"""Checks on real project files, when they are present.

Project files are never committed.  Put them in ``inbox/`` (ignored by git)
or point ``CKB_REAL_INBOX`` at a folder; without them these tests are skipped.
They expect at least one Mathcad worksheet and one Excel workbook that both
calculate the shear resistance V_Rd,c to EN 1992-1-1.
"""
import os
from pathlib import Path

import pytest

from ckb import expr as X

BOX = Path(os.getenv("CKB_REAL_INBOX") or Path(__file__).resolve().parent.parent / "inbox")
FILES = [p for p in BOX.glob("*") if p.suffix.lower() in (".mcdx", ".xlsx", ".pdf")] if BOX.exists() else []
pytestmark = pytest.mark.skipif(
    not (any(p.suffix == ".mcdx" for p in FILES) and any(p.suffix == ".xlsx" for p in FILES)),
    reason="no real project files in the inbox")


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    from ckb.pipeline import build
    root = tmp_path_factory.mktemp("real")
    out = build(BOX, root / "workspace", root / "knowledge_base", anonymous=True, log=lambda *_: None)
    out.root = root
    return out


def test_every_formula_reproduces_its_source(real):
    for doc in real.docs:
        s = doc.summary()
        assert s["formulas_mismatch"] == 0 and s["formulas_failed"] == 0, doc.label
        if doc.kind == "mathcad":
            r = doc.meta["stored_results"]
            assert r["compared"] > 20 and r["agree"] == r["compared"]


def test_shear_resistance_is_distilled_and_confirmed(real):
    o = real.kb.objects["V_Rd_c"]
    assert X.same(o.tree, X.parse(
        "max((C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + k_1 * sigma_cp) * b_w * d, V_Rd_c_min)"))
    assert o.status == "unified" and o.support["sources"] >= 2
    assert o.reference.get("status") == "agrees"
    assert any(e["matches_source"] for e in o.examples)


def test_a_pdf_of_a_worksheet_is_a_benchmark_not_a_second_source(real):
    prints = [d for d in real.docs if d.meta.get("print_of")]
    if not prints:
        pytest.skip("no PDF print of another source in the inbox")
    printed = [b for rows in real.benchmarks.values() for b in rows if b.kind == "printed" and b.concept == "V_Rd_c"]
    assert printed and all(b.status == "agree" for b in printed)


def test_no_file_or_sheet_names_in_the_anonymous_knowledge_base(real):
    text = "".join(p.read_text(encoding="utf-8") for p in (real.root / "knowledge_base").rglob("*") if p.is_file())
    for doc in real.docs:
        assert Path(doc.name).stem not in text
        for sheet in doc.meta.get("sheets", []):
            if len(sheet["title"].strip()) > 6:
                assert sheet["title"].strip() not in text
