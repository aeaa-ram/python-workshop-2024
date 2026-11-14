"""Self-documenting calculations.

A calculation run is printed the way a checked hand calculation reads: for
every step the description, the equation with the code's symbols, the same
equation with the numbers substituted, the result with its unit, and the
clause it comes from.  Notes, limitations and the evidence behind each object
are part of the sheet, so the reader can judge the result without opening
the code.

The equations are MathML printed from the same formula trees the code blocks
are generated from.
"""
from __future__ import annotations

import datetime as _dt
import html
import os
import shutil
import subprocess
from pathlib import Path

from .. import expr as X
from .. import units as U
from ..kb.objects import KnowledgeBase
from .calc import Result

SHEET_CSS = """
:root{--paper:#fff;--ink:#16211f;--muted:#5d6b68;--rule:#c9d2cf;--soft:#eef2f0;--accent:#0b5d73;
--ok:#1f7a4d;--warn:#a86400;--bad:#b3261e;--okbg:#e3f3ea;--warnbg:#fbefd9;--badbg:#fbe6e4}
*{box-sizing:border-box}
body{margin:0;background:#e9edeb;color:var(--ink);font:14px/1.5 "IBM Plex Sans","Segoe UI",Arial,sans-serif}
.sheet{background:var(--paper);max-width:210mm;margin:16px auto;padding:14mm 16mm 16mm;box-shadow:0 1px 4px rgba(0,0,0,.18)}
math{font-family:"Cambria Math","STIX Two Math","Latin Modern Math","Noto Sans Math",math;font-size:1.08em}
table.tb{width:100%;border-collapse:collapse;margin-bottom:8mm;font-size:12px}
table.tb td{border:1px solid var(--ink);padding:3px 6px;vertical-align:top}
table.tb small{display:block;color:var(--muted);font-size:9.5px;letter-spacing:.04em;text-transform:uppercase}
h1{font-size:19px;margin:0 0 2px;line-height:1.25}
h2{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--ink);
padding-bottom:3px;margin:9mm 0 3mm}
.ref{color:var(--muted);margin:0 0 2mm}
.row{display:grid;grid-template-columns:34% 1fr 24%;gap:0 10px;padding:6px 0;border-bottom:1px solid var(--soft);break-inside:avoid}
.row .d{color:var(--ink)} .row .d small{display:block;color:var(--muted);font-size:11.5px}
.row .c{color:var(--muted);font-size:11.5px;text-align:right}
.row .e{min-width:0;overflow-x:auto;overflow-y:hidden}
.eq{display:flex;gap:6px;align-items:baseline;margin:2px 0}
.eq .lhs{min-width:4.6em;text-align:right;white-space:nowrap}
.eq.res{font-weight:600}
.in{display:grid;grid-template-columns:34% 1fr 24%;gap:0 10px;padding:3px 0;border-bottom:1px solid var(--soft)}
.in .c{color:var(--muted);font-size:11.5px;text-align:right}
.result{margin:6mm 0 0;padding:10px 14px;border:1.5px solid var(--ink);display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.result .big{font-size:18px;font-weight:600}
.util{flex:1;min-width:180px}
.bar{height:10px;background:var(--soft);border:1px solid var(--rule);position:relative}
.bar i{position:absolute;inset:0 auto 0 0;display:block}
.ok .bar i{background:var(--ok)} .warn .bar i{background:var(--warn)} .bad .bar i{background:var(--bad)}
.pill{display:inline-block;padding:1px 8px;border-radius:9px;font-size:11.5px;font-weight:600}
.ok .pill,.pill.ok{background:var(--okbg);color:var(--ok)} .warn .pill,.pill.warn{background:var(--warnbg);color:var(--warn)}
.bad .pill,.pill.bad{background:var(--badbg);color:var(--bad)}
ul.notes{margin:0;padding-left:18px} ul.notes li{margin:2px 0}
ul.notes li.w{color:var(--warn)}
table.basis{width:100%;border-collapse:collapse;font-size:11.5px}
table.basis th,table.basis td{border-bottom:1px solid var(--rule);padding:3px 6px;text-align:left;vertical-align:top}
table.basis th{color:var(--muted);font-weight:500}
.foot{margin-top:8mm;color:var(--muted);font-size:10.5px}
@media print{.row .e{overflow:visible}body{background:#fff}.sheet{box-shadow:none;margin:0;max-width:none;padding:0}@page{size:A4;margin:16mm 16mm 18mm}}
"""


def _e(s) -> str:
    return html.escape(str(s))


def _num(v, sig: int = 5) -> str:
    return U.fmt(v, sig) if not isinstance(v, str) else v


def _unit(u: str) -> str:
    return "" if u in ("-", "") else u


def _status_class(status: str) -> str:
    return {"consensus": "ok", "unified": "ok", "single source": "warn", "disagreement": "bad"}.get(status, "warn")


def equation_lines(kb: KnowledgeBase, line) -> list[str]:
    """MathML for the three lines of a step: symbols, numbers, result."""
    sym = f"<math>{kb.ml(line.id)}</math>"
    out = [f'<div class="eq"><span class="lhs">{sym}</span><math displaystyle="true"><mo>=</mo>'
           f'{X.to_mathml(line.formula, kb.ml)}</math></div>']
    if X.symbols(line.formula):
        out.append('<div class="eq"><span class="lhs"></span><math displaystyle="true"><mo>=</mo>'
                   f'{X.to_mathml(line.formula, kb.ml, values=line.env, fmt=lambda v: U.fmt(v, 5))}</math></div>')
    unit = _unit(line.unit)
    canon = ""
    if isinstance(line.value, (int, float)) and isinstance(line.shown, (int, float)) \
            and abs(line.value - line.shown) > 1e-12 * max(1.0, abs(line.value)):
        canon = f'<mn>{_e(_num(line.value, 6))}</mn><mo>=</mo>'      # N, mm before the display unit
    shown = f"<mtext>{_e(line.shown)}</mtext>" if isinstance(line.shown, str) else f"<mn>{_e(_num(line.shown))}</mn>"
    out.append(f'<div class="eq res"><span class="lhs"></span><math><mo>=</mo>{canon}{shown}'
               + (f"<mtext>&#x2009;{_e(unit)}</mtext>" if unit else "") + "</math></div>")
    return out


def render_html(kb: KnowledgeBase, res: Result, meta: dict | None = None, standalone: bool = True) -> str:
    meta = meta or {}
    obj = kb.objects[res.target]
    today = meta.get("date") or _dt.date.today().isoformat()
    P = []
    P.append('<table class="tb"><tr>'
             f'<td style="width:38%"><small>Project</small>{_e(meta.get("project", ""))}&nbsp;</td>'
             f'<td style="width:38%"><small>Subject</small>{_e(meta.get("subject", obj.name))}</td>'
             f'<td><small>Calc. no.</small>{_e(meta.get("number", ""))}&nbsp;</td></tr><tr>'
             f'<td><small>Made by / date</small>{_e(meta.get("made_by", ""))} &nbsp; {_e(today)}</td>'
             f'<td><small>Checked by / date</small>{_e(meta.get("checked_by", ""))}&nbsp;</td>'
             f'<td><small>Approved by / date</small>{_e(meta.get("approved_by", ""))}&nbsp;</td></tr></table>')
    P.append(f"<h1><math>{obj.ml}</math> &nbsp;{_e(obj.name)}</h1>")
    P.append(f'<p class="ref">{_e(obj.reference_text)} &nbsp;·&nbsp; {_e(" › ".join(obj.topic_path))}</p>')

    P.append("<h2>Input</h2>")
    origin = {"example": "from a source case", "typical": "typical value", "given": "entered directly",
              "entered": ""}
    for ln in res.inputs:
        val = _e(ln.shown) if isinstance(ln.shown, str) else _e(_num(ln.shown, 7))
        unit = _unit(ln.unit)
        P.append(f'<div class="in"><div>{_e(ln.name)}</div>'
                 f'<div><math>{kb.ml(ln.id)}<mo>=</mo><mn>{val}</mn>'
                 + (f"<mtext>&#x2009;{_e(unit)}</mtext>" if unit else "") + "</math></div>"
                 f'<div class="c">{_e(ln.reference)}{" · " if ln.reference and origin.get(ln.source) else ""}'
                 f'{_e(origin.get(ln.source, ""))}</div></div>')

    P.append("<h2>Calculation</h2>")
    for ln in res.steps:
        cls = _status_class(ln.status)
        P.append(f'<div class="row"><div class="d">{_e(ln.name)}'
                 f'<small><span class="pill {cls}">{_e(ln.status)}</span></small></div>'
                 f'<div class="e">{"".join(equation_lines(kb, ln))}</div>'
                 f'<div class="c">{_e(ln.reference)}</div></div>')

    unit = _unit(res.unit)
    shown = _e(res.shown) if isinstance(res.shown, str) else _e(_num(res.shown))
    box = [f'<div class="big"><math>{obj.ml}<mo>=</mo><mn>{shown}</mn>'
           + (f"<mtext>&#x2009;{_e(unit)}</mtext>" if unit else "") + "</math></div>"]
    cls = ""
    if res.check:
        u = res.check["utilisation"]
        cls = "ok" if u <= 0.9 else ("warn" if u <= 1.0 else "bad")
        verdict = "OK" if res.check["ok"] else "NOT OK"
        box.append(f'<div class="util"><div><math>{kb.ml(res.check["against"])}<mo>=</mo>'
                   f'<mn>{_e(_num(res.check["shown"]))}</mn><mtext>&#x2009;{_e(_unit(res.check["unit"]))}</mtext></math>'
                   f' &nbsp; utilisation {_e(res.check["expression"])} = <b>{u:.2f}</b> '
                   f'<span class="pill">{verdict}</span></div>'
                   f'<div class="bar"><i style="width:{min(u, 1.0) * 100:.1f}%"></i></div></div>')
    P.append(f'<div class="result {cls}">{"".join(box)}</div>')

    if res.warnings or res.notes:
        P.append("<h2>Notes and limitations</h2><ul class=\"notes\">")
        for w in dict.fromkeys(res.warnings):
            P.append(f'<li class="w">{_e(w)}</li>')
        for n in dict.fromkeys(res.notes):
            P.append(f"<li>{_e(n)}</li>")
        P.append("</ul>")

    P.append("<h2>Basis of this calculation</h2>")
    P.append('<table class="basis"><tr><th>Object</th><th>Status</th><th>Sources</th><th>Benchmarks</th>'
             "<th>Independent reference</th><th>Version</th></tr>")
    for ln in res.steps:
        o = kb.objects[ln.id]
        b, r, s = o.benchmarks, o.reference, o.support
        ref = f"{r['status']} with {r['library']} ({r['samples']} samples)" if r else "none available"
        P.append(f'<tr><td><math>{o.ml}</math></td><td><span class="pill {_status_class(o.status)}">{_e(o.status)}</span></td>'
                 f"<td>{s.get('formula_instances', 0)} formulas in {s.get('sources', 0)} source(s), "
                 f"{s.get('variants_merged', 0)} variant(s)</td>"
                 f"<td>{b.get('agree', 0)} of {b.get('total', 0)} reproduced</td><td>{_e(ref)}</td>"
                 f"<td>{_e(o.version)}</td></tr>")
    P.append("</table>")
    P.append(f'<p class="foot">Numbers are substituted in N, mm and MPa. Logic distilled from source calculations; '
             f'{_e(kb.meta.get("code", ""))}, {_e(kb.meta.get("branch", ""))}. Generated {_e(today)}.</p>')
    body = f'<div class="sheet">{"".join(P)}</div>'
    if not standalone:
        return body
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{_e(obj.text)} calculation</title><style>{SHEET_CSS}</style></head><body>{body}</body></html>")


def render_text(kb: KnowledgeBase, res: Result) -> str:
    """The same calculation for a terminal."""
    obj = kb.objects[res.target]
    name = kb.name
    L = [f"{obj.text} - {obj.name}", obj.reference_text, ""]
    width = max([len(l.text) for l in res.inputs + res.steps] + [4])
    L.append("Input")
    for ln in res.inputs:
        val = ln.shown if isinstance(ln.shown, str) else U.fmt(ln.shown, 7)
        L.append(f"  {ln.text:>{width}} = {val} {_unit(ln.unit)}".rstrip().ljust(34) + f"  {ln.name}")
    L += ["", "Calculation"]
    pad = " " * (width + 2)
    for ln in res.steps:
        L.append(f"  {ln.text:>{width}} = {X.to_text(ln.formula, name)}")
        if X.symbols(ln.formula):
            L.append(f"{pad} = {X.to_text(ln.formula, name, values=ln.env, fmt=lambda v: U.fmt(v, 5))}")
        val = ln.shown if isinstance(ln.shown, str) else U.fmt(ln.shown)
        tail = f"{pad} = {val} {_unit(ln.unit)}".rstrip()
        L.append(tail.ljust(46) + f"  [{ln.reference}] ({ln.status})")
    L += ["", "Result"]
    val = res.shown if isinstance(res.shown, str) else U.fmt(res.shown)
    L.append(f"  {obj.text} = {val} {_unit(res.unit)}".rstrip())
    if res.check:
        c = res.check
        L.append(f"  {c['text']} = {U.fmt(c['shown'])} {c['unit']}   utilisation {c['expression']} = "
                 f"{c['utilisation']:.2f}  ->  {'OK' if c['ok'] else 'NOT OK'}")
    if res.warnings or res.notes:
        L += ["", "Notes and limitations"]
        L += [f"  ! {w}" for w in dict.fromkeys(res.warnings)]
        L += [f"  - {n}" for n in dict.fromkeys(res.notes)]
    return "\n".join(L) + "\n"


def find_browser() -> str | None:
    for cand in (os.getenv("CKB_BROWSER"), "/opt/pw-browsers/chromium/chrome",
                 shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("google-chrome"),
                 shutil.which("msedge"), shutil.which("chrome"),
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if cand and Path(cand).exists():
            return cand
    root = Path("/opt/pw-browsers")
    if root.exists():
        for p in sorted(root.glob("chromium*/chrome-linux*/chrome")):
            return str(p)
    return None


def to_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Print the report to PDF with a Chromium-based browser, if one is installed."""
    browser = find_browser()
    if not browser:
        return False
    cmd = [browser, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={Path(pdf_path).resolve()}", Path(html_path).resolve().as_uri()]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return Path(pdf_path).exists() and Path(pdf_path).stat().st_size > 1000
