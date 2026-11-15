"""The report as a Word document, from the same template and the same formula trees.

Equations are native Word equations (Office Math, printed by ``expr.to_omml``), so
they can be edited in Word like any other.  Headings use Word's heading styles: the
navigation pane shows them, and *Save as PDF* with "create bookmarks using headings"
turns them into PDF bookmarks.  The document is a record of one run: to change the
calculation, change the template or the cases and generate it again.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from .. import expr as X
from ..kb.objects import KnowledgeBase
from . import report as R
from .calc import Result, lookup

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
GREY = (0x5B, 0x69, 0x66)
OK, BAD = (0x0A, 0x7A, 0x2F), (0xB3, 0x26, 0x1E)


def _math(par, xml: str, bold: bool = False) -> None:
    from docx.oxml import parse_xml
    if bold:
        xml = re.sub(r"(<m:r>(?:<m:rPr>.*?</m:rPr>)?)", r'\1<w:rPr><w:b/></w:rPr>', xml)
    par._p.append(parse_xml(f'<m:oMath xmlns:m="{M_NS}" xmlns:w="{W_NS}">{xml}</m:oMath>'))


def _num(style, v) -> str:
    s = style.fmt(v) if not isinstance(v, str) else v
    neg = s.startswith("-")
    run = f'<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t xml:space="preserve">{"−" if neg else ""}{s.lstrip("-")}</m:t></m:r>'
    return run


def _unit(u: str) -> str:
    return "" if u in ("-", "") else \
        f'<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t xml:space="preserve"> {u}</m:t></m:r>'


_EQ = '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t xml:space="preserve"> = </m:t></m:r>'


def _run(par, text: str, *, bold=False, italic=False, size=None, color=None):
    from docx.shared import Pt, RGBColor
    r = par.add_run(text)
    r.bold, r.italic = bold, italic
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = RGBColor(*color)
    return r


def _right_tab(par, doc):
    from docx.enum.text import WD_TAB_ALIGNMENT
    sec = doc.sections[0]
    width = sec.page_width - sec.left_margin - sec.right_margin
    par.paragraph_format.tab_stops.add_tab_stop(width, WD_TAB_ALIGNMENT.RIGHT)


def _shade(cell, hex_fill: str):
    from docx.oxml import parse_xml
    cell._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd xmlns:w="{W_NS}" w:val="clear" w:color="auto" w:fill="{hex_fill}"/>'))


def _calc(doc, kb: KnowledgeBase, res: Result, opts: dict, label: str):
    from docx.shared import Mm, Pt
    style, obj = res.style, kb.objects[res.target]
    show = set(opts.get("show") or R.SHOW_ALL)
    remarks = {lookup(kb, k) or k: v for k, v in (opts.get("remarks") or {}).items()}
    if label:
        _run(doc.add_paragraph(), label, size=9, color=GREY)
    if opts.get("title", True):
        doc.add_heading(f"{obj.text} – {obj.name}", level=3)
        _run(doc.add_paragraph(), obj.reference_text, size=9, color=GREY)
    if opts.get("inputs", True):
        _run(doc.add_paragraph(), "INPUT", size=8, color=GREY, bold=True)
        t = doc.add_table(rows=0, cols=3)
        for ln in res.inputs:
            cells = t.add_row().cells
            _run(cells[0].paragraphs[0], ln.name, size=9)
            _math(cells[1].paragraphs[0], kb.omml(ln.id) + _EQ + _num(style, ln.shown) + _unit(ln.unit))
            note = {"fixed": f"fixed by {obj.code}", "recommended": "recommended value",
                    "given": "entered directly"}.get(ln.source, "")
            ref = " · ".join(x for x in (ln.reference, note) if x)
            _run(cells[2].paragraphs[0], ref, size=8, color=GREY)
            if remarks.get(ln.id):
                _run(cells[2].add_paragraph(), remarks[ln.id], size=8, italic=True, color=GREY)
        for row in t.rows:
            row.cells[0].width, row.cells[1].width, row.cells[2].width = Mm(70), Mm(55), Mm(55)
    _run(doc.add_paragraph(), "CALCULATION", size=8, color=GREY, bold=True)
    steps_opt = opts.get("steps", "all")
    if steps_opt == "result":
        lines = [ln for ln in res.steps if ln.id == res.target]
    elif isinstance(steps_opt, list):
        want = {lookup(kb, s) or s for s in steps_opt} | {res.target}
        lines = [ln for ln in res.steps if ln.id in want]
    else:
        lines = res.steps
    for ln in lines:
        o = kb.objects[ln.id]
        p = doc.add_paragraph()
        _right_tab(p, doc)
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.keep_with_next = True
        _run(p, o.name, size=10)
        ref = o.reference_text.replace(o.code + " ", "") if o.code == obj.code else o.reference_text
        _run(p, "\t" + ref, size=8, color=GREY)
        eqs = []
        if "equation" in show:
            eqs.append((kb.omml(ln.id) + _EQ + X.to_omml(o.tree, kb.omml), False))
        if "substituted" in show and X.symbols(o.tree):
            eqs.append((_EQ + X.to_omml(o.tree, kb.omml, values=ln.env, fmt=style.fmt_short), False))
        if "result" in show or not eqs:
            eqs.append((_EQ + _num(style, ln.shown) + _unit(ln.unit), True))
        for i, (xml, bold) in enumerate(eqs):
            q = doc.add_paragraph()
            q.paragraph_format.left_indent = Mm(8)
            q.paragraph_format.space_after = Pt(1)
            q.paragraph_format.keep_with_next = i < len(eqs) - 1
            if i == 0 and xml.startswith(_EQ):          # no equation line: the first line names the step
                xml = kb.omml(ln.id) + xml
            _math(q, xml, bold)
        if remarks.get(ln.id):
            _run(doc.add_paragraph(), remarks[ln.id], size=8, italic=True, color=GREY)
    # verdict
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    _math(p, obj.omml + _EQ + _num(style, res.shown) + _unit(res.unit), bold=True)
    if res.check:
        c = res.check
        _run(p, "     ")
        _math(p, kb.omml(c["against"]) + _EQ + _num(style, c["shown"]) + _unit(c["unit"]))
        _run(p, f"     η = {c['utilisation']:.2f} {'≤' if c['ok'] else '>'} 1.00   ", bold=True)
        _run(p, "OK" if c["ok"] else "NOT OK", bold=True, color=OK if c["ok"] else BAD)
    if opts.get("checks", True):
        for chk in res.checks:
            mark = {"ok": "met", "violated": "NOT MET", "not checked": "to be checked"}[chk["status"]]
            q = doc.add_paragraph(style="List Bullet")
            _run(q, f"{chk['text']} ({chk['clause']}): {mark}", size=9,
                 color=BAD if chk["status"] == "violated" else None)
    if opts.get("limitations", False):
        for t_ in dict.fromkeys(res.limitations):
            _run(doc.add_paragraph(style="List Bullet"), t_, size=9)


def _table(doc, kb: KnowledgeBase, it: dict, style):
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    target, cases, opts, gov = it["target"], it["cases"], it["opts"], it["gov"]
    obj = kb.objects[target]
    cols = opts.get("columns") or (["case", target] + (["check", "utilisation", "verdict"] if obj.check else []))
    rows = [c for c in cases if c.result is not None]
    if opts.get("sort"):
        key, _, order = str(opts["sort"]).partition(" ")
        rows.sort(key=lambda c: R._cell_value(kb, c, key) if isinstance(R._cell_value(kb, c, key), (int, float)) else 0,
                  reverse=order.strip().lower() == "desc")
    if opts.get("title"):
        doc.add_heading(str(opts["title"]), level=3)
    t = doc.add_table(rows=1, cols=len(cols))
    t.style = "Light List"
    for i, col in enumerate(cols):
        cell = t.rows[0].cells[i]
        if col in ("case", "utilisation", "verdict"):
            _run(cell.paragraphs[0], {"case": "Case", "utilisation": "Utilisation", "verdict": "Verdict"}[col], bold=True, size=9)
        else:
            sid = obj.check if col == "check" else (lookup(kb, col) or col)
            _math(cell.paragraphs[0], kb.omml(sid))
            u = style.unit(kb, sid)
            if u != "-":
                _run(cell.add_paragraph(), u, size=8, color=GREY)
    for c in rows:
        cells = t.add_row().cells
        for i, col in enumerate(cols):
            v = R._cell_value(kb, c, col)
            sid = obj.check if col == "check" else (lookup(kb, col) or col)
            text = c.name if col == "case" else ("" if v is None else (f"{v:.2f}" if col == "utilisation" else
                                                                      v if col == "verdict" else style.fmt(style.show(kb, sid, v))))
            par = cells[i].paragraphs[0]
            if col != "case":
                par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            color = (OK if v == "OK" else BAD) if col == "verdict" else None
            _run(par, str(text), size=9, bold=c is gov and len(rows) > 1, color=color)
            if c is gov and len(rows) > 1:
                _shade(cells[i], "E8F1F4")
    if gov is not None and len(rows) > 1:
        _run(doc.add_paragraph(), "The governing case is highlighted.", size=8, color=GREY)
    for p in t.rows[0].cells:
        p.paragraphs[0].paragraph_format.space_after = Pt(0)


def _chart_png(data: dict) -> bytes | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    colors = ["#2a78d6", "#eb6834"]
    fig, ax = plt.subplots(figsize=(6.3, 2.7), dpi=200)
    for k, (name, ys) in enumerate(data["series"]):
        ax.plot(data["xs"], [y if y is not None else float("nan") for y in ys], color=colors[k], lw=1.6, label=name)
    if data.get("ref"):
        ax.axhline(data["ref"][1], color="#16211f", lw=0.8, ls="--")
        ax.text(data["xs"][-1], data["ref"][1], f"{data['ref'][0]} = {data['ref'][1]:.4g} ", ha="right", va="bottom",
                fontsize=7, color="#16211f")
    if data.get("marker") and isinstance(data["marker"][1], (int, float)):
        ax.plot([data["marker"][0]], [data["marker"][1]], "o", ms=5, color=colors[0], mec="white", mew=1.5)
    ax.set_xlabel(data["x_label"], fontsize=8)
    ax.set_ylabel(data["y_label"], fontsize=8)
    ax.tick_params(labelsize=7, length=0)
    ax.grid(axis="y", color="#e3e8e6", lw=0.7)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.set_ylim(bottom=min(0, ax.get_ylim()[0]))
    if len(data["series"]) > 1:
        ax.legend(fontsize=7, frameon=False, loc="upper left")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _footer(doc, left: str):
    from docx.oxml import parse_xml
    footer = doc.sections[0].footer
    p = footer.paragraphs[0]
    _run(p, left, size=7, color=GREY)
    r = footer.add_paragraph()
    _run(r, "Page ", size=7, color=GREY)
    for instr in ("PAGE", None, "NUMPAGES"):
        if instr is None:
            _run(r, " of ", size=7, color=GREY)
            continue
        r._p.append(parse_xml(f'<w:fldSimple xmlns:w="{W_NS}" w:instr="{instr}"><w:r><w:t>1</w:t></w:r></w:fldSimple>'))


def render_docx(kb: KnowledgeBase, template: dict, path: Path, base: Path | None = None) -> Path:
    from docx import Document
    from docx.shared import Mm, Pt
    items, used, style = R.layout(kb, template, base)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin = sec.right_margin = sec.top_margin = Mm(15)
    sec.bottom_margin = Mm(17)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Arial", Pt(10)
    doc.core_properties.title = template.get("title") or "Calculation"
    doc.core_properties.subject = ", ".join(sorted({kb.objects[o].code for o in used}))
    if template.get("title_block", True):
        t = doc.add_table(rows=2, cols=3)
        t.style = "Table Grid"
        for r, row in enumerate(R.title_block(template)):
            for c, (k, v) in enumerate(row):
                cell = t.rows[r].cells[c]
                _run(cell.paragraphs[0], k.upper(), size=7, color=GREY)
                _run(cell.add_paragraph(), v or " ", size=9)
        doc.add_paragraph()
    if template.get("title"):
        doc.add_heading(template["title"], level=1)
    for it in items:
        t = it["type"]
        if t == "heading":
            doc.add_heading(it["text"], level=2)
        elif t == "text":
            doc.add_paragraph(it["text"])
        elif t == "pagebreak":
            doc.add_page_break()
        elif t == "error":
            _run(doc.add_paragraph(), it["text"], color=BAD)
        elif t == "calc":
            _calc(doc, kb, it["result"], it["opts"], it["label"])
        elif t == "table":
            _table(doc, kb, it, style)
        elif t == "chart":
            png = _chart_png(it["data"])
            if png:
                doc.add_picture(io.BytesIO(png), width=Mm(170))
                _run(doc.add_paragraph(), it["data"]["caption"], size=8, color=GREY)
    left, versions = R.footer_text(kb, used)
    _footer(doc, left)
    doc.core_properties.keywords = versions          # out of sight, for `ckb verify`
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path
