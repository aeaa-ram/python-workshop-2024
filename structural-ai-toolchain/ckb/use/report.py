"""Reports: a calculation template run over any number of cases.

A report is described once, in a small YAML template, and then produced for as many
cases as needed.  The template lists blocks, each with its own options:

    title: Shear check of slab strips
    project: Example bridge
    style: {decimals: 2, units: {V_Rd_c: kN}}
    defaults: {f_ck: 35, gamma_C: 1.5}          # applied to every case
    cases:                                       # inline rows, or {file: cases.xlsx}
      - {case: Strip A, d: 273, A_sl: 1340, b_w: 1000, V_Ed: 150}
      - {case: Strip B, d: 259, A_sl: 754,  b_w: 1000, V_Ed: 140}
    blocks:
      - heading: Shear resistance without shear reinforcement
      - text: Slabs are checked per metre width.
      - calc: V_Rd_c                  # one calculation, written out
        case: governing               # governing | first | <case name>
        show: [equation, substituted, result]
        steps: all                    # all | result | [k, rho_l, V_Rd_c]
        remarks: {d: "from the reinforcement drawing"}
      - table: V_Rd_c                 # every case in one table
        columns: [case, d, A_sl, V_Rd_c, V_Ed, utilisation, verdict]
        sort: utilisation desc
      - chart: V_Rd_c                 # a parameter study
        x: d
        range: [150, 600]
        series: [V_Rd_c, V_Rd_c_min]

The output is a static HTML page laid out for A4, printed to PDF with a
Chromium-based browser.  Equations are MathML printed from the same formula
trees as the code blocks (``expr.to_mathml``), so the report shows the logic
that runs, not a copy of it.
"""
from __future__ import annotations

import csv
import datetime as _dt
import html
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .. import expr as X
from .. import units as U
from ..kb.objects import KnowledgeBase, ResolveError
from .calc import Result, lookup, parse_assignments, run, starting_values
from .style import Style

SHOW_ALL = ("equation", "substituted", "result")


def _e(s) -> str:
    return html.escape(str(s))


# --------------------------------------------------------------------------
# cases
# --------------------------------------------------------------------------
@dataclass
class Case:
    name: str
    values: dict                 # canonical
    given: list
    check: float | None = None   # canonical value of the quantity checked against
    result: Result | None = None
    error: str = ""


def _rows_from_file(path: Path) -> list[dict]:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        ws = load_workbook(path, data_only=True).worksheets[0]
        rows = [[c.value for c in r] for r in ws.iter_rows()]
        head = [str(h).strip() if h is not None else "" for h in rows[0]]
        return [{h: v for h, v in zip(head, r) if h and v is not None} for r in rows[1:] if any(v is not None for v in r)]
    if path.suffix.lower() in (".yaml", ".yml"):
        return list(yaml.safe_load(path.read_text(encoding="utf-8")))
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [{k.strip(): v for k, v in r.items() if k and v not in (None, "")} for r in csv.DictReader(fh)]


def build_cases(kb: KnowledgeBase, target: str, rows: list[dict], defaults: dict | None = None,
                style: Style | None = None) -> list[Case]:
    """Rows of ``name: value`` (a header may carry a unit: ``d [m]``) -> calculated cases."""
    obj = kb.objects[target]
    out = []
    for i, row in enumerate(rows or [{}], 1):
        merged = dict(defaults or {})
        merged.update(row)
        name = str(merged.pop("case", merged.pop("name", f"Case {i}")))
        pairs, check = [], None
        for key, val in merged.items():
            label, unit = key, ""
            if "[" in key or "(" in key:
                label, _, rest = key.replace("(", "[").partition("[")
                unit = rest.rstrip(")] ").strip()
            label = label.strip()
            if obj.check and lookup(kb, label, [obj.check]) == obj.check:
                try:
                    check = U.to_canonical(float(val), unit or kb.unit(obj.check))
                except (TypeError, ValueError, U.UnitError):
                    pass
                continue
            pairs.append(f"{label}={val} {unit}".strip())
        try:
            entered, given = parse_assignments(kb, target, pairs)
            values, origin = starting_values(kb, target, given)
            values.update(entered)
            case = Case(name, values, given, check)
            origin.update({k: "entered" for k in entered})
            case.result = run(kb, target, values, given, origin, check, style)
        except (ValueError, ResolveError) as exc:
            case = Case(name, {}, [], check, None, str(exc))
        out.append(case)
    return out


def governing(cases: list[Case], kb: KnowledgeBase, target: str) -> Case | None:
    ok = [c for c in cases if c.result is not None]
    if not ok:
        return None
    with_check = [c for c in ok if c.result.check]
    if with_check:
        return max(with_check, key=lambda c: c.result.check["utilisation"])
    sense = kb.objects[target].sense
    vals = [c for c in ok if isinstance(c.result.value, (int, float))]
    if not vals:
        return ok[0]
    return min(vals, key=lambda c: c.result.value) if sense == "resistance" else max(vals, key=lambda c: c.result.value)


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------
CSS = """
:root{--paper:#fff;--ink:#16211f;--muted:#5b6966;--rule:#c9d2cf;--soft:#eef2f0;--accent:#0b5d73;
--ok:#0a7d34;--bad:#c0302f;--hl:#f3f7f6;--s1:#2a78d6;--s2:#eb6834}
*{box-sizing:border-box}
body{margin:0;background:#e9edeb;color:var(--ink);font:13px/1.45 "IBM Plex Sans","Segoe UI",Arial,sans-serif}
.sheet{background:var(--paper);max-width:210mm;margin:16px auto;padding:14mm 15mm 16mm;box-shadow:0 1px 4px rgba(0,0,0,.18)}
math{font-family:"Cambria Math","STIX Two Math","Latin Modern Math","Noto Sans Math",math;font-size:1.06em}
table.tb{width:100%;border-collapse:collapse;margin-bottom:7mm;font-size:11.5px}
table.tb td{border:1px solid var(--ink);padding:3px 6px;vertical-align:top}
table.tb small{display:block;color:var(--muted);font-size:9px;letter-spacing:.05em;text-transform:uppercase}
h1{font-size:18px;margin:0 0 4mm;line-height:1.25}
h2{font-size:13px;margin:7mm 0 2mm;padding-bottom:2px;border-bottom:1px solid var(--ink)}
h3{font-size:12px;margin:5mm 0 1mm}
p.text{margin:1mm 0 3mm;max-width:160mm}
.ref{color:var(--muted);margin:0 0 2mm;font-size:11.5px}
.grp{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin:3mm 0 1mm}
.in{display:grid;grid-template-columns:minmax(0,1fr) 15em minmax(0,13em);gap:0 12px;padding:3px 0;border-bottom:1px solid var(--soft);break-inside:avoid;align-items:baseline}
.in .c,.st .c{color:var(--muted);font-size:11px}
.in .c{text-align:right}
.rem{font-style:italic;color:var(--muted);font-size:11px}
.st{padding:4px 0 5px;border-bottom:1px solid var(--soft);break-inside:avoid}
.st .hd{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.st .eqs{padding-left:7mm;margin-top:1px;overflow-wrap:anywhere}
.st .rem{padding-left:7mm}
.eq{display:flex;gap:6px;align-items:baseline;margin:1px 0}
.eq .lhs{min-width:3.6em;text-align:right;flex:none}
.eq math{max-width:100%}
.eq.res{font-weight:700}
.eq.res math{font-weight:700}
.verdict{margin:3mm 0 1mm;padding:6px 10px;border:1.5px solid var(--ink);display:flex;gap:6px 18px;flex-wrap:wrap;align-items:baseline;break-inside:avoid}
.verdict b{font-size:14px}
.ok{color:var(--ok);font-weight:700}.bad{color:var(--bad);font-weight:700}
ul.notes{margin:1mm 0 0;padding-left:16px;font-size:11.5px} ul.notes li{margin:1px 0}
ul.notes li.w{color:var(--bad)}
table.cases{width:100%;border-collapse:collapse;font-size:11.5px;margin:2mm 0}
table.cases th,table.cases td{border-bottom:1px solid var(--rule);padding:3px 6px;text-align:right;white-space:nowrap}
table.cases th:first-child,table.cases td:first-child{text-align:left}
table.cases th{font-weight:600;border-bottom:1px solid var(--ink)}
table.cases th small{display:block;font-weight:400;color:var(--muted)}
table.cases tr.gov td{background:var(--hl);font-weight:700}
table.cases td{font-variant-numeric:tabular-nums}
figure{margin:3mm 0;break-inside:avoid} figcaption{font-size:11px;color:var(--muted)}
svg text{font-family:"IBM Plex Sans","Segoe UI",Arial,sans-serif}
.foot{margin-top:8mm;color:var(--muted);font-size:9.5px;display:flex;justify-content:space-between;gap:12px}
.pb{break-after:page}
@media print{body{background:#fff}.sheet{box-shadow:none;margin:0;max-width:none;padding:0}@page{size:A4;margin:15mm 15mm 17mm}}
"""


def _num_ml(style: Style, v) -> str:
    if isinstance(v, str):
        return f"<mtext>{_e(v)}</mtext>"
    s = style.fmt(v)
    if s.startswith("-"):
        return f"<mo>&#x2212;</mo><mn>{_e(s[1:])}</mn>"
    return f"<mn>{_e(s)}</mn>"


def _unit_ml(u: str) -> str:
    return "" if u in ("-", "") else f"<mtext>&#x2009;{_e(u)}</mtext>"


def calc_block(kb: KnowledgeBase, res: Result, opts: dict) -> str:
    """One calculation written out: inputs, every step (equation, substituted values, result), verdict."""
    style = res.style
    obj = kb.objects[res.target]
    show = set(opts.get("show") or SHOW_ALL)
    steps_opt = opts.get("steps", "all")
    remarks = {lookup(kb, k) or k: v for k, v in (opts.get("remarks") or {}).items()}
    P = ['<div class="calc">']
    if opts.get("title", True):
        P.append(f'<h3 data-outline="{_e(obj.text + " – " + obj.name)}" data-find="{_e(obj.name)}">'
                 f"<math>{obj.ml}</math> &nbsp;{_e(obj.name)}</h3>")
        P.append(f'<p class="ref">{_e(obj.reference_text)}</p>')
    if opts.get("inputs", True):
        P.append('<div class="grp">Input</div>')
        for ln in res.inputs:
            val = _num_ml(style, ln.shown)
            note = {"fixed": f"fixed by {obj.code}", "recommended": "recommended value",
                    "given": "entered directly"}.get(ln.source, "")
            ref = " · ".join(x for x in (ln.reference, note) if x)
            rem = remarks.get(ln.id)
            P.append(f'<div class="in"><div>{_e(ln.name)}</div><div><math>{kb.ml(ln.id)}<mo>=</mo>{val}'
                     f'{_unit_ml(ln.unit)}</math></div><div class="c">{_e(ref)}'
                     + (f'<div class="rem">{_e(rem)}</div>' if rem else "") + "</div></div>")
    if steps_opt == "result":
        lines = [ln for ln in res.steps if ln.id == res.target]
    elif isinstance(steps_opt, list):
        want = {lookup(kb, s) or s for s in steps_opt} | {res.target}
        lines = [ln for ln in res.steps if ln.id in want]
    else:
        lines = res.steps
    P.append('<div class="grp">Calculation</div>')
    for ln in lines:
        o = kb.objects[ln.id]
        sym = f"<math>{o.ml}</math>"
        eqs = []

        def lhs():
            return sym if not eqs else ""
        if "equation" in show:
            eqs.append(f'<div class="eq"><span class="lhs">{lhs()}</span><math displaystyle="true"><mo>=</mo>'
                       f'{X.to_mathml(o.tree, kb.ml)}</math></div>')
        if "substituted" in show and X.symbols(o.tree):
            # the numbers are in the units the formulas work in (N, mm, MPa)
            eqs.append(f'<div class="eq"><span class="lhs">{lhs()}</span><math displaystyle="true">'
                       f'<mo>=</mo>{X.to_mathml(o.tree, kb.ml, values=ln.env, fmt=style.fmt_short)}</math></div>')
        if "result" in show or not eqs:
            eqs.append(f'<div class="eq res"><span class="lhs">{lhs()}</span><math><mo>=</mo>'
                       f'{_num_ml(style, ln.shown)}{_unit_ml(ln.unit)}</math></div>')
        ref = o.reference_text.replace(o.code + " ", "") if o.code == obj.code else o.reference_text
        rem = remarks.get(ln.id)
        P.append(f'<div class="st"><div class="hd"><span>{_e(o.name)}</span><span class="c">{_e(ref)}</span></div>'
                 f'<div class="eqs">{"".join(eqs)}</div>'
                 + (f'<div class="rem">{_e(rem)}</div>' if rem else "") + "</div>")
    if res.check:
        c = res.check
        u = c["utilisation"]
        cls, word = ("ok", "OK") if c["ok"] else ("bad", "NOT OK")
        num, den = (kb.ml(c["against"]), obj.ml) if obj.sense == "resistance" else (obj.ml, kb.ml(c["against"]))
        ratio = f"<mi>η</mi><mo>=</mo>{num}<mo>/</mo>{den}"
        P.append(f'<div class="verdict"><span><math>{obj.ml}<mo>=</mo>{_num_ml(style, res.shown)}{_unit_ml(res.unit)}'
                 f'</math></span><span><math>{kb.ml(c["against"])}<mo>=</mo>{_num_ml(style, c["shown"])}'
                 f'{_unit_ml(c["unit"])}</math></span><span><math>{ratio}</math> = <b>{u:.2f}</b> '
                 f'{"≤" if c["ok"] else ">"} 1.00</span><span class="{cls}">{word}</span></div>')
    else:
        P.append(f'<div class="verdict"><span><math>{obj.ml}<mo>=</mo>{_num_ml(style, res.shown)}'
                 f'{_unit_ml(res.unit)}</math></span></div>')
    notes = []
    if opts.get("checks", True):
        for chk in res.checks:
            mark = {"ok": "met", "violated": "NOT MET", "not checked": "to be checked"}[chk["status"]]
            cls = ' class="w"' if chk["status"] == "violated" else ""
            notes.append(f"<li{cls}>{_e(chk['text'])} ({_e(chk['clause'])}): {mark}</li>")
        for w in res.warnings:
            if not w.startswith("Not met"):
                notes.append(f'<li class="w">{_e(w)}</li>')
    if opts.get("limitations", False):
        for t in dict.fromkeys(res.limitations):
            notes.append(f"<li>{_e(t)}</li>")
    if notes:
        P.append('<ul class="notes">' + "".join(notes) + "</ul>")
    P.append("</div>")
    return "".join(P)


def table_block(kb: KnowledgeBase, target: str, cases: list[Case], opts: dict, style: Style, gov: Case | None) -> str:
    obj = kb.objects[target]
    cols = opts.get("columns")
    if not cols:
        _, inputs = kb.plan(target)
        cols = ["case"] + [p for p in inputs if any(c.result and p in [i.id for i in c.result.inputs
                                                                        if i.source == "entered"] for c in cases)]
        cols += [target] + (["check", "utilisation", "verdict"] if obj.check else [])
    rows = [c for c in cases if c.result is not None]
    sort = opts.get("sort")
    if sort:
        key, _, order = str(sort).partition(" ")
        rows.sort(key=lambda c: _cell_value(kb, c, key) if isinstance(_cell_value(kb, c, key), (int, float)) else 0,
                  reverse=order.strip().lower() == "desc")
    head = []
    for col in cols:
        if col == "case":
            head.append("<th>Case</th>")
        elif col in ("utilisation", "verdict"):
            head.append(f"<th>{col.capitalize()}</th>")
        elif col == "check":
            head.append(f"<th><math>{kb.ml(obj.check)}</math><small>{_e(style.unit(kb, obj.check))}</small></th>")
        else:
            sid = lookup(kb, col) or col
            u = style.unit(kb, sid)
            head.append(f"<th><math>{kb.ml(sid)}</math><small>{_e('' if u == '-' else u)}</small></th>")
    body = []
    for c in rows:
        tds = []
        for col in cols:
            v = _cell_value(kb, c, col)
            if col == "case":
                tds.append(f"<td>{_e(c.name)}</td>")
            elif col == "verdict":
                cls = "ok" if v == "OK" else "bad"
                tds.append(f'<td class="{cls}">{_e(v)}</td>')
            elif col == "utilisation":
                tds.append(f"<td>{'' if v is None else f'{v:.2f}'}</td>")
            else:
                sid = obj.check if col == "check" else (lookup(kb, col) or col)
                tds.append(f"<td>{'' if v is None else _e(style.fmt(style.show(kb, sid, v)))}</td>")
        cls = ' class="gov"' if gov is not None and c is gov and opts.get("highlight", True) else ""
        body.append(f"<tr{cls}>{''.join(tds)}</tr>")
    for c in cases:
        if c.result is None:
            body.append(f'<tr><td>{_e(c.name)}</td><td colspan="{len(cols) - 1}" class="bad" style="text-align:left">'
                        f"{_e(c.error)}</td></tr>")
    title = opts.get("title")
    cap = f"<h3>{_e(title)}</h3>" if title else ""
    note = '<p class="ref">The governing case is highlighted.</p>' if gov is not None and len(rows) > 1 else ""
    return f'{cap}<table class="cases"><tr>{"".join(head)}</tr>{"".join(body)}</table>{note}'


def _cell_value(kb, c: Case, col: str):
    r = c.result
    if r is None:
        return None
    if col == "case":
        return c.name
    if col == "utilisation":
        return r.check["utilisation"] if r.check else None
    if col == "verdict":
        return ("OK" if r.check["ok"] else "NOT OK") if r.check else None
    sid = lookup(kb, col) or col
    if col == "check" or sid == kb.objects[r.target].check:
        return c.check
    return r.env().get(sid)


def chart_data(kb: KnowledgeBase, target: str, case: Case, opts: dict, style: Style) -> dict | None:
    """A parameter study: the result (and optionally one more step) against one input."""
    if case is None or case.result is None:
        return None
    x = lookup(kb, str(opts.get("x", ""))) or ""
    _, inputs = kb.plan(target, case.given)
    if x not in inputs:
        x = next((p for p in inputs if kb.quantities.get(p) and kb.quantities[p].kind == "input"), inputs[0])
    series = [lookup(kb, s) or s for s in (opts.get("series") or [target])]
    series = [s for s in series if s in kb.objects][:2] or [target]
    u_y = style.unit(kb, series[0])
    series = [s for s in series if U.parse_unit(style.unit(kb, s)).dims == U.parse_unit(u_y).dims]
    q = kb.quantities.get(x)
    x0 = case.values[x]
    if opts.get("range"):
        lo, hi = (U.to_canonical(float(v), style.unit(kb, x)) for v in opts["range"])
    elif q is not None and q.range:
        lo, hi = q.range
    else:
        lo, hi = 0.5 * x0, 1.5 * x0
    n = int(opts.get("points", 80))
    pts = {s: [] for s in series}
    xs = []
    for i in range(n + 1):
        xv = lo + (hi - lo) * i / n
        vals = dict(case.values)
        vals[x] = xv
        try:
            _, trace = kb.evaluate(target, vals, case.given)
        except ResolveError:
            continue
        env = {t.id: t.value for t in trace}
        xs.append(style.show(kb, x, xv))
        for s in series:
            v = env.get(s)
            pts[s].append(style.show(kb, s, v) if isinstance(v, (int, float)) else None)
    if not xs:
        return None
    ref = None
    if case.check is not None and kb.objects[target].check and series[0] == target:
        ref = style.show(kb, target, case.check)
    return {"xs": xs, "series": [(kb.name(s), pts[s]) for s in series],
            "x_label": f"{kb.name(x)} [{style.unit(kb, x)}]", "y_label": f"[{u_y}]",
            "marker": (style.show(kb, x, x0), style.show(kb, series[0], case.result.env().get(series[0]))),
            "ref": (kb.name(kb.objects[target].check), ref) if ref is not None else None,
            "caption": opts.get("caption") or f"{kb.name(series[0])} against {kb.name(x)} "
                                               f"({case.name}; other inputs as in that case)"}


def chart_block(kb: KnowledgeBase, target: str, case: Case, opts: dict, style: Style) -> str:
    """A parameter study as a static SVG line chart."""
    data = chart_data(kb, target, case, opts, style)
    return svg_line_chart(**data) if data else ""


def _nice(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    ticks, t = [], start
    while t <= hi + 1e-9 * step:
        if t >= lo - 1e-9 * step:
            ticks.append(round(t, 10))
        t += step
    return ticks


def svg_line_chart(xs, series, x_label="", y_label="", marker=None, ref=None, caption="",
                   width=640, height=260) -> str:
    colors = ["#2a78d6", "#eb6834"]
    ys = [v for _, vals in series for v in vals if v is not None] + ([ref[1]] if ref else [])
    y_lo, y_hi = min(0.0, min(ys)), max(ys) * 1.08
    yt = _nice(y_lo, y_hi)
    y_lo, y_hi = min(y_lo, yt[0]), max(y_hi, yt[-1])
    xt = _nice(min(xs), max(xs))
    ml, mr, mt, mb = 56, 18, 14, 40
    W, H = width - ml - mr, height - mt - mb
    sx = lambda v: ml + (v - min(xs)) / (max(xs) - min(xs) or 1) * W            # noqa: E731
    sy = lambda v: mt + H - (v - y_lo) / (y_hi - y_lo or 1) * H                 # noqa: E731
    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="{_e(caption)}">']
    for t in yt:
        out.append(f'<line x1="{ml}" x2="{ml + W}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="#e3e8e6" stroke-width="1"/>'
                   f'<text x="{ml - 6}" y="{sy(t) + 4:.1f}" text-anchor="end" font-size="10" fill="#5b6966">{_tick(t)}</text>')
    for t in xt:
        if min(xs) - 1e-9 <= t <= max(xs) + 1e-9:
            out.append(f'<text x="{sx(t):.1f}" y="{mt + H + 14}" text-anchor="middle" font-size="10" fill="#5b6966">{_tick(t)}</text>')
    out.append(f'<line x1="{ml}" x2="{ml + W}" y1="{mt + H}" y2="{mt + H}" stroke="#9aa5a2" stroke-width="1"/>')
    out.append(f'<text x="{ml + W / 2:.0f}" y="{height - 6}" text-anchor="middle" font-size="11" fill="#16211f">{_e(x_label)}</text>')
    out.append(f'<text x="{ml - 44}" y="{mt + 4}" font-size="10" fill="#5b6966">{_e(y_label)}</text>')
    if ref:
        out.append(f'<line x1="{ml}" x2="{ml + W}" y1="{sy(ref[1]):.1f}" y2="{sy(ref[1]):.1f}" stroke="#16211f" stroke-width="1"/>'
                   f'<text x="{ml + W - 2}" y="{sy(ref[1]) - 4:.1f}" text-anchor="end" font-size="10" fill="#16211f">{_e(ref[0])} = {_tick(ref[1])}</text>')
    for k, (name, vals) in enumerate(series):
        d = []
        for xv, yv in zip(xs, vals):
            if yv is None:
                continue
            d.append(f"{'M' if not d else 'L'}{sx(xv):.1f},{sy(yv):.1f}")
        out.append(f'<path d="{" ".join(d)}" fill="none" stroke="{colors[k]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    if marker and isinstance(marker[1], (int, float)):
        out.append(f'<circle cx="{sx(marker[0]):.1f}" cy="{sy(marker[1]):.1f}" r="4.5" fill="#2a78d6" stroke="#fff" stroke-width="2"/>')
    if len(series) > 1:
        lx = ml + 8
        for k, (name, _) in enumerate(series):
            out.append(f'<line x1="{lx}" x2="{lx + 16}" y1="{mt + 8 + 14 * k}" y2="{mt + 8 + 14 * k}" stroke="{colors[k]}" stroke-width="2"/>'
                       f'<text x="{lx + 21}" y="{mt + 12 + 14 * k}" font-size="10.5" fill="#16211f">{_e(name)}</text>')
    out.append("</svg>")
    return f"<figure>{''.join(out)}<figcaption>{_e(caption)}</figcaption></figure>"


def _tick(v: float) -> str:
    if abs(v) >= 1000 or v == int(v):
        return f"{v:.0f}"
    return f"{v:.3g}"


# --------------------------------------------------------------------------
# the report
# --------------------------------------------------------------------------
def load_template(path: Path) -> dict:
    """A template from YAML (any file name: the web calculator saves it as .txt)."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def layout(kb: KnowledgeBase, template: dict, base: Path | None = None) -> tuple[list[dict], list[str], Style]:
    """The report as a list of blocks with everything calculated: what every renderer
    (HTML for PDF, Word) draws.  Returns (items, objects used, style)."""
    style = Style.load(template.get("style") or {})
    blocks = template.get("blocks") or []
    targets = [lookup(kb, str(b.get(k))) for b in blocks for k in ("calc", "table", "chart") if b.get(k)]
    targets = [t for t in targets if t in kb.objects]
    if not targets:
        raise ValueError("the template has no calc, table or chart block naming a calculation object")
    rows = template.get("cases")
    if isinstance(rows, dict) and rows.get("file"):
        f = Path(rows["file"])
        rows = _rows_from_file(f if f.is_absolute() or base is None else base / f)
    cache: dict[str, list[Case]] = {}

    def cases_for(t: str) -> list[Case]:
        if t not in cache:
            cache[t] = build_cases(kb, t, rows or [{}], template.get("defaults"), style)
        return cache[t]

    def pick(t: str, which) -> Case | None:
        cs = cases_for(t)
        if which in (None, "governing"):
            return governing(cs, kb, t)
        if which == "first":
            return cs[0]
        return next((c for c in cs if c.name == str(which)), None)

    items, used = [], set()
    for b in blocks:
        if b == "pagebreak" or (isinstance(b, dict) and "pagebreak" in b):
            items.append({"type": "pagebreak"})
        elif "heading" in b:
            items.append({"type": "heading", "text": str(b["heading"])})
        elif "text" in b:
            items.append({"type": "text", "text": str(b["text"])})
        elif "calc" in b:
            t = lookup(kb, str(b["calc"]))
            c = pick(t, b.get("case"))
            if c is None or c.result is None:
                items.append({"type": "error", "text": f"{b['calc']}: no case to calculate ({c.error if c else ''})"})
                continue
            label = ""
            if len(cases_for(t)) > 1 and b.get("label", True):
                label = f"Case: {c.name}" + (" (governing)" if c is governing(cases_for(t), kb, t) else "")
            items.append({"type": "calc", "result": c.result, "opts": b, "label": label})
            used |= {s.id for s in c.result.steps}
        elif "table" in b:
            t = lookup(kb, str(b["table"]))
            items.append({"type": "table", "target": t, "cases": cases_for(t), "opts": b,
                          "gov": governing(cases_for(t), kb, t)})
            used |= set(kb.plan(t)[0])
        elif "chart" in b:
            t = lookup(kb, str(b["chart"]))
            data = chart_data(kb, t, pick(t, b.get("case")), b, style)
            if data:
                items.append({"type": "chart", "data": data})
            used |= set(kb.plan(t)[0])
    return items, sorted(o for o in used if o in kb.objects), style


def title_block(template: dict) -> list[list[tuple[str, str]]]:
    """Rows of (label, text) for the title block."""
    date = template.get("date") or _dt.date.today().isoformat()
    return [[("Project", template.get("project", "")), ("Subject", template.get("subject", template.get("title", ""))),
             ("Calc. no.", template.get("number", ""))],
            [("Made by / date", f"{template.get('made_by', '')}   {date}"), ("Checked by / date", template.get("checked_by", "")),
             ("Approved by / date", template.get("approved_by", ""))]]


def footer_text(kb: KnowledgeBase, used: list[str]) -> tuple[str, str]:
    codes = sorted({kb.objects[o].code for o in used if kb.objects[o].code})
    return (f"{', '.join(codes)}. Recommended values unless stated. Substituted values are in N, mm and MPa.",
            " ".join(f"ckb {oid} {kb.objects[oid].version}" for oid in used))


def render(kb: KnowledgeBase, template: dict, base: Path | None = None, with_objects: bool = False):
    """The report as one static HTML page (with ``with_objects``: also the objects it used)."""
    items, used, style = layout(kb, template, base)
    P = []
    if template.get("title_block", True):
        rows = title_block(template)
        widths = ("40%", "40%", "")
        P.append('<table class="tb">' + "".join(
            "<tr>" + "".join(f'<td{f" style=width:{w}" if w else ""}><small>{_e(k)}</small>{_e(v)}&nbsp;</td>'
                             for (k, v), w in zip(r, widths)) + "</tr>" for r in rows) + "</table>")
    if template.get("title"):
        P.append(f'<h1 data-outline="{_e(template["title"])}">{_e(template["title"])}</h1>')
    for it in items:
        t = it["type"]
        if t == "heading":
            P.append(f'<h2 data-outline="{_e(it["text"])}">{_e(it["text"])}</h2>')
        elif t == "text":
            P.append(f'<p class="text">{_e(it["text"])}</p>')
        elif t == "pagebreak":
            P.append('<div class="pb"></div>')
        elif t == "error":
            P.append(f'<p class="bad">{_e(it["text"])}</p>')
        elif t == "calc":
            if it["label"]:
                P.append(f'<p class="ref">{_e(it["label"])}</p>')
            P.append(calc_block(kb, it["result"], it["opts"]))
        elif t == "table":
            P.append(table_block(kb, it["target"], it["cases"], it["opts"], style, it["gov"]))
        elif t == "chart":
            P.append(svg_line_chart(**it["data"]))
    left, versions = footer_text(kb, used)
    P.append(f'<div class="foot"><span>{_e(left)}</span></div>')
    title = template.get("title") or "Calculation"
    # the versions are kept out of sight: in the page's metadata, where `ckb verify` reads them
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="generator" content="{_e(versions)}"><title>{_e(title)}</title>'
            f"<style>{CSS}</style></head><body><div class=\"sheet\">{''.join(P)}</div></body></html>")
    return (page, used) if with_objects else page


def cases_from_calculator(kb: KnowledgeBase, path: Path) -> list[dict]:
    """The inputs of an Excel calculator generated by ``excel_bridge`` as one case.

    The workbook is the place to change inputs; this turns its current inputs into a
    report row, so a report can be printed from it at any time.
    """
    from .excel_bridge import read_calculator
    rec = read_calculator(Path(path))
    if rec is None:
        raise ValueError(f"{path} is not a calculator generated from the knowledge base")
    style = Style.load(rec.get("style") or {})
    row = {"case": Path(path).stem}
    for sid, v in rec["inputs"].items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            unit = style.unit(kb, sid)
            row[sid if unit == "-" else f"{sid} [{unit}]"] = v
    return [row]


def quick_template(target: str, values: dict, kb: KnowledgeBase, check: float | None = None,
                   meta: dict | None = None, style: Style | None = None) -> dict:
    """A one-case template for ``python -m ckb report V_Rd_c d=... ``."""
    row = {"case": "Calculation"}
    style = style or Style()
    for k, v in values.items():
        u = kb.unit(k)
        row[k if u == "-" else f"{k} [{u}]"] = U.from_canonical(v, u) if isinstance(v, (int, float)) else v
    if check is not None and kb.objects[target].check:
        row[f"{kb.objects[target].check} [{kb.unit(kb.objects[target].check)}]"] = U.from_canonical(
            check, kb.unit(kb.objects[target].check))
    t = {"title": kb.objects[target].name, "style": style.to_dict(), "cases": [row],
         "blocks": [{"calc": target, "show": list(SHOW_ALL), "steps": "all", "limitations": True}]}
    t.update(meta or {})
    return t


def example_template(kb: KnowledgeBase, target: str) -> str:
    """A commented template to start from (``python -m ckb report-template V_Rd_c``)."""
    obj = kb.objects[target]
    _, inputs = kb.plan(target)
    values, _ = starting_values(kb, target)
    ins = [p for p in inputs if kb.quantities.get(p) and kb.quantities[p].kind == "input"]
    def row(name, k):
        cells = [f"case: {name}"] + [f"{kb.var(p)}: {X._short(round(U.from_canonical(values[p], kb.unit(p)) * k, 3))}"
                                     for p in ins[:4]]
        if obj.check:
            cells.append(f"{kb.var(obj.check)}: {X._short(round(U.from_canonical(kb.quantities[obj.check].start, kb.unit(obj.check)) * k, 1))}"
                         if obj.check in kb.quantities and kb.quantities[obj.check].start else f"{kb.var(obj.check)}: 100")
        return "  - {" + ", ".join(cells) + "}"
    lines = [
        f"# Report template for {obj.text} ({obj.reference_text}).",
        "# Run:  python -m ckb report --template this_file.yaml [--pdf]",
        f"title: {obj.name}",
        "project: ''", "number: ''", "made_by: ''", "checked_by: ''",
        "style:",
        "  decimals: 2            # digits after the decimal point",
        "  min_significant: 3     # small values keep 3 significant digits",
        f"  units: {{{kb.var(target)}: {kb.unit(target)}}}   # display unit per quantity",
        "defaults:               # applied to every case (values in the usual units)",
    ] + [f"  {kb.var(p)}: {X._short(round(U.from_canonical(values[p], kb.unit(p)), 4))}"
         for p in inputs if p not in ins[:4]] + [
        "cases:                  # one row per case; or  cases: {file: cases.xlsx}  (header = names, e.g. 'd [mm]')",
        row("Case 1", 1.0), row("Case 2", 0.85), row("Case 3", 1.2),
        "blocks:",
        f"  - heading: {obj.name}",
        f"  - calc: {target}",
        "    case: governing      # governing | first | a case name",
        "    show: [equation, substituted, result]   # drop items to shorten",
        "    steps: all           # all | result | a list of intermediate steps",
        "    remarks: {}          # e.g. {d: 'from drawing 123'}",
        "    limitations: false   # print the scope and limitations of the objects used",
        f"  - table: {target}",
        "    sort: utilisation desc" if obj.check else "    sort: ''",
        f"  - chart: {target}",
        f"    x: {kb.var(ins[0]) if ins else kb.var(inputs[0])}",
    ]
    return "\n".join(lines) + "\n"


def render_text(kb: KnowledgeBase, res: Result) -> str:
    """The calculation for a terminal."""
    style = res.style
    obj = kb.objects[res.target]
    name = kb.name
    L = [f"{obj.text} - {obj.name}", obj.reference_text, ""]
    width = max([len(l.text) for l in res.inputs + res.steps] + [4])
    L.append("Input")
    for ln in res.inputs:
        val = ln.shown if isinstance(ln.shown, str) else style.fmt(ln.shown)
        unit = "" if ln.unit == "-" else ln.unit
        L.append(f"  {ln.text:>{width}} = {val} {unit}".rstrip().ljust(36) + f"  {ln.name}")
    L += ["", "Calculation"]
    pad = " " * (width + 2)
    for ln in res.steps:
        L.append(f"  {ln.text:>{width}} = {X.to_text(ln.formula, name)}")
        if X.symbols(ln.formula):
            L.append(f"{pad} = {X.to_text(ln.formula, name, values=ln.env, fmt=style.fmt)}")
        val = ln.shown if isinstance(ln.shown, str) else style.fmt(ln.shown)
        unit = "" if ln.unit == "-" else ln.unit
        L.append(f"{pad} = {val} {unit}".rstrip().ljust(48) + f"  {ln.reference}")
    L += ["", "Result"]
    val = res.shown if isinstance(res.shown, str) else style.fmt(res.shown)
    L.append(f"  {obj.text} = {val} {'' if res.unit == '-' else res.unit}".rstrip())
    if res.check:
        c = res.check
        L.append(f"  {c['text']} = {style.fmt(c['shown'])} {c['unit']}   {c['expression']} = "
                 f"{c['utilisation']:.2f}  ->  {'OK' if c['ok'] else 'NOT OK'}")
    if res.checks:
        L += ["", "Conditions"]
        for chk in res.checks:
            mark = {"ok": "met", "violated": "NOT MET", "not checked": "to be checked"}[chk["status"]]
            L.append(f"  {mark:13} {chk['text']} ({chk['clause']})")
    extra = [w for w in res.warnings if not w.startswith("Not met")]
    if extra:
        L += [""] + [f"  ! {w}" for w in extra]
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
    """Print the report to PDF with a Chromium-based browser (Edge or Chrome on Windows), then add
    bookmarks for the title, the headings and every calculation, and the document title."""
    browser = find_browser()
    if not browser:
        return False
    cmd = [browser, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={Path(pdf_path).resolve()}", Path(html_path).resolve().as_uri()]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    ok = Path(pdf_path).exists() and Path(pdf_path).stat().st_size > 1000
    if ok:
        try:
            add_bookmarks(Path(pdf_path), Path(html_path).read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001 - bookmarks are a nicety
            pass
    return ok


def outline(page_html: str) -> list[tuple[int, str, str]]:
    """(level, bookmark text, text to find on the page) for every h1/h2/h3 with data-outline."""
    out = []
    for m in re.finditer(r'<h([123])\s+data-outline="([^"]*)"(?:\s+data-find="([^"]*)")?', page_html):
        text = html.unescape(m.group(2))
        out.append((int(m.group(1)), text, html.unescape(m.group(3) or m.group(2))))
    return out


def add_bookmarks(pdf_path: Path, page_html: str) -> int:
    """Bookmarks for the report's headings, found page by page in reading order."""
    from pypdf import PdfReader, PdfWriter
    marks = outline(page_html)
    reader = PdfReader(str(pdf_path))
    key = lambda t: re.sub(r"[^0-9a-z]+", "", t.lower())       # noqa: E731
    pages = [key(p.extract_text() or "") for p in reader.pages]
    writer = PdfWriter(clone_from=reader)
    parents: dict[int, object] = {}
    page, n = 0, 0
    for level, text, find in marks:
        k = key(find)
        hit = next((i for i in range(page, len(pages)) if k and k in pages[i]), None)
        if hit is None:
            continue
        page = hit
        parent = next((parents[lv] for lv in range(level - 1, 0, -1) if lv in parents), None)
        parents[level] = writer.add_outline_item(title=text, page_number=hit, parent=parent)
        for deeper in [lv for lv in parents if lv > level]:
            del parents[deeper]
        n += 1
    title = re.search(r"<title>(.*?)</title>", page_html)
    versions = re.search(r'<meta name="generator" content="([^"]*)"', page_html)
    meta = {"/Title": html.unescape(title.group(1))} if title else {}
    if versions:
        meta["/Keywords"] = html.unescape(versions.group(1))        # read by `ckb verify`
    if meta:
        writer.add_metadata(meta)
    writer.page_mode = "/UseOutlines"
    with open(pdf_path, "wb") as fh:
        writer.write(fh)
    return n
