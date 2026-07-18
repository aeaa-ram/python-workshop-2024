"""HTML renderer: CalcSheet -> print-ready, self-contained A4 report.

Design goals (structural-engineering calc sheet, Mathcad-like):
- black page border, company logo top-left, project/title cartouche
- header + footer repeated on every page (prepared / checked / approved)
- OK / NOT OK verdicts in green / red
- math pre-rendered to inline SVG => fully offline, no MathJax/LaTeX
- a self-contained machine-readable layer baked INTO the page content
  (not an attachment): invisible sentinel-wrapped base64(gzip(json)) that
  survives plain text extraction, so the PDF alone reconstructs the data.

Render modes:
- "detailed": Mathcad three-line steps (symbolic, substituted, result)
- "compact":  one line per step (symbol = result unit)
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
from src.output_engine.branding import (
    DEFAULT_BRANDING,
    Branding,
    ReportMeta,
)

# Sentinels for the embedded machine-readable payload (see pdf_stamp.py).
MR_BEGIN = "@@CALCSHEET/1@@"
MR_END = "@@END@@"


def _css(b: Branding) -> str:
    return f"""
:root {{
  --primary: {b.primary};
  --accent: {b.accent};
  --light: {b.light};
  --ok: {b.ok_color};
  --not-ok: {b.not_ok_color};
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #f4f5f7; }}
body {{ font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
       color: #1a202c; font-size: 10.5pt; }}

/* Page = a table so the header (thead) and footer (tfoot) repeat on
   every printed page and never overlap the flowing body (tbody). This
   is the most reliable running-header technique in headless Chromium.
   The black Mathcad-style frame is the border on the body cell. */
.sheet {{ width: 210mm; margin: 8mm auto; background: #fff;
         border-collapse: collapse; box-shadow: 0 2px 10px rgba(0,0,0,.18); }}
.sheet > thead, .sheet > tfoot {{ display: table-header-group; }}
.sheet > tfoot {{ display: table-footer-group; }}
.sheet td {{ padding: 0; border: 1.4pt solid #111; }}
.cartouche {{ border-bottom: 2.5px solid var(--primary); }}
.cart-row {{ display: flex; align-items: stretch; }}
.cart-logo {{ padding: 4mm 5mm; display: flex; align-items: center;
             border-right: 1px solid #d3d9e3; }}
.cart-logo svg, .logo-img {{ height: 9mm; width: auto; }}
.cart-title {{ flex: 1; padding: 3mm 5mm; }}
.cart-title .proj {{ font-size: 8.5pt; color: #5a6472; text-transform: uppercase;
                    letter-spacing: .5px; }}
.cart-title h1 {{ font-size: 14pt; color: var(--primary); margin: 1mm 0 0 0; }}
.cart-status {{ padding: 3mm 5mm; text-align: right; border-left: 1px solid #d3d9e3;
               min-width: 34mm; font-size: 8.5pt; color: #5a6472; }}
.cart-status .badge {{ display: inline-block; margin-top: 1mm; padding: .8mm 2.4mm;
                      background: var(--accent); color: #fff; border-radius: 2px;
                      font-weight: 700; letter-spacing: .5px; }}

/* Footer cartouche */
.foot {{ border-top: 1.5px solid var(--primary); display: flex;
        font-size: 8pt; color: #47505e; }}
.foot .cell {{ padding: 2mm 4mm; border-right: 1px solid #d3d9e3; }}
.foot .cell:last-child {{ border-right: none; margin-left: auto; text-align: right; }}
.foot b {{ color: var(--primary); }}

.body {{ padding: 5mm 8mm 6mm 8mm; }}
h2.section {{ color: var(--primary); font-size: 12pt; margin: 5mm 0 2mm 0;
             padding-bottom: 1mm; border-bottom: 1px solid var(--light); }}
p.note {{ margin: 2mm 0; }}

table.inputs {{ border-collapse: collapse; width: 100%; margin: 2mm 0;
               font-size: 9.5pt; }}
table.inputs th {{ background: var(--primary); color: #fff; text-align: left;
                  padding: 1.4mm 2.4mm; font-weight: 600; }}
table.inputs td {{ padding: 1.2mm 2.4mm; border-bottom: 1px solid #e6eaf0; }}
table.inputs tr:nth-child(even) td {{ background: var(--light); }}
table.inputs td svg {{ vertical-align: middle; }}

.step {{ break-inside: avoid; margin: 2.5mm 0; padding-left: 3mm;
        border-left: 2.5px solid var(--accent); }}
.step .desc {{ font-weight: 600; color: var(--primary); margin-bottom: 1mm;
             font-size: 9.5pt; }}
.step .clause {{ font-weight: 400; color: #7a828e; font-size: 8.5pt; }}
.mline {{ margin: .6mm 0 .6mm 6mm; overflow-x: auto; }}
.mline.first {{ margin-left: 0; }}
.compact {{ break-inside: avoid; margin: 1.4mm 0; padding-left: 3mm;
           border-left: 2.5px solid var(--accent); }}
.mfallback {{ font-family: "Consolas", monospace; font-size: 9pt; color: #445; }}

.check {{ break-inside: avoid; display: flex; align-items: center; gap: 3mm;
         margin: 2.5mm 0; padding: 2mm 3mm; border-radius: 3px; }}
.check.ok {{ background: #E9F6EC; border-left: 4px solid var(--ok); }}
.check.no {{ background: #FCEBEB; border-left: 4px solid var(--not-ok); }}
.verdict {{ font-weight: 800; color: #fff; padding: .8mm 3mm; border-radius: 3px;
           letter-spacing: .5px; font-size: 9pt; white-space: nowrap; }}
.check.ok .verdict {{ background: var(--ok); }}
.check.no .verdict {{ background: var(--not-ok); }}

/* Machine-readable layer: present in page content, visually silent. */
.mr-data {{ color: #ffffff; font-family: monospace; font-size: 3px;
           line-height: 1.05; word-break: break-all; white-space: pre-wrap;
           user-select: all; }}

@media print {{
  html, body {{ background: #fff; }}
  @page {{ size: A4; margin: 7mm 6mm; }}
  .sheet {{ width: auto; margin: 0; box-shadow: none; }}
  .body {{ padding: 3mm 5mm; }}
}}
"""


class _SvgMath:
    """Offline TeX -> inline SVG via matplotlib mathtext (cached)."""

    def __init__(self) -> None:
        import matplotlib

        matplotlib.use("Agg")
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
    """Invisible, self-contained machine-readable payload for the page."""
    raw = sheet.to_json(indent=0).encode("utf-8")
    b64 = base64.b64encode(gzip.compress(raw)).decode("ascii")
    return f'<div class="mr-data">{MR_BEGIN}{b64}{MR_END}</div>'


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
    # Page as a table: thead=cartouche, tfoot=footer (both repeat every
    # printed page), tbody=flowing body. Border on the cells = the frame.
    status = esc(m.status or "DRAFT")
    p.append('<table class="sheet"><thead><tr><td>')
    p.append('<div class="cartouche"><div class="cart-row">')
    p.append(f'<div class="cart-logo">{b.logo_markup()}</div>')
    p.append('<div class="cart-title">')
    p.append(f'<div class="proj">{esc(m.project or b.company_name)}'
             f'{" · " + esc(m.project_no) if m.project_no else ""}</div>')
    p.append(f"<h1>{esc(sheet.title)}</h1>")
    if sheet.reference:
        p.append(f'<div class="proj">{esc(sheet.reference)}</div>')
    p.append("</div>")
    p.append(f'<div class="cart-status">Rev {esc(sheet.revision)}<br>'
             f'{esc(sheet.created)}<br><span class="badge">{status}</span></div>')
    p.append("</div></div></td></tr></thead>")

    p.append('<tfoot><tr><td><div class="foot">')
    p.append(f'<div class="cell"><b>Prepared</b> {esc(m.prepared_by or "—")}</div>')
    p.append(f'<div class="cell"><b>Checked</b> {esc(m.checked_by or "—")}</div>')
    p.append(f'<div class="cell"><b>Approved</b> {esc(m.approved_by or "—")}</div>')
    p.append(f'<div class="cell">{esc(b.company_name)}</div>')
    p.append("</div></td></tr></tfoot>")

    p.append('<tbody><tr><td><div class="body">')
    if sheet.description:
        p.append(f'<p class="note">{esc(sheet.description)}</p>')

    section_no = 0
    input_buffer: list = []

    def flush_inputs() -> None:
        if not input_buffer:
            return
        p.append('<table class="inputs"><thead><tr>'
                 "<th>Symbol</th><th>Value</th><th>Unit</th>"
                 "<th>Description</th></tr></thead><tbody>")
        for it in input_buffer:
            p.append(f"<tr><td>{inline(it.latex_lhs)}</td>"
                     f"<td>{fmt_number(it.value)}</td>"
                     f"<td>{esc(it.unit)}</td>"
                     f"<td>{esc(it.description)}</td></tr>")
        p.append("</tbody></table>")
        input_buffer.clear()

    for it in sheet.items:
        if it.kind == "section":
            flush_inputs()
            section_no += 1
            p.append(f'<h2 class="section">{section_no}. {esc(it.name)}</h2>')
        elif it.kind == "text":
            flush_inputs()
            p.append(f'<p class="note">{esc(it.text)}</p>')
        elif it.kind == "input":
            input_buffer.append(it)
        elif it.kind == "calc":
            flush_inputs()
            result = fmt_number(it.value)
            ru = unit_latex(it.unit)
            unit = f"\\ {ru}" if ru else ""
            desc = _step_desc(esc, it)
            if mode == "compact":
                p.append(f'<div class="compact">{desc}'
                         f'{inline(f"{it.latex_lhs} = {result}{unit}", 12)}</div>')
            else:
                lines = [f"{it.latex_lhs} = {it.latex_symbolic}",
                         f"= {it.latex_substituted}",
                         f"= \\mathbf{{{result}}}{unit}"]
                p.append(f'<div class="step">{desc}{display_lines(lines)}</div>')
        elif it.kind == "check":
            flush_inputs()
            ok = it.passed
            state, label = ("ok", b.ok_label) if ok else ("no", b.not_ok_label)
            d = f" — {esc(it.description)}" if it.description else ""
            p.append(f'<div class="check {state}"><span class="verdict">{label}'
                     f'</span><span>{inline(it.latex_symbolic, 12)}{d}</span></div>')
    flush_inputs()

    p.append(_mr_layer(sheet))
    p.append("</div></td></tr></tbody></table></body></html>")
    return "\n".join(p)


def _step_desc(esc, item) -> str:
    if not item.description:
        return ""
    text = item.description
    clause = ""
    m = re.search(r"\[(.*?)\]\s*$", text)
    if m:
        clause = f' <span class="clause">[{esc(m.group(1))}]</span>'
        text = text[: m.start()].strip()
    return f'<div class="desc">{esc(text)}{clause}</div>'


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

    The PDF carries a document outline (bookmarks) and — baked into the
    page content, not as an attachment — the self-contained
    machine-readable calculation layer.
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
            render_html(sheet, branding, meta, mode), encoding="utf-8"
        )
        subprocess.run(
            [chromium, "--headless", "--disable-gpu", "--no-sandbox",
             "--virtual-time-budget=10000", "--no-pdf-header-footer",
             "--generate-pdf-document-outline",
             f"--print-to-pdf={out_path}", html_file.as_uri()],
            check=True, capture_output=True,
        )
    # Also attach the JSON (belt & braces) + metadata; the in-page layer
    # is the primary, attachment-free path.
    try:
        from src.output_engine.pdf_stamp import stamp_pdf

        stamp_pdf(out_path, sheet)
    except ImportError:
        pass
    return out_path
