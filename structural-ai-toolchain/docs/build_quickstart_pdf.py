"""Build docs/QUICKSTART.pdf — the 1-page starter for non-coders.

    python docs/build_quickstart_pdf.py

Keep the cards in step with docs/QUICKSTART.md.
"""

from __future__ import annotations

import html
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CARDS = [
    ("Put a sheet IN → get a tool OUT",
     ["python main.py ingest sheet.mcdx", "python main.py gui",
      "python main.py grind sheet.xlsx"],
     "<b>ingest</b> is the thorough way: it breaks the file into pieces, "
     "looks up the code clauses, <b>asks you</b> what to keep, which case "
     "governs and what the final UR is — then rebuilds and loops until it "
     "converges. .mcdx .xlsx .xlsm .csv .ipynb .py."),
    ("Already exists? → the knowledge base asks",
     ["revise <tool> · new tool · abort"],
     "Before anything is written the central library is checked for "
     "duplicates and for formulas it already holds (those keep their "
     "clause and are reused, not re-typed)."),
    ("Double-check → the master reviewer",
     ["python main.py review <tool>", "python main.py review <tool> --fix"],
     "Units, dimensions, power-of-ten slips, values vs the original "
     "(<code>--original print.pdf</code>). It <b>fixes</b> what it can "
     "prove; corrected steps get a yellow note."),
    ("If it asks questions → answer",
     ["repository/<tool>/CLARIFICATIONS.md"],
     "e.g. “Cell H1 = 1.0 has no label — what is it?”. It never "
     "silently guesses; open points also sit in <code>JOURNAL.md</code>."),
    ("See the result → the report",
     ["python main.py render <tool> --pdf",
      "python main.py render <tool> --pdf --mode compact"],
     "A4, logo, title block, every formula written out with numbers and "
     "units, clause in the margin, OK / NOT OK."),
    ("Print / share → normal PDF",
     ["reconstruct_from_pdf(\"file.pdf\")"],
     "Ctrl+P as usual. The whole calculation also hides <i>inside</i> the "
     "page, so the PDF alone can rebuild it later."),
    ("Change inputs → edit 1 file",
     ["repository/<tool>/<tool>.py"],
     "Edit the numbers in <code>build_sheet()</code>, render again. Every "
     "value recomputes — never hand-typed."),
    ("Build a NEW tool from scratch",
     ["python main.py new \"Punching Shear (EC2 6.4)\"",
      "python main.py register <slug>"],
     "Starter file → edit → register. Reuse library formulas with "
     "<code>sheet.apply()</code>."),
    ("Find a formula to reuse",
     ["python main.py atoms --search \"crack width\"",
      "python main.py atoms --tree"],
     "Drill down country → code → chapter → clause, or call it: "
     "<code>custom.E_cm(f_cm=38)</code>."),
    ("See EVERYTHING (non-coders)",
     ["python main.py dashboard", "python main.py doctor"],
     "What's hosted, reused, reviewed and who edited it. <b>doctor</b> "
     "shows whether the AI and the PDF printer are set up."),
]


def build_html() -> str:
    from src.output_engine.branding import DEFAULT_BRANDING as B

    esc = html.escape
    cards = []
    for i, (title, cmds, text) in enumerate(CARDS, 1):
        code = "".join(f"<div>{esc(c)}</div>" for c in cmds)
        cards.append(
            f'<div class="card"><h3><span class="n">{i}</span>{esc(title)}'
            f'</h3><div class="code">{code}</div><p>{text}</p></div>')
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Structural AI Toolchain — quickstart</title><style>
@page {{ size: A4; margin: 10mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Segoe UI", Helvetica, Arial, sans-serif; margin: 0;
  color: #1a202c; font-size: 8.6pt; }}
.top {{ background: {B.primary}; color: #fff; border-radius: 6px;
  padding: 3.5mm 5mm; display: flex; align-items: center; gap: 6mm; }}
.top .logo {{ background: #fff; border-radius: 4px; padding: 1.5mm 2.5mm;
  height: 11mm; display: flex; align-items: center; }}
.top .logo svg, .top .logo img {{ height: 8mm; width: auto; }}
.top h1 {{ margin: 0; font-size: 15pt; }}
.top .sub {{ font-size: 8.4pt; opacity: .9; }}
.top .inst {{ margin-left: auto; font-size: 8pt; text-align: right; }}
.top code {{ color: #fff; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2.6mm;
  margin-top: 3mm; }}
.card {{ border: 1px solid #dfe5ee; border-left: 3px solid {B.accent};
  border-radius: 5px; padding: 2.4mm 3mm; break-inside: avoid; }}
.card h3 {{ margin: 0 0 1.4mm; font-size: 9.6pt; color: {B.primary}; }}
.n {{ display: inline-block; background: {B.primary}; color: #fff;
  border-radius: 50%; width: 4.6mm; height: 4.6mm; text-align: center;
  line-height: 4.6mm; font-size: 7.6pt; margin-right: 1.6mm; }}
.code {{ background: #f1f4f8; border-radius: 3px; padding: 1.2mm 2mm;
  font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 7.6pt; }}
.card p {{ margin: 1.4mm 0 0; line-height: 1.32; }}
code {{ font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 7.6pt; }}
.foot {{ margin-top: 3mm; background: #eef2f8; border-radius: 5px;
  padding: 2.4mm 3.5mm; font-size: 8pt; }}
.foot b {{ color: {B.primary}; }}
</style></head><body>
<div class="top"><div class="logo">{B.logo_markup()}</div>
<div><h1>Structural AI Toolchain</h1>
<div class="sub">1-page starter — everything runs locally from
<code>structural-ai-toolchain/</code>. AI optional: set
<code>ANTHROPIC_API_KEY</code>.</div></div>
<div class="inst">install once:<br><code>pip install -r requirements.txt</code></div>
</div>
<div class="grid">{''.join(cards)}</div>
<div class="foot"><b>Where things live:</b> <code>repository/</code> = your
tools + reports (the source of truth) · <code>src/library/</code> = shared
formulas · <code>docs/</code> = deeper guides & PITFALLS.
<b>Full run once:</b> <code>python main.py demo</code>.
<b>Does it exist already?</b> <code>python main.py ask "what you want"</code>.
</div></body></html>"""


def main() -> Path:
    from src.output_engine import find_chromium

    out = ROOT / "docs" / "QUICKSTART.pdf"
    chromium = find_chromium()
    if chromium is None:
        raise SystemExit("No Chromium found (set CHROME_BIN).")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "quickstart.html"
        page.write_text(build_html(), encoding="utf-8")
        subprocess.run([chromium, "--headless", "--disable-gpu", "--no-sandbox",
                        "--no-pdf-header-footer", f"--print-to-pdf={out}",
                        page.as_uri()], check=True, capture_output=True)
    return out


if __name__ == "__main__":
    print(main())
