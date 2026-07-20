"""HTML renderer: CalcSheet -> print-ready, self-contained A4 report.

A structural-engineering calc report that tells a story, not just a list of
formulas:
- black page frame, company logo, project/title cartouche, repeated on
  every page (prepared / checked / approved)
- section headings with a narrative intro (what this section does)
- each step: a lead line saying what it computes, the equation, and the
  **code clause right-aligned in italic** (Mathcad-style margin reference),
  with the result in bold
- verifications as prominent, clearly-differentiated OK / NOT OK panels
- math pre-rendered to inline SVG => fully offline, no MathJax/LaTeX
- every equation ALSO carries an invisible, selectable plain-text line, and
  the whole calculation is baked in as a machine-readable layer, so the PDF
  is copyable by humans and reconstructable by AI (see reconstruct_from_pdf)

Render modes: "detailed" (three-line) and "compact" (one line per step).
"""

from __future__ import annotations

import base64
import gzip
import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.models.calculation import CalcSheet, fmt_number, unit_latex
from src.output_engine.branding import DEFAULT_BRANDING, Branding, ReportMeta

MR_BEGIN = "@@CALCSHEET/1@@"
MR_END = "@@END@@"


def _css(b: Branding) -> str:
    return f"""
:root {{
  --primary: {b.primary}; --accent: {b.accent}; --light: {b.light};
  --ok: {b.ok_color}; --not-ok: {b.not_ok_color};
  --ink: #1c2530; --muted: #6b7686; --rule: #d7dee8;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #eef1f5; }}
body {{ font-family: "Segoe UI","Helvetica Neue",Arial,sans-serif;
  color: var(--ink); font-size: 10.2pt; line-height: 1.4; }}

.sheet {{ width: 210mm; margin: 8mm auto; background: #fff;
  border-collapse: collapse; box-shadow: 0 2px 12px rgba(0,0,0,.16); }}
.sheet > thead > tr > td {{ padding: 0; border: 1.4pt solid var(--primary); }}
.sheet > tbody > tr > td {{ padding: 0;
  border: 1.4pt solid var(--primary); border-top: none; }}

/* ---- Mathcad-style title block (bounding-box grid), repeats each page ---- */
table.tblock {{ width: 100%; border-collapse: collapse; }}
table.tblock td {{ border: 0.8pt solid var(--rule); padding: 1.6mm 3mm;
  vertical-align: top; }}
.tb-logo {{ width: 42mm; text-align: center; vertical-align: middle;
  background: #fff; }}
.tb-logo svg, .tb-logo .logo-img {{ height: 10mm; width: auto; max-width: 38mm; }}
.tb-k {{ font-size: 6.8pt; text-transform: uppercase; letter-spacing: .5px;
  color: var(--muted); display: block; }}
.tb-v {{ font-size: 10pt; color: var(--primary); font-weight: 600; }}
.tb-title {{ }}
.tb-title .ttl {{ font-size: 12.5pt; font-weight: 700; color: var(--primary);
  line-height: 1.15; }}
.tb-title .ref {{ font-size: 8.4pt; color: var(--accent); margin-top: .6mm; }}
.tb-people {{ width: 40mm; }}
.tb-people .row {{ display: flex; justify-content: space-between;
  font-size: 8.6pt; padding: .3mm 0; }}
.tb-people .row b {{ color: var(--muted); font-weight: 600;
  text-transform: uppercase; font-size: 6.8pt; letter-spacing: .4px;
  align-self: center; }}
.tb-people .row span {{ color: var(--primary); font-weight: 600; }}
.tb-status {{ text-align: right; }}
.tb-status .badge {{ display: inline-block; padding: .6mm 2.4mm;
  background: var(--accent); color: #fff; border-radius: 2px; font-weight: 700;
  font-size: 7.6pt; letter-spacing: .5px; }}

.body {{ padding: 5mm 9mm 7mm; }}
h1.doctitle {{ font-size: 3px; line-height: 1; margin: 0; color: #fff;
  font-weight: normal; }}

/* ---- narrative / abstract ---- */
.abstract {{ background: var(--light); border-left: 3px solid var(--accent);
  padding: 2.6mm 3.5mm; margin: 1mm 0 3mm; font-size: 9.8pt; }}
.abstract .lbl {{ font-size: 7.6pt; text-transform: uppercase; letter-spacing: .6px;
  color: var(--primary); font-weight: 700; display: block; margin-bottom: 1mm; }}

h2.section {{ color: var(--primary); font-size: 11.6pt; margin: 6mm 0 1mm;
  padding-bottom: 1.2mm; border-bottom: 1.5px solid var(--primary);
  display: flex; align-items: baseline; gap: 2.5mm; }}
h2.section .num {{ font-size: 9.5pt; background: var(--primary); color: #fff;
  border-radius: 3px; padding: .3mm 2mm; }}
p.intro {{ color: #33404f; margin: 1.4mm 0 2.5mm; font-size: 9.7pt; }}
p.note {{ margin: 1.6mm 0; }}

/* ---- inputs ---- */
table.inputs {{ border-collapse: collapse; width: 100%; margin: 1.5mm 0 2mm;
  font-size: 9.4pt; }}
table.inputs th {{ background: var(--primary); color: #fff; text-align: left;
  padding: 1.3mm 2.4mm; font-weight: 600; }}
table.inputs td {{ padding: 1.1mm 2.4mm; border: none;
  border-bottom: 1px solid #e7ebf1; }}
table.inputs tr:nth-child(even) td {{ background: #f6f8fb; }}
table.inputs td.sym svg {{ vertical-align: middle; }}
table.inputs td.ref {{ color: var(--muted); font-style: italic; font-size: 8.4pt;
  text-align: right; white-space: nowrap; }}

/* ---- calculation steps ---- */
.step {{ break-inside: avoid; margin: 2.6mm 0; padding-left: 3mm;
  border-left: 2.5px solid var(--accent); }}
.step .lead {{ font-weight: 600; color: var(--primary); font-size: 9.7pt;
  margin-bottom: .6mm; }}
.eqrow {{ display: flex; align-items: flex-start; justify-content: space-between;
  gap: 6mm; }}
.eqrow .eq {{ flex: 1 1 auto; min-width: 0; }}
.eqrow .clause {{ flex: 0 0 auto; color: var(--muted); font-style: italic;
  font-size: 8.4pt; text-align: right; max-width: 46mm; padding-top: 1mm; }}
.mline {{ margin: .5mm 0 .5mm 6mm; overflow-x: auto; }}
.mline.first {{ margin-left: 0; }}
.result svg {{ }}
.compact {{ break-inside: avoid; margin: 1.4mm 0; padding-left: 3mm;
  border-left: 2.5px solid var(--accent); display: flex;
  justify-content: space-between; gap: 6mm; }}
.compact .clause {{ color: var(--muted); font-style: italic; font-size: 8.4pt; }}
.mfallback {{ font-family: "Consolas",monospace; font-size: 9pt; color: #445; }}

/* invisible-but-selectable plain text of each equation (copy/paste + AI).
   MUST stay in normal flow and painted (white, tiny) — off-screen/absolute
   text is clipped out of the printed PDF and would not be extractable. */
.sr {{ display: block; color: #fff; font-family: "Consolas",monospace;
  font-size: 2px; line-height: 1; margin: 0; user-select: all;
  white-space: pre-wrap; word-break: break-all; }}

/* ---- verification panels ---- */
.checks-head {{ margin-top: 2mm; }}
.check {{ break-inside: avoid; margin: 2.4mm 0; border-radius: 5px;
  border: 1px solid; display: flex; align-items: stretch; overflow: hidden; }}
.check.ok {{ border-color: var(--ok); background: #eaf6ec; }}
.check.no {{ border-color: var(--not-ok); background: #fcecec; }}
.check .verdict {{ display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 800; letter-spacing: .6px; padding: 0 4mm;
  font-size: 11pt; min-width: 22mm; }}
.check.ok .verdict {{ background: var(--ok); }}
.check.no .verdict {{ background: var(--not-ok); }}
.check .body2 {{ padding: 2mm 3.5mm; flex: 1; }}
.check .body2 .desc {{ font-weight: 600; color: var(--primary); font-size: 9.6pt;
  margin-bottom: .6mm; }}
.check .body2 .crit {{ overflow-x: auto; }}
.check .body2 .clause {{ color: var(--muted); font-style: italic; font-size: 8.2pt;
  margin-top: .8mm; }}

/* ---- figures / sketches ---- */
figure.fig {{ break-inside: avoid; margin: 3mm auto; text-align: center; }}
figure.fig img {{ max-width: 100%; border: 0.6pt solid var(--rule);
  border-radius: 3px; }}
figure.fig figcaption {{ font-size: 8.4pt; color: var(--muted);
  font-style: italic; margin-top: 1mm; }}

/* machine-readable layer: in normal flow, painted white & tiny so it is
   extractable by pdftotext (reconstruct_from_pdf) yet visually silent.
   break-inside:avoid keeps the base64 on ONE page so the repeating header
   text can't interleave into it across a page break and corrupt it. */
.mr-data {{ color: #fff; font-family: monospace; font-size: 3px;
  line-height: 1.05; word-break: break-all; white-space: pre-wrap;
  user-select: all; break-inside: avoid; page-break-inside: avoid; }}

@media print {{
  html, body {{ background: #fff; }}
  @page {{ size: A4; margin: 11mm 6mm 6mm;
    @top-right {{ content: "Page " counter(page) " of " counter(pages);
      font-family: "Segoe UI",Arial,sans-serif; font-size: 8pt;
      color: {b.primary}; }}
    @top-left {{ content: "{b.company_name}"; font-family: "Segoe UI",Arial;
      font-size: 8pt; color: #6b7686; }}
  }}
  .sheet {{ width: auto; margin: 0; box-shadow: none; }}
  .body {{ padding: 4mm 7mm; }}
}}
"""


class _SvgMath:
    """Offline TeX -> inline SVG via matplotlib mathtext (cached)."""

    def __init__(self) -> None:
        import matplotlib

        matplotlib.use("Agg")
        # Emit <text>/<tspan> (real, selectable characters) instead of glyph
        # <path> outlines, so the PRINTED equations are selectable/copyable
        # in the PDF — not just the hidden machine-readable layer.
        matplotlib.rcParams["svg.fonttype"] = "none"
        from matplotlib import mathtext
        from matplotlib.font_manager import FontProperties

        self._mathtext = mathtext
        self._FontProperties = FontProperties
        self._cache: dict[tuple[str, int], str | None] = {}

    @staticmethod
    def _sanitize(latex: str) -> str:
        latex = re.sub(r"\\le(?![a-zA-Z])", r"\\leq", latex)
        latex = re.sub(r"\\ge(?![a-zA-Z])", r"\\geq", latex)
        return latex

    def render(self, latex: str, size: int = 11) -> str | None:
        key = (latex, size)
        if key not in self._cache:
            import io

            buf = io.BytesIO()
            try:
                self._mathtext.math_to_image(
                    f"${self._sanitize(latex)}$", buf, format="svg",
                    prop=self._FontProperties(size=size),
                )
                svg = buf.getvalue().decode("utf-8")
                self._cache[key] = svg[svg.index("<svg"):]
            except Exception:
                self._cache[key] = None
        return self._cache[key]


def _make_math_backend() -> _SvgMath | None:
    try:
        return _SvgMath()
    except ImportError:
        return None


def _mr_layer(sheet: CalcSheet) -> str:
    raw = sheet.to_json(indent=0).encode("utf-8")
    b64 = base64.b64encode(gzip.compress(raw)).decode("ascii")
    return f'<div class="mr-data">{MR_BEGIN}{b64}{MR_END}</div>'


def _plain_eq(item) -> str:
    """Clean, selectable plain-text form of a calc step (copy/paste + AI)."""
    result = fmt_number(item.value) if item.value is not None else ""
    unit = f" {item.unit}" if item.unit and item.unit not in ("-",) else ""
    if item.expression:
        return f"{item.name} = {item.expression} = {result}{unit}"
    return f"{item.name} = {result}{unit}"


def render_html(
    sheet: CalcSheet,
    branding: Branding | None = None,
    meta: ReportMeta | None = None,
    mode: str = "detailed",
) -> str:
    b = branding or DEFAULT_BRANDING
    m = meta or ReportMeta.from_sheet(sheet)
    esc = html.escape
    svg_math = _make_math_backend()

    def inline(latex: str, size: int = 11) -> str:
        if svg_math is not None:
            svg = svg_math.render(latex, size)
            return svg if svg is not None else \
                f'<code class="mfallback">{esc(latex)}</code>'
        return f"\\({latex}\\)"

    def display_lines(lines: list[str]) -> str:
        out = []
        for i, line in enumerate(lines):
            first = " first" if i == 0 else ""
            out.append(f'<div class="mline{first}">{inline(line, 12)}</div>')
        return "".join(out)

    p: list[str] = ["<!DOCTYPE html>", '<html lang="en"><head>',
                    '<meta charset="utf-8">', f"<title>{esc(sheet.title)}</title>",
                    f"<style>{_css(b)}</style>", "</head><body>"]

    status = esc(m.status or "DRAFT")
    # Mathcad-style title block (bounding-box grid), repeated on every page
    # via <thead>. No footer — "nothing below but calculations".
    p.append('<table class="sheet"><thead><tr><td>')
    p.append('<table class="tblock"><tr>')
    p.append(f'<td class="tb-logo" rowspan="2">{b.logo_markup()}</td>')
    p.append('<td><span class="tb-k">Project</span>'
             f'<span class="tb-v">{esc(m.project or "—")}</span></td>')
    p.append('<td><span class="tb-k">Project No.</span>'
             f'<span class="tb-v">{esc(m.project_no or "—")}</span></td>')
    p.append('<td class="tb-people" rowspan="2">'
             f'<div class="row"><b>Prepared</b><span>{esc(m.prepared_by or "—")}</span></div>'
             f'<div class="row"><b>Checked</b><span>{esc(m.checked_by or "—")}</span></div>'
             f'<div class="row"><b>Approved</b><span>{esc(m.approved_by or "—")}</span></div>'
             '</td></tr>')
    p.append('<tr><td class="tb-title" colspan="2">'
             f'<div class="ttl">{esc(sheet.title)}</div>'
             + (f'<div class="ref">{esc(sheet.reference)}</div>' if sheet.reference else "")
             + '</td></tr>')
    p.append('<tr>'
             f'<td colspan="3"><span class="tb-k">Rev / Date</span>'
             f'<span class="tb-v">{esc(sheet.revision)} · {esc(sheet.created)}</span></td>'
             f'<td class="tb-status"><span class="badge">{status}</span></td>'
             '</tr>')
    p.append("</table></td></tr></thead>")

    p.append('<tbody><tr><td><div class="body">')
    # semantic H1 for the PDF document outline (bookmark) — visually silent
    # since the title already shows in the title block above.
    p.append(f'<h1 class="doctitle">{esc(sheet.title)}</h1>')
    if sheet.description:
        p.append('<div class="abstract"><span class="lbl">Purpose</span>'
                 f'{esc(sheet.description)}</div>')

    section_no = 0
    input_buffer: list = []

    def flush_inputs() -> None:
        if not input_buffer:
            return
        any_ref = any(it.reference for it in input_buffer)
        p.append('<table class="inputs"><thead><tr>'
                 "<th>Symbol</th><th>Value</th><th>Unit</th><th>Description</th>"
                 + ("<th>Reference</th>" if any_ref else "")
                 + "</tr></thead><tbody>")
        for it in input_buffer:
            ref = f'<td class="ref">{esc(it.reference)}</td>' if any_ref else ""
            p.append(f'<tr><td class="sym">{inline(it.latex_lhs)}</td>'
                     f"<td>{fmt_number(it.value)}</td>"
                     f"<td>{esc(it.unit)}</td>"
                     f"<td>{esc(it.description)}</td>{ref}</tr>")
        p.append("</tbody></table>")
        input_buffer.clear()

    for it in sheet.items:
        if it.kind == "section":
            flush_inputs()
            section_no += 1
            p.append(f'<h2 class="section"><span class="num">{section_no}</span>'
                     f"{esc(it.name)}</h2>")
            if it.intro:
                p.append(f'<p class="intro">{esc(it.intro)}</p>')
        elif it.kind == "text":
            flush_inputs()
            p.append(f'<p class="note">{esc(it.text)}</p>')
        elif it.kind == "image":
            flush_inputs()
            cap = f"<figcaption>{esc(it.text)}</figcaption>" if it.text else ""
            p.append(
                f'<figure class="fig">'
                f'<img style="width:{it.image_width_mm}mm" '
                f'src="data:{it.image_mime};base64,{it.image_b64}">{cap}'
                f"</figure>")
        elif it.kind == "input":
            input_buffer.append(it)
        elif it.kind == "calc":
            flush_inputs()
            result = fmt_number(it.value)
            ru = unit_latex(it.unit)
            unit = f"\\ {ru}" if ru else ""
            lead = f'<div class="lead">{esc(it.description)}</div>' \
                if it.description else ""
            clause = f'<div class="clause">{esc(it.reference)}</div>' \
                if it.reference else ""
            sr = f'<span class="sr">{esc(_plain_eq(it))}</span>'
            if mode == "compact":
                eq = inline(f"{it.latex_lhs} = \\mathbf{{{result}}}{unit}", 12)
                p.append(f'<div class="compact"><div>{lead}{eq}{sr}</div>'
                         f'{clause}</div>')
            else:
                # Unit-aware sheets (Mathcad) carry units, so a
                # substituted-numbers line can't be consistent once the
                # result is converted to its display unit — show the clean
                # two-line symbolic = result. Unit-naive sheets keep the
                # full three-line Mathcad breakdown.
                if getattr(sheet, "unit_aware", False):
                    lines = [f"{it.latex_lhs} = {it.latex_symbolic}",
                             f"= \\mathbf{{{result}}}{unit}"]
                else:
                    lines = [f"{it.latex_lhs} = {it.latex_symbolic}",
                             f"= {it.latex_substituted}",
                             f"= \\mathbf{{{result}}}{unit}"]
                p.append(
                    f'<div class="step">{lead}'
                    f'<div class="eqrow"><div class="eq">{display_lines(lines)}'
                    f'{sr}</div>{clause}</div></div>')
        elif it.kind == "check":
            flush_inputs()
            ok = it.passed
            state, label = ("ok", b.ok_label) if ok else ("no", b.not_ok_label)
            desc = f'<div class="desc">{esc(it.description)}</div>' \
                if it.description else ""
            clause = f'<div class="clause">{esc(it.reference)}</div>' \
                if it.reference else ""
            p.append(
                f'<div class="check {state}"><div class="verdict">{label}</div>'
                f'<div class="body2">{desc}'
                f'<div class="crit">{inline(it.latex_symbolic, 12)}</div>'
                f'{clause}</div></div>')
    flush_inputs()

    p.append(_mr_layer(sheet))
    p.append("</div></td></tr></tbody></table></body></html>")
    return "\n".join(p)


# ---------------------------------------------------------------------- #
# Headless-Chromium PDF (no LaTeX, no internet)
# ---------------------------------------------------------------------- #
_CHROMIUM_CANDIDATES = ("chromium", "chromium-browser", "google-chrome", "chrome")


def find_chromium() -> str | None:
    import os

    env = os.getenv("CHROME_BIN")
    if env and Path(env).exists():
        return env
    for c in _CHROMIUM_CANDIDATES:
        found = shutil.which(c)
        if found:
            return found
    pw = Path("/opt/pw-browsers/chromium")
    return str(pw) if pw.exists() else None


def render_pdf_browser(
    sheet: CalcSheet,
    out_path: str | Path,
    branding: Branding | None = None,
    meta: ReportMeta | None = None,
    mode: str = "detailed",
) -> Path:
    """Print the HTML report to an A4 PDF with headless Chromium.

    Carries a document outline (bookmarks) and — baked into the page
    content, not an attachment — the self-contained machine-readable layer.
    """
    chromium = find_chromium()
    if chromium is None:
        raise RuntimeError(
            "No Chromium/Chrome found (set CHROME_BIN). Alternatively open "
            "the .html report in any browser and print to PDF manually."
        )
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        html_file = Path(tmp) / "report.html"
        html_file.write_text(
            render_html(sheet, branding, meta, mode), encoding="utf-8")
        subprocess.run(
            [chromium, "--headless", "--disable-gpu", "--no-sandbox",
             "--virtual-time-budget=10000", "--no-pdf-header-footer",
             "--generate-pdf-document-outline",
             f"--print-to-pdf={out_path}", html_file.as_uri()],
            check=True, capture_output=True)
    try:
        from src.output_engine.pdf_stamp import stamp_pdf

        stamp_pdf(out_path, sheet)
    except ImportError:
        pass
    return out_path
