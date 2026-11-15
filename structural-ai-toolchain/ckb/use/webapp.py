"""The web calculator: the knowledge base as one self-contained HTML file.

No server and no installation: the file holds the objects, their formulas as plain
JavaScript functions, the design background and - out of the way, on a Status tab -
the evidence behind each object.  An engineer finds a quantity in the code tree or
by searching ("concrete shear"), types the inputs and reads a clean calculation that
updates as they type.  Dependencies are resolved in the page, and any intermediate
value can be entered directly instead of being calculated.

Per object there are five tabs:

    Calculate           inputs, the calculation, conditions, cases, a report template
    Design background   scope, limitations, pitfalls and guidance with their sources;
                        where the object is shared with other codes; a dependency map
    Chart               the result against any input (a parameter study)
    Code                the Python code block and the function this page runs
    Status              confidence, sources, simplifications found, benchmarks,
                        independent reference check

The JavaScript functions are printed from the same formula trees as the Python code
blocks, the Excel formulas, the Mathcad worksheet and the report equations
(``expr.to_js`` / ``to_python`` / ``to_excel`` / ``to_mathml``), so none of them can
drift from the knowledge base.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import expr as X
from .. import units as U
from ..kb.codegen import module_source
from ..kb.objects import KnowledgeBase
from ..kb.search import index as search_index

MAX_POINTS = 160     # benchmark points per object shown on the Status tab

UNIT_CHOICES = ["N", "kN", "MN", "mm", "cm", "m", "mm²", "cm²", "m²", "mm³", "cm³", "m³", "mm⁴", "cm⁴", "m⁴",
                "MPa", "N/mm²", "kPa", "GPa", "Nmm", "kNm", "MN·m", "kN/m", "N/mm"]


def unit_choices(unit: str) -> list:
    """[[text, factor], ...]: the quantity's own unit first, then units it can be shown in."""
    own = U.parse_unit(unit)
    if own.text in ("°", "rad"):
        opts = ["°", "rad"]
    elif own.text in ("‰", "%"):
        opts = ["‰", "%", "-"]
    elif own.dims == U.parse_unit("-").dims:
        opts = []
    else:
        opts = [u for u in UNIT_CHOICES if U.parse_unit(u).dims == own.dims]
    out, seen = [[own.text, own.factor]], {own.text}
    for u in opts:
        info = U.parse_unit(u)
        if info.text not in seen:
            seen.add(info.text)
            out.append([info.text, info.factor])
    return out


def _ref(kb: KnowledgeBase, item) -> str:
    if not getattr(item, "clause", ""):
        return ""
    c = item.clause
    return f"{item.code or ''} " + (c if c.lower().startswith(("table", "fig")) else f"cl. {c}")


def payload(kb: KnowledgeBase, tax=None) -> dict:
    objects = {}
    for o in kb.objects.values():
        b = o.benchmarks
        pts = [[it["expected"], it["got"], it["status"], 1 if it.get("per_width") else 0, it.get("source", ""),
                it.get("where", ""), it.get("detail", "")]
               for it in b.get("items", []) if isinstance(it.get("expected"), (int, float))
               and isinstance(it.get("got"), (int, float))]
        pts.sort(key=lambda p: p[2] == "agree")
        ev = o.evidence
        objects[o.id] = {
            "id": o.id, "text": o.text, "ml": o.ml, "name": o.name, "unit": o.unit, "units": unit_choices(o.unit),
            "ref": o.reference_text, "code": o.code, "topic": o.topic, "path": o.topic_path, "basis": o.basis,
            "params": o.params, "check": o.check, "sense": o.sense, "fixed": o.fixed, "refs": o.refs,
            "mlF": X.to_mathml(o.tree, kb.ml), "mlS": X.to_mathml(o.tree, kb.ml, slots=True),
            "tex": f"{o.tex} = {X.to_latex(o.tree, kb.tex)}",
            "checks": [{"text": c.get("text", c["when"]), "clause": c.get("clause", ""),
                        "syms": X.symbols(X.parse(c["when"]))} for c in o.checks],
            "background": o.background,
            "alternatives": [{"ml": X.to_mathml(X.parse(a["formula"]), kb.ml), "when": a.get("when", "")}
                             for a in o.alternatives if a.get("formula")],
            "python": module_source(kb, o), "version": o.version,
            "conf": o.confidence,
            "ev": {"sources": ev.get("sources", 0), "formulas": ev.get("formula_instances", 0),
                   "printed": ev.get("printed_values", 0), "practice": ev.get("practice", []),
                   "variants": [{k: v[k] for k in ("text", "relation", "instances", "sources", "differences",
                                                   "reason", "reproduced", "compared") if k in v}
                                for v in ev.get("variants", [])]},
            "bench": {"total": b.get("total", 0), "agree": b.get("agree", 0), "deviation": b.get("deviation", 0),
                      "not_comparable": b.get("not_comparable", 0), "pts": pts[:MAX_POINTS]},
            "reference": o.reference,
        }
    quantities = {}
    for q in kb.quantities.values():
        quantities[q.id] = {"id": q.id, "text": q.text, "ml": q.ml, "name": q.name, "unit": q.unit,
                            "units": unit_choices(q.unit), "kind": q.kind, "value": q.value, "start": q.start,
                            "range": q.range, "choices": q.choices, "ndp": q.ndp, "ref": _ref(kb, q).strip(),
                            "background": q.background, "seen": q.seen}
    return {"meta": kb.meta, "codes": kb.codes, "references": kb.references, "sources": len(kb.sources),
            "objects": objects, "quantities": quantities, "index": search_index(kb, tax)}


def functions_js(kb: KnowledgeBase) -> str:
    lines = ["const F = {"]
    for o in kb.objects.values():
        lines.append(f"  {json.dumps(o.id)}: function (e) {{ return {X.to_js(o.tree, lambda s: f'e.{s}')}; }},")
    lines.append("};")
    lines.append("const C = {")
    for o in kb.objects.values():
        if o.checks:
            fns = ", ".join(f"function (e) {{ return {X.to_js(X.parse(c['when']), lambda s: f'e.{s}')}; }}"
                            for c in o.checks)
            lines.append(f"  {json.dumps(o.id)}: [{fns}],")
    lines.append("};")
    return "\n".join(lines)


def render(kb: KnowledgeBase, standalone: bool = True, files: dict | None = None) -> str:
    """The page.  ``files`` (from ``share.calculator_files``) embeds an Excel calculator and a Mathcad
    worksheet per object, so the page offers them for download without Python."""
    from ..distill.taxonomy import load
    data = payload(kb, load())
    if files:
        data["files"] = files
    data = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = (TEMPLATE.replace("/*__FUNCTIONS__*/", functions_js(kb)).replace("/*__DATA__*/", data)
            .replace("__STANDALONE__", "true" if standalone else "false"))
    if not standalone:
        return page
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            "</head>\n<body>\n" + page + "\n</body>\n</html>\n")


def write(kb: KnowledgeBase, path: Path, standalone: bool = True, files: dict | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(kb, standalone, files), encoding="utf-8")
    return path


TEMPLATE = r"""<title>Calculation Knowledge Base</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Noto+Sans+Math&display=swap">
<style>
:root{
  --bg:#f1f2f0; --surface:#fcfcfb; --raised:#f5f6f4; --ink:#1b2220; --ink2:#47514e; --muted:#6a7471; --rule:#d8dcd9; --soft:#eaece9;
  --accent:#0b5d73; --accent-soft:#dcecf0; --s1:#2a78d6; --s2:#eb6834;
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --crit:#d03b3b; --ok-ink:#0a7a2f; --bad-ink:#b3261e;
  --font:"IBM Plex Sans","Segoe UI",system-ui,Arial,sans-serif; --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  --math:"Cambria Math","STIX Two Math","Latin Modern Math","Noto Sans Math",math;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#121312; --surface:#1a1a19; --raised:#222321; --ink:#e8ebe9; --ink2:#bcc4c1; --muted:#949d9a; --rule:#353836; --soft:#2a2c2a;
  --accent:#6cc3d8; --accent-soft:#18363e; --s1:#3987e5; --s2:#d95926;
  --ok-ink:#62d08a; --bad-ink:#f2928b; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#121312; --surface:#1a1a19; --raised:#222321; --ink:#e8ebe9; --ink2:#bcc4c1; --muted:#949d9a; --rule:#353836; --soft:#2a2c2a;
  --accent:#6cc3d8; --accent-soft:#18363e; --s1:#3987e5; --s2:#d95926;
  --ok-ink:#62d08a; --bad-ink:#f2928b; color-scheme:dark}
*{box-sizing:border-box}
html,body{background:var(--bg)}
body{color:var(--ink);font:14px/1.5 var(--font);margin:0}
math{font-family:var(--math);font-size:1.08em}
button,input,select,textarea{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.wrap{max-width:1480px;margin:0 auto;padding-block:max(14px,env(safe-area-inset-top,0px)) 40px;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header.top{display:flex;flex-wrap:wrap;gap:6px 20px;align-items:center;justify-content:space-between;margin-bottom:12px}
header.top h1{font-size:19px;margin:0;font-weight:600;letter-spacing:-.01em}
header.top p{margin:0;color:var(--muted);font-size:13px}
.btn{background:var(--surface);border:1px solid var(--rule);padding:5px 11px;cursor:pointer;border-radius:4px}
.btn:hover{border-color:var(--ink2)} .btn.primary{background:var(--accent);border-color:var(--accent);color:var(--surface)}
.btn.small{padding:2px 8px;font-size:12.5px}
.shell{display:grid;grid-template-columns:300px minmax(0,1fr);gap:16px;align-items:start}
nav.side{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:12px;position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto}
.search{width:100%;padding:7px 10px;border:1px solid var(--rule);background:var(--raised);border-radius:4px}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0 6px}
.chip{border:1px solid var(--rule);background:var(--raised);border-radius:999px;padding:1px 9px;font-size:12px;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--surface)}
.t-code{font-weight:600;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);margin:12px 0 2px}
.t-chap{font-weight:600;margin:8px 0 1px;font-size:13px}
.t-sec{color:var(--muted);font-size:12px;margin:5px 0 1px 4px}
.t-obj{display:flex;gap:8px;align-items:center;width:100%;text-align:left;background:none;border:0;border-left:2px solid var(--rule);padding:3px 8px;cursor:pointer;margin-left:4px;border-radius:0 4px 4px 0}
.t-obj:hover{background:var(--raised)} .t-obj[aria-current="true"]{border-left-color:var(--accent);background:var(--accent-soft)}
.t-obj .s{min-width:4.8em;font-size:13px} .t-obj .n{color:var(--muted);font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.t-obj .via{font-size:11px;color:var(--muted)}
.dot{width:9px;height:9px;border-radius:50%;flex:none;display:inline-block}
.dot.good{background:var(--good)} .dot.warn{background:var(--warn)} .dot.crit{background:var(--crit)}
.legend-dots{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:11.5px;color:var(--muted);margin-top:12px;padding-top:8px;border-top:1px solid var(--soft)}
.legend-dots span{display:inline-flex;gap:5px;align-items:center}
.ovw{display:block;width:100%;text-align:left;background:var(--raised);border:1px solid var(--rule);padding:6px 9px;cursor:pointer;margin-top:8px;border-radius:4px}
.ovw[aria-current="true"]{border-color:var(--accent)}
.hit{display:block;width:100%;text-align:left;background:none;border:0;border-bottom:1px solid var(--soft);padding:6px 4px;cursor:pointer}
.hit:hover{background:var(--raised)} .hit .r{color:var(--muted);font-size:12px}
main{min-width:0;display:flex;flex-direction:column;gap:14px}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:14px 16px}
.crumb{color:var(--muted);font-size:12.5px}
.head h2{margin:2px 0 4px;font-size:19px;font-weight:600;line-height:1.3;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.meta{display:flex;flex-wrap:wrap;gap:4px 14px;color:var(--ink2);font-size:13px;align-items:center}
.stat-link{background:none;border:0;padding:0;cursor:pointer;display:inline-flex;gap:6px;align-items:center;color:var(--ink2);font-size:13px;text-decoration:underline;text-decoration-color:var(--rule);text-underline-offset:3px}
[role="tablist"]{display:flex;gap:2px;margin-top:12px;border-bottom:1px solid var(--rule);overflow-x:auto}
[role="tab"]{background:none;border:0;border-bottom:2px solid transparent;padding:6px 12px;cursor:pointer;color:var(--ink2);white-space:nowrap}
[role="tab"][aria-selected="true"]{border-bottom-color:var(--accent);color:var(--ink);font-weight:500}
.calc-grid{display:grid;grid-template-columns:minmax(260px,340px) minmax(0,1fr);gap:14px;align-items:start}
h3{font-size:14px;margin:0 0 8px;font-weight:600}
h4{font-size:12px;margin:14px 0 6px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.inp{padding:7px 0;border-bottom:1px solid var(--soft)}
.inp label{display:flex;justify-content:space-between;gap:8px;align-items:baseline;font-size:13px}
.inp label .nm{color:var(--ink2)}
.ctl{display:flex;gap:6px;margin-top:3px}
.ctl input{flex:1;min-width:0;padding:4px 8px;border:1px solid var(--rule);background:var(--raised);border-radius:4px;font-variant-numeric:tabular-nums}
.ctl select,.ctl .u{min-width:4.2em;padding:4px 6px;border:1px solid var(--rule);background:var(--raised);border-radius:4px;font-size:12.5px}
.ctl .u{border-color:transparent;background:none;color:var(--muted)}
.hint{font-size:11.5px;color:var(--muted);margin-top:2px;display:flex;flex-wrap:wrap;gap:3px 8px;align-items:center}
.tag{border:1px solid var(--rule);border-radius:3px;padding:0 5px;font-size:10.5px;letter-spacing:.03em}
.warn-text{color:var(--bad-ink)} .hint .practice{font-style:italic}
.choice{border:1px dashed var(--rule);background:none;border-radius:3px;padding:0 6px;font-size:11.5px;cursor:pointer;color:var(--ink2)}
.opts{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;font-size:12.5px;color:var(--ink2);padding-bottom:8px;border-bottom:1px solid var(--rule);margin-bottom:6px}
.opts label{display:inline-flex;gap:4px;align-items:center;cursor:pointer}
.st{padding:6px 0 7px;border-bottom:1px solid var(--soft)}
.st .hd{display:flex;justify-content:space-between;gap:12px;align-items:baseline;font-size:13px}
.st .hd .c{color:var(--muted);font-size:12px;text-align:right}
.st .eqs{padding-left:18px;margin-top:2px;overflow-x:auto}
.eq{display:flex;gap:6px;align-items:baseline;margin:2px 0;white-space:nowrap}
.eq .lhs{min-width:3.8em;text-align:right;flex:none}
.eq.res{font-weight:700} .eq.res math{font-weight:700}
.give{background:none;border:0;color:var(--muted);font-size:11.5px;cursor:pointer;text-decoration:underline;text-decoration-color:var(--rule);padding:0}
.verdict{margin:12px 0 4px;padding:9px 12px;border:1.5px solid var(--ink);border-radius:4px;display:flex;gap:6px 20px;flex-wrap:wrap;align-items:baseline}
.verdict b{font-size:15px}
.ok{color:var(--ok-ink);font-weight:700}.bad{color:var(--bad-ink);font-weight:700}
ul.conds{margin:6px 0 0;padding:0;list-style:none;font-size:13px}
ul.conds li{display:flex;gap:8px;padding:2px 0;align-items:baseline}
ul.conds .m{min-width:6.5em;font-size:11.5px;font-weight:600}
details{margin-top:8px} summary{cursor:pointer;color:var(--ink2);font-size:13px}
details ul{margin:6px 0;padding-left:18px;font-size:13px;color:var(--ink2)}
table.cases{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}
table.cases th,table.cases td{border-bottom:1px solid var(--soft);padding:4px 6px;text-align:right;white-space:nowrap}
table.cases th:first-child,table.cases td:first-child{text-align:left}
table.cases th{font-weight:600;border-bottom-color:var(--rule)} table.cases th small{display:block;font-weight:400;color:var(--muted)}
table.cases tr.gov td{background:var(--accent-soft);font-weight:600}
.scroll{overflow-x:auto}
.dl{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;margin-top:4px}
#ask{margin:6px 0 2px} #ask-out{margin-top:6px} #ask-out .ans{margin:4px 0 6px;color:var(--ink2)}
.rb{display:flex;flex-wrap:wrap;gap:6px 12px;margin:6px 0;font-size:12.5px}
.rb label{display:flex;flex-direction:column;gap:2px;color:var(--ink2)} .rb label.ck{flex-direction:row;align-items:center;gap:5px}
.rb input:not([type=checkbox]),.rb select{padding:3px 7px;border:1px solid var(--rule);background:var(--raised);border-radius:4px;min-width:9em}
textarea.yaml{width:100%;min-height:220px;font:12px/1.45 var(--mono);border:1px solid var(--rule);background:var(--raised);padding:8px;border-radius:4px}
pre.code{font:12px/1.5 var(--mono);background:var(--raised);border:1px solid var(--soft);padding:10px 12px;overflow:auto;border-radius:4px;margin:6px 0 12px}
.note{border-left:3px solid var(--rule);padding:4px 0 4px 10px;margin:8px 0}
.note.pitfall{border-left-color:var(--serious)} .note.limitation{border-left-color:var(--warn)} .note.scope{border-left-color:var(--s1)} .note.practice{border-left-color:var(--s2)}
.note .k{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600}
.note .src{font-size:12px;color:var(--muted);margin-top:2px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:8px 0 4px}
.tile{background:var(--raised);border:1px solid var(--soft);border-radius:4px;padding:8px 10px}
.tile .v{font-size:20px;font-weight:600;font-variant-numeric:tabular-nums} .tile .l{font-size:12px;color:var(--muted)}
.muted{color:var(--muted)} .small{font-size:12.5px}
.chartbox{position:relative;margin-top:8px}
.chartbox svg{display:block;width:100%;height:auto;overflow:visible}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--rule);border-radius:4px;padding:5px 8px;font-size:12px;box-shadow:0 2px 6px rgba(0,0,0,.12);white-space:nowrap;display:none;z-index:2}
.tip b{font-variant-numeric:tabular-nums}
.ctrls{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:end;font-size:13px}
.ctrls label{display:flex;flex-direction:column;gap:2px;color:var(--ink2);font-size:12px}
.ctrls input,.ctrls select{padding:4px 7px;border:1px solid var(--rule);background:var(--raised);border-radius:4px;min-width:6em}
.series-key{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;margin-top:8px}
.series-key span{display:inline-flex;gap:6px;align-items:center}
.series-key i{display:inline-block;width:16px;height:2px}
.bars .row{display:grid;grid-template-columns:minmax(120px,240px) minmax(0,1fr);gap:10px;align-items:center;padding:3px 0}
.bars .lab{font-size:12.5px;color:var(--ink2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bars .track{display:flex;align-items:center;gap:2px;min-height:16px}
.bars .seg{height:14px}
.bars .seg:last-of-type{border-radius:0 4px 4px 0}
.bars .n{font-size:12px;color:var(--ink2);margin-left:6px;font-variant-numeric:tabular-nums}
.depmap{overflow-x:auto;margin-top:6px}
.depmap svg{display:block}
.depmap .node{cursor:pointer}
dialog{border:1px solid var(--rule);border-radius:6px;background:var(--surface);color:var(--ink);max-width:min(520px,calc(100vw - 32px));padding:16px}
dialog::backdrop{background:rgba(0,0,0,.35)}
.setrow{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:4px 0;font-size:13px;border-bottom:1px solid var(--soft)}
.setrow select{padding:3px 6px;border:1px solid var(--rule);background:var(--raised);border-radius:4px}
@media (max-width:900px){.shell{grid-template-columns:minmax(0,1fr)} nav.side{position:static;max-height:46vh}
  .calc-grid{grid-template-columns:minmax(0,1fr)}}
</style>
<div class="wrap">
<header class="top">
  <div><h1>Calculation knowledge base</h1><p id="sub"></p></div>
  <button class="btn" id="settings-btn" type="button">Settings</button>
</header>
<div class="shell">
  <nav class="side" aria-label="Codes and calculation objects">
    <input class="search" id="q" type="search" placeholder="Search: concrete shear, V_Rd,c, 6.2.2" aria-label="Search">
    <div id="ask" hidden><button class="btn small" type="button" id="ask-btn">Ask Claude about it</button><div id="ask-out" class="small"></div></div>
    <div class="chips" id="codes"></div>
    <div id="tree"></div>
    <button class="ovw" id="ovw" type="button">Overview of the knowledge base</button>
    <div class="legend-dots"><span><i class="dot good"></i>checked</span><span><i class="dot warn"></i>not yet checked</span><span><i class="dot crit"></i>review needed</span></div>
  </nav>
  <main id="main"></main>
</div>
</div>
<dialog id="settings">
  <h3>Settings</h3>
  <p class="small muted">How numbers are shown here. The calculation itself always runs in N, mm, MPa.</p>
  <div class="setrow"><span>Digits after the decimal point</span><select id="set-dec"></select></div>
  <div class="setrow"><span>Significant digits kept for small values</span><select id="set-sig"></select></div>
  <h4>Units in this calculation</h4>
  <div id="set-units" class="small"></div>
  <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px">
    <button class="btn" id="set-reset" type="button">Reset</button><button class="btn primary" id="set-close" type="button">Done</button>
  </div>
</dialog>
<div class="tip" id="tip"></div>
<script>
"use strict";
const D = /*__DATA__*/;
/*__FUNCTIONS__*/
const STANDALONE = __STANDALONE__;
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem("ckb:" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("ckb:" + k, JSON.stringify(v)); } catch (e) {} }
};

// ---------------------------------------------------------------- style
const S = Object.assign({decimals: 2, minsig: 3, units: {}}, store.get("style", {}));
function digits(v) {
  if (!isFinite(v) || v === 0) return S.decimals;
  const need = S.minsig - 1 - Math.floor(Math.log10(Math.abs(v)));
  return Math.max(S.decimals, Math.min(need, 12));
}
function fmt(v) {
  if (v == null) return "–";
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (!isFinite(v)) return "n/a";
  if (v !== 0 && (Math.abs(v) >= 1e7 || Math.abs(v) < 1e-12)) return v.toExponential(Math.max(S.minsig - 1, 1));
  return v.toFixed(digits(v));
}
function fmtShort(v) {
  let s = fmt(v);
  if (typeof v === "number" && s.includes(".") && !s.includes("e")) s = s.replace(/0+$/, "").replace(/\.$/, "");
  return s;
}
const item = id => D.objects[id] || D.quantities[id];
function unitOf(id) {
  const it = item(id);
  if (!it) return ["-", 1];
  return it.units.find(u => u[0] === S.units[id]) || it.units[0];
}
const shown = (id, v) => typeof v === "number" ? v / unitOf(id)[1] : v;
const ulabel = u => u === "-" ? "" : u;
const symML = id => { const it = item(id); return it ? it.ml : "<mi>" + esc(id) + "</mi>"; };
const symText = id => { const it = item(id); return it ? it.text : id; };
const mathNum = v => {
  const s = typeof v === "number" ? fmt(v) : String(v);
  return s.startsWith("-") ? "<mo>&#x2212;</mo><mn>" + esc(s.slice(1)) + "</mn>" : "<mn>" + esc(s) + "</mn>";
};
const mathUnit = u => u === "-" ? "" : "<mtext>&#x2009;" + esc(u) + "</mtext>";

// ---------------------------------------------------------------- confidence
const CONF = {high: {cls: "good", label: "checked"}, medium: {cls: "warn", label: "not yet checked"}, low: {cls: "crit", label: "review needed"}};
const conf = o => CONF[(o.conf || {}).level] || CONF.medium;
const dot = o => { const c = conf(o); return `<span class="dot ${c.cls}" role="img" aria-label="${c.label}" title="${c.label}"></span>`; };

// ---------------------------------------------------------------- engine (same objects as Python)
function plan(target, given) {
  const fixed = D.objects[target].fixed || {};
  const steps = [], inputs = [], done = {};
  function visit(id, trail) {
    if (done[id]) return;
    if (trail.includes(id)) throw new Error("objects refer to each other in a circle: " + trail.concat(id).join(" -> "));
    for (const p of D.objects[id].params) {
      if (p in fixed) continue;
      if (D.objects[p] && !given.has(p)) visit(p, trail.concat(id));
      else if (!inputs.includes(p)) inputs.push(p);
    }
    done[id] = 1; steps.push(id);
  }
  visit(target, []);
  return {steps, inputs};
}
function evaluate(target, values, given) {
  const {steps, inputs} = plan(target, given);
  const e = Object.assign({}, values, D.objects[target].fixed || {});
  const trace = [];
  for (const id of steps) {
    const v = F[id](e);
    e[id] = v;
    const env = {};
    for (const p of D.objects[id].params) env[p] = e[p];
    trace.push({id, v, env});
  }
  return {value: e[target], trace, env: e, steps, inputs};
}
function derive(s, env, depth) {
  if (s in env) return env[s];
  if (depth > 10) return undefined;
  const o = D.objects[s];
  if (o) {
    const local = Object.assign({}, env);
    for (const p of o.params) { const v = derive(p, local, depth + 1); if (v === undefined) return undefined; local[p] = v; }
    try { return F[s](local); } catch (e) { return undefined; }
  }
  const q = D.quantities[s];
  return q && q.kind === "coefficient" && q.value != null ? q.value : undefined;
}
function checksFor(target, env, given) {
  const out = [], local = Object.assign({}, env);
  for (const id of plan(target, given).steps) {
    (D.objects[id].checks || []).forEach((c, i) => {
      let ok = true;
      for (const s of c.syms) {
        if (!(s in local)) { const v = derive(s, local, 0); if (v === undefined) { ok = false; break; } local[s] = v; }
      }
      let status = "not checked";
      if (ok) { try { status = C[id][i](local) ? "ok" : "violated"; } catch (e) {} }
      out.push({object: id, text: c.text, clause: c.clause, status});
    });
  }
  return out;
}
function defaults(target, given) {
  const out = {};
  for (const p of plan(target, given).inputs) { const q = D.quantities[p]; if (q && q.start != null) out[p] = q.start; }
  return out;
}

// ---------------------------------------------------------------- state
const state = {view: "overview", target: null, tab: "calc", code: store.get("code", "all"), q: ""};
const work = {};      // per object: {values, entered:Set, given:Set, check, show, steps, chart}
function W(id) {
  if (!work[id]) {
    const saved = store.get("work:" + id, null);
    const w = {values: {}, entered: new Set(), given: new Set(), check: null,
               show: {equation: true, substituted: true, result: true}, steps: "all", chart: {}};
    if (saved) {
      w.given = new Set(saved.given || []);
      Object.assign(w.values, saved.values || {});
      w.entered = new Set(Object.keys(saved.values || {}));
      w.check = saved.check == null ? null : saved.check;
      if (saved.show) w.show = saved.show;
      if (saved.steps) w.steps = saved.steps;
    }
    work[id] = w;
  }
  return work[id];
}
function saveWork(id) {
  const w = work[id];
  const vals = {};
  for (const k of w.entered) if (k in w.values) vals[k] = w.values[k];
  store.set("work:" + id, {values: vals, given: [...w.given], check: w.check, show: w.show, steps: w.steps});
}
function valuesFor(id) {
  const w = W(id);
  const v = defaults(id, w.given);
  for (const k of w.entered) if (k in w.values) v[k] = w.values[k];
  return v;
}

// ---------------------------------------------------------------- tree and search
const topicKey = t => String(t || "").split(".").map(x => parseInt(x, 10) || 0);
const cmpTopic = (a, b) => { const x = topicKey(a), y = topicKey(b); for (let i = 0; i < Math.max(x.length, y.length); i++) { const d = (x[i] || 0) - (y[i] || 0); if (d) return d; } return 0; };
function topicTitle(code, tid) {
  const c = D.codes.find(c => c.code === code);
  const t = c && c.topics.find(t => t.id === tid);
  return t ? `${tid} ${t.title}` : tid;
}
function entries(code) {
  const out = [];
  for (const o of Object.values(D.objects)) {
    if (o.code === code) out.push({id: o.id, topic: o.topic, label: o.text, name: o.name, via: null});
    for (const r of o.refs || []) if (r.code === code)
      out.push({id: o.id, topic: r.topic || "", label: o.text, name: o.name, via: `${o.code}, ${r.how || "shared"}`});
  }
  out.sort((a, b) => cmpTopic(a.topic, b.topic) || a.label.localeCompare(b.label));
  return out;
}
function renderCodes() {
  const opts = [["all", "All codes"]].concat(D.codes.map(c => [c.code, c.code]));
  $("#codes").innerHTML = opts.map(([k, l]) => `<button class="chip" type="button" data-code="${esc(k)}" aria-pressed="${state.code === k}">${esc(l)}</button>`).join("");
}
function renderTree() {
  const box = $("#tree");
  if (state.q.trim()) { renderHits(box); return; }
  let h = "";
  const general = Object.values(D.objects).filter(o => !o.code);
  if (general.length && state.code === "all") {
    h += `<div class="t-code">Definitions used by every code</div>` + general.map(o =>
      `<button class="t-obj" type="button" data-id="${esc(o.id)}" aria-current="${state.view === "object" && state.target === o.id}">`
      + `${dot(o)}<span class="s">${esc(o.text)}</span><span class="n">${esc(o.name)}</span></button>`).join("");
  }
  for (const c of D.codes) {
    if (state.code !== "all" && state.code !== c.code) continue;
    h += `<div class="t-code">${esc(c.code)}</div>`;
    let chap = null, sec = null;
    for (const e of entries(c.code)) {
      const ch = e.topic.split(".")[0];
      if (ch !== chap) { chap = ch; sec = null; h += `<div class="t-chap">${esc(topicTitle(c.code, ch))}</div>`; }
      if (e.topic !== ch && e.topic !== sec) { sec = e.topic; h += `<div class="t-sec">${esc(topicTitle(c.code, e.topic))}</div>`; }
      const o = D.objects[e.id];
      h += `<button class="t-obj" type="button" data-id="${esc(e.id)}" aria-current="${state.view === "object" && state.target === e.id}">`
        + `${dot(o)}<span class="s">${esc(e.label)}</span><span class="n">${esc(e.via ? "from " + e.via : e.name)}</span></button>`;
    }
  }
  box.innerHTML = h;
}
// word search: the same index and rules as `python -m ckb search`
const WORD = /[a-z0-9]+(?:\.[0-9]+)*/g;
const words = t => (String(t).toLowerCase().replace(/_/g, " ").match(WORD) || []);
const stem = w => { for (const s of ["ing", "es", "s"]) if (w.length > s.length + 3 && w.endsWith(s)) return w.slice(0, -s.length); return w; };
const symkey = s => String(s).normalize("NFKC").replace("epsilon", "eps").replace(/[\s_.,;:{}\\'’`\-−]+/g, "");
function hitWord(t, vocab) {
  const st = stem(t);
  return vocab.some(w => w === t || w.startsWith(st) || (w.length > 3 && st.startsWith(stem(w)) && st.length - w.length <= 3));
}
const FIELDS = [["name", 3], ["chapter", 2], ["other", 1], ["weak", 0.4]];
function search(q) {
  q = q.trim();
  if (!q) return [];
  const key = symkey(q), tokens = words(q).filter(t => t.length > 1 || /^\d+$/.test(t));
  let hits = [];
  for (const [id, e] of Object.entries(D.index)) {
    const o = D.objects[id];
    if (key && e.keys.includes(key)) { hits.push([100, id, "symbol"]); continue; }
    if (q === (o.ref.match(/cl\. ([^,]+)/) || [])[1]) { hits.push([90, id, "clause"]); continue; }
    if (!tokens.length) continue;
    let score = 0, found = 0, weak = false;
    for (const t of tokens) for (const [f, w] of FIELDS) { if (hitWord(t, e[f].split(" "))) { score += w; found++; weak = weak || f === "weak"; break; } }
    if (!found) continue;
    score = score / tokens.length + (found === tokens.length ? 20 : 5 * found / tokens.length) + 1.5 * e.rank;
    hits.push([score, id, (found === tokens.length ? "all words" : `${found} of ${tokens.length} words`) + (weak ? ", partly in the background" : "")]);
  }
  hits.sort((a, b) => b[0] - a[0] || a[1].localeCompare(b[1]));
  if (hits.length && hits[0][0] >= 90) hits = hits.filter(h => h[0] >= 90);
  else if (hits.length && hits[0][0] >= 20) hits = hits.filter(h => h[0] >= 20);
  return hits.slice(0, 15);
}
function renderHits(box) {
  const hits = search(state.q).filter(h => state.code === "all" || D.objects[h[1]].code === state.code || (D.objects[h[1]].refs || []).some(r => r.code === state.code));
  if (!hits.length) { box.innerHTML = `<p class="small muted">Nothing found for “${esc(state.q)}”. Try fewer words, a symbol (V_Rd,c) or a clause (6.2.2).</p>`; return; }
  box.innerHTML = `<p class="small muted">${hits.length} result${hits.length > 1 ? "s" : ""}</p>` + hits.map(([s, id, why]) => {
    const o = D.objects[id];
    return `<button class="hit" type="button" data-id="${esc(id)}">${dot(o)} <b>${esc(o.text)}</b> ${esc(o.name)}<div class="r">${esc(o.ref)} · ${esc(why)}</div></button>`;
  }).join("");
}

// ---------------------------------------------------------------- page
function open(id, tab) {
  state.view = "object"; state.target = id; state.tab = tab || "calc";
  renderTree(); renderMain();
  try {   // on a phone the tree sits above the page: go to the calculation
    if (window.matchMedia("(max-width: 900px)").matches) $("#main").scrollIntoView({block: "start"});
    else window.scrollTo({top: 0});
  } catch (e) {}
}
function renderMain() {
  $("#ovw").setAttribute("aria-current", String(state.view === "overview"));
  if (state.view !== "object") { renderOverview(); return; }
  const o = D.objects[state.target], c = conf(o);
  const crumb = (o.code ? [o.code] : ["Definition used by every code"]).concat(o.path || []).join(" › ");
  const tabs = [["calc", "Calculate"], ["background", "Design background"], ["chart", "Chart"], ["code", "Code"], ["status", "Status"]];
  $("#main").innerHTML = `<section class="card head"><div class="crumb">${esc(crumb)}</div>
    <h2><math>${o.ml}</math><span>${esc(o.name)}</span></h2>
    <div class="meta"><span>${esc(o.ref)}</span><span>Result in ${esc(o.unit === "-" ? "no unit" : o.unit)}</span>
      <button class="stat-link" type="button" data-tab="status">${dot(o)}${esc(c.label)}</button></div>
    <div role="tablist">${tabs.map(([k, l]) => `<button role="tab" type="button" data-tab="${k}" aria-selected="${state.tab === k}">${l}</button>`).join("")}</div>
  </section><section class="card" id="panel"></section>`;
  ({calc: renderCalc, background: renderBackground, chart: renderChart, code: renderCode, status: renderStatus})[state.tab]();
}

// ---------------------------------------------------------------- Calculate
function renderCalc() {
  const id = state.target, o = D.objects[id], w = W(id);
  $("#panel").innerHTML = `<div class="calc-grid"><div id="inputs"></div><div><div id="sheet"></div><div id="dl"></div><div id="cases"></div></div></div>`;
  renderInputs(); renderSheet(); renderDownloads(); renderCases();
}
function inputRow(p, value, isCheck) {
  const it = item(p), [u] = unitOf(p), q = D.quantities[p];
  const v = shown(p, value);
  const sel = it && it.units.length > 1
    ? `<select data-unit="${esc(p)}" aria-label="unit">${it.units.map(x => `<option ${x[0] === u ? "selected" : ""}>${esc(x[0])}</option>`).join("")}</select>`
    : `<span class="u">${esc(ulabel(u))}</span>`;
  const hint = [];
  const w = W(state.target);
  if (q && q.kind === "coefficient" && q.value != null) {
    const rec = Math.abs((value || 0) - q.value) <= 1e-12 * Math.max(1, Math.abs(q.value));
    hint.push(rec ? `<span class="tag">recommended</span>` : `<span class="tag">recommended ${esc(fmt(shown(p, q.value)))}</span>`);
  }
  if (q && q.ndp) hint.push(`<span class="tag" title="Nationally Determined Parameter: check the National Annex">NDP</span>`);
  if (q && q.choices && q.choices.length) for (const ch of q.choices)
    hint.push(`<button type="button" class="choice" data-set="${esc(p)}" data-v="${ch.value}" title="${esc(ch.label)}">${esc(fmt(shown(p, ch.value)))} ${esc(ch.label)}</button>`);
  if (D.objects[p] && w.given.has(p)) hint.push(`<button type="button" class="give" data-ungive="${esc(p)}">calculate instead</button>`);
  if (q && q.ref) hint.push(`<span>${esc(q.ref)}</span>`);
  const tips = new Set();
  for (const s of plan(state.target, w.given).steps) for (const b of D.objects[s].background || [])
    if (b.kind === "practice" && b.about === p) tips.add(b.text.split(": ")[0]);
  for (const t of tips) hint.push(`<span class="practice">${esc(t)}</span>`);
  if (q && q.range && typeof value === "number" && (value < q.range[0] - 1e-9 || value > q.range[1] + 1e-9))
    hint.push(`<span class="warn-text">outside the usual range ${esc(fmt(shown(p, q.range[0])))} to ${esc(fmt(shown(p, q.range[1])))} ${esc(ulabel(u))}</span>`);
  return `<div class="inp"><label for="in-${esc(p)}"><span class="nm">${esc(it ? it.name : p)}${isCheck ? " (to check against)" : ""}</span><math>${symML(p)}</math></label>
    <div class="ctl"><input id="in-${esc(p)}" data-in="${esc(p)}" inputmode="decimal" autocomplete="off" value="${value == null ? "" : esc(fmtShort(v))}">${sel}</div>
    ${hint.length ? `<div class="hint">${hint.join("")}</div>` : ""}</div>`;
}
function renderInputs() {
  const id = state.target, o = D.objects[id], w = W(id);
  const vals = valuesFor(id);
  const {inputs} = plan(id, w.given);
  let h = `<h3>Input</h3>`;
  h += inputs.map(p => inputRow(p, vals[p], false)).join("");
  if (o.check) h += inputRow(o.check, w.check, true);
  const fixed = Object.entries(o.fixed || {});
  if (fixed.length) h += `<p class="small muted">${fixed.map(([k, v]) => `<math>${symML(k)}<mo>=</mo>${mathNum(v)}</math>`).join(", ")} fixed by ${esc(o.code)}.</p>`;
  h += `<div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap"><button class="btn small" type="button" id="reset">Reset inputs</button></div>`;
  $("#inputs").innerHTML = h;
  refreshInputHints();
}
function refreshInputHints() {}
function renderSheet() {
  const id = state.target, o = D.objects[id], w = W(id);
  let r;
  try { r = evaluate(id, valuesFor(id), w.given); }
  catch (e) { $("#sheet").innerHTML = `<p class="bad">${esc(e.message)}</p>`; return; }
  const sh = w.show;
  let h = `<div class="opts"><span>Show</span>`
    + [["equation", "Equation"], ["substituted", "Substituted values"], ["result", "Result"]].map(([k, l]) =>
      `<label><input type="checkbox" data-show="${k}" ${sh[k] ? "checked" : ""}>${l}</label>`).join("")
    + `<label><input type="checkbox" id="only-result" ${w.steps === "result" ? "checked" : ""}>Final step only</label></div>`;
  const lines = w.steps === "result" ? r.trace.filter(t => t.id === id) : r.trace;
  for (const t of lines) {
    const so = D.objects[t.id], [u] = unitOf(t.id), eqs = [];
    const lhs = () => eqs.length ? "" : `<math>${so.ml}</math>`;
    if (sh.equation) eqs.push(`<div class="eq"><span class="lhs">${lhs()}</span><math displaystyle="true"><mo>=</mo>${so.mlF}</math></div>`);
    if (sh.substituted && so.params.length) eqs.push(`<div class="eq sub" data-env="${esc(JSON.stringify(t.env))}"><span class="lhs">${lhs()}</span><math displaystyle="true"><mo>=</mo>${so.mlS}</math></div>`);
    if (sh.result || !eqs.length) eqs.push(`<div class="eq res"><span class="lhs">${lhs()}</span><math><mo>=</mo>${mathNum(shown(t.id, t.v))}${mathUnit(u)}</math></div>`);
    const ref = so.code === o.code ? so.ref.replace(o.code + " ", "") : so.ref;
    const give = t.id !== id ? ` · <button class="give" type="button" data-give="${esc(t.id)}">enter directly</button>` : "";
    h += `<div class="st"><div class="hd"><span>${esc(so.name)}</span><span class="c">${esc(ref)}${give}</span></div><div class="eqs">${eqs.join("")}</div></div>`;
  }
  const [ut] = unitOf(id);
  if (o.check && w.check != null && typeof r.value === "number" && r.value !== 0) {
    const res = o.sense === "resistance";
    const eta = res ? w.check / r.value : r.value / w.check, ok = eta <= 1;
    const [uc] = unitOf(o.check);
    h += `<div class="verdict"><span><math>${o.ml}<mo>=</mo>${mathNum(shown(id, r.value))}${mathUnit(ut)}</math></span>
      <span><math>${symML(o.check)}<mo>=</mo>${mathNum(shown(o.check, w.check))}${mathUnit(uc)}</math></span>
      <span><math><mi>η</mi><mo>=</mo>${res ? symML(o.check) + "<mo>/</mo>" + o.ml : o.ml + "<mo>/</mo>" + symML(o.check)}</math> = <b>${eta.toFixed(2)}</b> ${ok ? "≤" : ">"} 1.00</span>
      <span class="${ok ? "ok" : "bad"}">${ok ? "OK" : "NOT OK"}</span></div>`;
  } else {
    h += `<div class="verdict"><span><math>${o.ml}<mo>=</mo>${mathNum(shown(id, r.value))}${mathUnit(ut)}</math></span>`
      + (o.check ? `<span class="small muted">Enter <math>${symML(o.check)}</math> to check against it.</span>` : "") + `</div>`;
  }
  const checks = checksFor(id, r.env, w.given);
  if (checks.length) h += `<ul class="conds">` + checks.map(c => {
    const m = {ok: ["met", "ok"], violated: ["NOT MET", "bad"], "not checked": ["to be checked", ""]}[c.status];
    return `<li><span class="m ${m[1]}">${m[0]}</span><span>${esc(c.text)} <span class="muted">(${esc(c.clause)})</span></span></li>`;
  }).join("") + `</ul>`;
  const lim = [];
  for (const s of r.steps) for (const b of D.objects[s].background || []) if (b.kind === "scope" || b.kind === "limitation") lim.push(`<li><b>${esc(D.objects[s].text)}</b>: ${esc(b.text)}</li>`);
  if (lim.length) h += `<details><summary>Scope and limitations of the expressions used (${lim.length})</summary><ul>${lim.join("")}</ul></details>`;
  h += `<p class="small muted" style="margin-top:10px">Substituted values are in N, mm and MPa. Version ${esc(o.version)}.</p>`;
  $("#sheet").innerHTML = h;
  // fill the substituted lines
  for (const el of document.querySelectorAll("#sheet .eq.sub")) {
    const env = JSON.parse(el.dataset.env);
    for (const sl of el.querySelectorAll("mn.slot")) {
      const v = env[sl.dataset.s];
      const s = typeof v === "number" ? fmtShort(v) : String(v);
      sl.textContent = s.startsWith("-") ? "(−" + s.slice(1) + ")" : s;
    }
  }
}

// cases: the same calculation for several sets of inputs; the governing one is highlighted
function cases() { return store.get("cases:" + state.target, []); }
function setCases(c) { store.set("cases:" + state.target, c); }
function caseResult(cs) {
  const id = state.target, o = D.objects[id];
  const v = Object.assign(defaults(id, new Set(cs.given || [])), cs.values);
  try {
    const r = evaluate(id, v, new Set(cs.given || []));
    let eta = null;
    if (o.check && cs.check != null && typeof r.value === "number" && r.value) eta = o.sense === "resistance" ? cs.check / r.value : r.value / cs.check;
    return {r, eta};
  } catch (e) { return {error: e.message}; }
}
function renderCases() {
  const id = state.target, o = D.objects[id], list = cases();
  let h = `<h4>Cases</h4><p class="small muted">Add the current inputs as a case to compare several members. The governing case is highlighted; a case opens again when you click its name.</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn small" type="button" id="add-case">Add current inputs as a case</button>
    <button class="btn small" type="button" id="tpl">Build a report${list.length ? ` (${list.length} case${list.length > 1 ? "s" : ""})` : ""}</button>
    ${list.length ? `<button class="btn small" type="button" id="clear-cases">Remove all cases</button>` : ""}</div>`;
  if (list.length) {
    const res = list.map(caseResult);
    const keys = [];
    for (const c of list) for (const k of Object.keys(c.values)) if (!keys.includes(k) && k !== o.check) keys.push(k);
    let gov = -1, best = null;
    res.forEach((x, i) => {
      if (x.error) return;
      const m = x.eta != null ? x.eta : (o.sense === "resistance" ? -x.r.value : x.r.value);
      if (best == null || m > best) { best = m; gov = i; }
    });
    const head = keys.map(k => `<th><math>${symML(k)}</math><small>${esc(ulabel(unitOf(k)[0]))}</small></th>`).join("");
    h += `<div class="scroll"><table class="cases"><tr><th>Case</th>${head}<th><math>${o.ml}</math><small>${esc(ulabel(unitOf(id)[0]))}</small></th>`
      + (o.check ? `<th><math>${symML(o.check)}</math><small>${esc(ulabel(unitOf(o.check)[0]))}</small></th><th>η</th><th></th>` : "") + `<th></th></tr>`;
    list.forEach((c, i) => {
      const x = res[i];
      const cells = keys.map(k => `<td>${k in c.values ? esc(fmt(shown(k, c.values[k]))) : "–"}</td>`).join("");
      const val = x.error ? `<td class="bad">${esc(x.error)}</td>` : `<td>${esc(fmt(shown(id, x.r.value)))}</td>`;
      const chk = o.check ? `<td>${c.check == null ? "–" : esc(fmt(shown(o.check, c.check)))}</td><td>${x.eta == null ? "–" : x.eta.toFixed(2)}</td><td>${x.eta == null ? "" : (x.eta <= 1 ? '<span class="ok">OK</span>' : '<span class="bad">NOT OK</span>')}</td>` : "";
      h += `<tr class="${i === gov && list.length > 1 ? "gov" : ""}"><td><button class="give" type="button" data-load="${i}">${esc(c.name)}</button></td>${cells}${val}${chk}<td><button class="give" type="button" data-del="${i}" aria-label="remove ${esc(c.name)}">remove</button></td></tr>`;
    });
    h += `</table></div>`;
  }
  h += `<div id="tpl-box"></div>`;
  $("#cases").innerHTML = h;
}
function yamlNum(id, v) {
  const x = +(v / item(id).units[0][1]).toPrecision(8);
  return Number.isInteger(x) || Math.abs(x) >= 1e-4 ? String(x) : x.toExponential(6);   // YAML reads 1.0e-07, not 1e-7
}
function templateYAML() {
  const id = state.target, o = D.objects[id], w = W(id);
  let list = cases();
  if (!list.length) list = [currentCase("Case 1")];
  const rb = reportOpts();
  const q = v => JSON.stringify(String(v || ""));
  const L = [`# Report template for ${o.text} (${o.ref}).`, `# Save as ${id}_report.yaml and run:`, `#   python -m ckb report --template ${id}_report.yaml --pdf --docx`,
    `title: ${q(rb.title)}`, `project: ${q(rb.project)}`, `number: ${q(rb.number)}`, `made_by: ${q(rb.made_by)}`, `checked_by: ${q(rb.checked_by)}`,
    `style:`, `  decimals: ${S.decimals}`, `  min_significant: ${S.minsig}`];
  const units = Object.entries(S.units).filter(([k]) => item(k));
  L.push(`  units: {${units.map(([k, u]) => `${k}: ${u}`).join(", ")}}`);
  L.push(`cases:          # values in the usual units: ${[...new Set(list.flatMap(c => Object.keys(c.values)))].map(k => `${k} [${item(k) ? item(k).units[0][0] : ""}]`).join(", ")}`);
  for (const c of list) {
    const cells = [`case: ${JSON.stringify(c.name)}`].concat(Object.entries(c.values).map(([k, v]) => `${k}: ${yamlNum(k, v)}`));
    if (o.check && c.check != null) cells.push(`${o.check}: ${yamlNum(o.check, c.check)}`);
    L.push(`  - {${cells.join(", ")}}`);
  }
  const show = Object.keys(w.show).filter(k => w.show[k]);
  const remarks = Object.entries(rb.remarks).filter(([, v]) => v.trim());
  L.push(`blocks:`);
  if (rb.heading) L.push(`  - heading: ${q(rb.heading)}`);
  if (rb.text) L.push(`  - text: ${q(rb.text)}`);
  if (rb.calc) L.push(`  - calc: ${id}`, `    case: governing          # governing | first | a case name`,
    `    show: [${show.join(", ")}]`, `    steps: ${w.steps === "result" ? "result" : "all"}                # all | result | [k, rho_l, ...]`,
    `    remarks: {${remarks.map(([k, v]) => `${k}: ${q(v)}`).join(", ")}}`, `    limitations: ${rb.limitations ? "true" : "false"}`);
  if (rb.table && list.length > 1) L.push(`  - table: ${id}`, `    sort: ${o.check ? "utilisation desc" : ""}`);
  if (rb.chart && rb.x) L.push(`  - chart: ${id}`, `    x: ${rb.x}`);
  return L.join("\n") + "\n";
}
function reportOpts() {
  const id = state.target, o = D.objects[id], w = W(id);
  if (!w.report) {
    const x = plan(id, w.given).inputs.find(p => D.quantities[p] && D.quantities[p].kind === "input") || "";
    w.report = {title: o.name, project: "", number: "", made_by: "", checked_by: "", heading: o.name, text: "",
                calc: true, table: true, chart: true, limitations: false, x, remarks: {}};
  }
  return w.report;
}
function renderBuilder() {
  const id = state.target, w = W(id), rb = reportOpts(), {inputs} = plan(id, w.given);
  const fld = (k, l) => `<label>${l}<input data-rb="${k}" value="${esc(rb[k])}"></label>`;
  const chk = (k, l) => `<label class="ck"><input type="checkbox" data-rb="${k}" ${rb[k] ? "checked" : ""}>${l}</label>`;
  const xs = inputs.filter(p => D.quantities[p] && D.quantities[p].kind === "input");
  $("#tpl-box").innerHTML = `<h4>Report</h4><p class="small muted">Choose what the report shows; the template below follows. Save it as a file and run the command in its first lines (or use the Excel form: <code>python -m ckb report-template ${esc(id)} -o report.xlsx</code>). What is shown per step follows the Show options above the calculation; decimals and units follow Settings.</p>
    <div class="rb">${fld("title", "Title")}${fld("project", "Project")}${fld("number", "Calc. no.")}${fld("made_by", "Made by")}${fld("checked_by", "Checked by")}${fld("heading", "Heading")}${fld("text", "Text under the heading")}</div>
    <div class="rb">${chk("calc", "Calculation of the governing case")}${chk("limitations", "Scope and limitations")}${chk("table", "Summary table of all cases")}${chk("chart", "Chart against")}
      <select data-rb="x">${xs.map(p => `<option value="${esc(p)}" ${p === rb.x ? "selected" : ""}>${esc(symText(p))}</option>`).join("")}</select></div>
    <details><summary>Remarks beside the inputs</summary><div class="rb">${inputs.map(p => `<label>${esc(symText(p))}<input data-rem="${esc(p)}" value="${esc(rb.remarks[p] || "")}"></label>`).join("")}</div></details>
    <textarea class="yaml" id="yaml" spellcheck="false" readonly>${esc(templateYAML())}</textarea><button class="btn small" type="button" id="copy">Copy</button> <span id="copied" class="small muted"></span>`;
}
function currentCase(name) {
  const id = state.target, w = W(id), vals = valuesFor(id), {inputs} = plan(id, w.given), values = {};
  for (const p of inputs) {
    const q = D.quantities[p];
    if (w.entered.has(p) || !(q && q.kind === "coefficient")) values[p] = vals[p];
  }
  return {name, values, given: [...w.given], check: w.check};
}


// ---------------------------------------------------------------- take it with you: downloads
// Excel calculators and Mathcad worksheets are embedded in the page (built by `python -m ckb share`),
// so nobody needs Python. The Excel file gets the inputs on the page; the calculation page is built here.
let ZIP = null;
function loadZip() {
  if (window.JSZip) return Promise.resolve(window.JSZip);
  if (ZIP) return ZIP;
  ZIP = new Promise(res => {
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
    const t = setTimeout(() => res(null), 8000);
    s.onload = () => { clearTimeout(t); res(window.JSZip || null); };
    s.onerror = () => { clearTimeout(t); res(null); };
    document.head.appendChild(s);
  });
  return ZIP;
}
const b64bytes = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
async function claudeCap(name) {
  try { return window.claude && window.claude.use ? await window.claude.use(name) : null; } catch (e) { return null; }
}
async function saveFile(filename, data, mime) {
  const dl = await claudeCap("downloads");             // inside claude.ai: the viewer confirms each file
  if (dl) {
    try { await dl.save({filename, data: data instanceof Uint8Array ? new Blob([data], {type: mime}) : data}); return ""; }
    catch (e) { return e && e.code === "declined" ? "" : `Not saved (${(e && e.code) || "error"}).`; }
  }
  const blob = data instanceof Blob ? data : new Blob([data], {type: mime});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
  return "";
}
function renderDownloads() {
  const id = state.target, f = D.files && D.files[id];
  $("#dl").innerHTML = `<h4>Take it with you</h4><div class="dl">`
    + (f ? `<button class="btn small" type="button" id="dl-xlsx">Excel calculator</button><button class="btn small" type="button" id="dl-mcdx">Mathcad Prime worksheet</button>` : "")
    + `<button class="btn small" type="button" id="dl-html">Calculation page (print to PDF)</button></div>
    <p class="small muted" id="dl-msg">${f ? "The Excel file carries the inputs above and live formulas; the Mathcad worksheet opens with example inputs. " : `This copy was built without the Excel and Mathcad files: they are in the workshop package (python -m ckb share), or run python -m ckb excel ${esc(id)}. `}The calculation page is this calculation as shown, ready to print. Every file carries version ${esc(D.objects[id].version)}.</p>`;
}
async function excelBytes(id) {
  const f = D.files[id], w = W(id);
  const bytes = b64bytes(f.xlsx);
  if (w.given.size) return [bytes, "with example inputs: a value entered directly is not carried into Excel"];
  const Z = await loadZip();
  if (!Z) return [bytes, "with example inputs (the zip library did not load); change them in Excel"];
  const zip = await Z.loadAsync(bytes), path = "xl/worksheets/sheet1.xml";
  let xml = await zip.file(path).async("string");
  const put = (cell, v) => {
    const re = new RegExp('<c r="' + cell + '"([^>]*?)(?:/>|>[\\s\\S]*?</c>)');
    xml = xml.replace(re, (m, a) => `<c r="${cell}"${a.replace(/\s*t="[^"]*"/, "")} t="n"><v>${v}</v></c>`);
  };
  const vals = valuesFor(id);
  for (const [sid, cell] of Object.entries(f.cells)) {
    if (!D.objects[sid] && typeof vals[sid] === "number") put(cell, +(vals[sid] / item(sid).units[0][1]).toPrecision(12));
  }
  const chk = D.objects[id].check;
  if (f.check && chk && w.check != null) put(f.check, +(w.check / item(chk).units[0][1]).toPrecision(12));
  zip.file(path, xml);
  return [await zip.generateAsync({type: "uint8array", compression: "DEFLATE"}), "with the inputs on the page"];
}
async function mathcadFile(id) {
  const bytes = b64bytes(D.files[id].mcdx);
  if (!(await claudeCap("downloads"))) return [`${id}.mcdx`, bytes, "application/octet-stream"];
  const Z = await loadZip();                 // claude.ai saves .zip, not .mcdx: the worksheet goes in a zip
  if (!Z) return [null, null, null];
  const zip = new Z();
  zip.file(`${id}.mcdx`, bytes);
  return [`${id}_mathcad.zip`, await zip.generateAsync({type: "uint8array", compression: "DEFLATE"}), "application/zip"];
}
const REPORT_CSS = `body{margin:0;background:#e9edeb;color:#16211f;font:13px/1.45 "IBM Plex Sans","Segoe UI",Arial,sans-serif}
.sheet{background:#fff;max-width:210mm;margin:16px auto;padding:14mm 15mm 16mm;box-shadow:0 1px 4px rgba(0,0,0,.18)}
math{font-family:"Cambria Math","STIX Two Math","Latin Modern Math",math;font-size:1.06em}
table.tb{width:100%;border-collapse:collapse;margin-bottom:6mm;font-size:11.5px} table.tb td{border:1px solid #16211f;padding:3px 6px;width:33%}
table.tb small{display:block;color:#5b6966;font-size:9px;letter-spacing:.05em;text-transform:uppercase}
h1{font-size:18px;margin:0 0 3mm} h3{font-size:13px;margin:4mm 0 1mm} .ref,.muted,.small{color:#5b6966;font-size:11.5px}
.grp,h4{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:#5b6966;margin:3mm 0 1mm;font-weight:600}
table.in{width:100%;border-collapse:collapse} table.in td{padding:3px 6px 3px 0;border-bottom:1px solid #eef2f0;vertical-align:baseline}
table.in td.c{color:#5b6966;font-size:11px;text-align:right} table.in td.r{font-style:italic;color:#5b6966;font-size:11px}
.st{padding:4px 0 5px;border-bottom:1px solid #eef2f0;break-inside:avoid} .st .hd{display:flex;justify-content:space-between;gap:12px}
.st .hd .c{color:#5b6966;font-size:11px} .st .eqs{padding-left:7mm} .eq{display:flex;gap:6px;align-items:baseline;margin:1px 0}
.eq .lhs{min-width:3.6em;text-align:right} .eq.res,.eq.res math{font-weight:700}
.verdict{margin:3mm 0 1mm;padding:6px 10px;border:1.5px solid #16211f;display:flex;gap:6px 18px;flex-wrap:wrap;align-items:baseline;break-inside:avoid}
.ok{color:#0a7d34;font-weight:700} .bad{color:#c0302f;font-weight:700}
ul.conds{list-style:none;padding:0;margin:2mm 0;font-size:11.5px} ul.conds li{display:flex;gap:8px} ul.conds .m{min-width:6.5em;font-weight:600}
details summary{font-size:11.5px;color:#5b6966} details ul{font-size:11.5px;color:#5b6966}
.foot{margin-top:8mm;color:#5b6966;font-size:9.5px;display:flex;justify-content:space-between;gap:12px}
@media print{body{background:#fff}.sheet{box-shadow:none;margin:0;max-width:none;padding:0}@page{size:A4;margin:15mm 15mm 17mm}}`;
function reportHTML(id) {
  const o = D.objects[id], w = W(id), rb = reportOpts(), vals = valuesFor(id), {inputs, steps} = plan(id, w.given);
  const sheet = $("#sheet").cloneNode(true);
  sheet.querySelectorAll(".opts, .give").forEach(e => e.remove());
  sheet.querySelectorAll("details").forEach(d => d.setAttribute("open", ""));
  const rows = inputs.map(p => {
    const q = D.quantities[p], it = item(p);
    return `<tr><td>${esc(it ? it.name : p)}</td><td><math>${symML(p)}<mo>=</mo>${mathNum(shown(p, vals[p]))}${mathUnit(unitOf(p)[0])}</math></td>`
      + `<td class="c">${esc(q && q.ref || "")}</td><td class="r">${esc(rb.remarks[p] || "")}</td></tr>`;
  }).join("");
  const date = new Date().toISOString().slice(0, 10);
  const versions = steps.map(s => `ckb ${s} ${D.objects[s].version}`).join(" · ");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">`
    + `<title>${esc(rb.title || o.name)}</title><style>${REPORT_CSS}</style></head><body><div class="sheet">`
    + `<table class="tb"><tr><td><small>Project</small>${esc(rb.project)}&nbsp;</td><td><small>Subject</small>${esc(rb.title || o.name)}</td><td><small>Calc. no.</small>${esc(rb.number)}&nbsp;</td></tr>`
    + `<tr><td><small>Made by / date</small>${esc(rb.made_by)} ${date}</td><td><small>Checked by / date</small>${esc(rb.checked_by)}&nbsp;</td><td><small>Approved by / date</small>&nbsp;</td></tr></table>`
    + `<h1>${esc(rb.title || o.name)}</h1><h3><math>${o.ml}</math> ${esc(o.name)}</h3><p class="ref">${esc(o.ref)}</p>`
    + `<div class="grp">Input</div><table class="in">${rows}</table><div class="grp">Calculation</div>${sheet.innerHTML}`
    + `<div class="foot"><span>${esc(o.code)}; recommended values unless stated. Substituted values are in N, mm and MPa. Print with your browser (Ctrl+P) to make a PDF.</span><span>${esc(versions)}</span></div>`
    + `</div></body></html>`;
}
async function download(kind) {
  const id = state.target, msg = $("#dl-msg");
  msg.textContent = "Preparing…";
  try {
    let text = "";
    if (kind === "xlsx") {
      const [bytes, how] = await excelBytes(id);
      text = (await saveFile(`${id}_calculator.xlsx`, bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")) || `Excel calculator ${how}.`;
    } else if (kind === "mcdx") {
      const [name, bytes, mime] = await mathcadFile(id);
      text = name ? ((await saveFile(name, bytes, mime)) || "Mathcad Prime worksheet with example inputs" + (name.endsWith(".zip") ? " (unzip it first)." : ".")) : "The zip library did not load; try again later.";
    } else {
      text = (await saveFile(`${id}_calculation.html`, reportHTML(id), "text/html")) || "Open the page in your browser and print it to PDF.";
    }
    msg.textContent = text;
  } catch (e) { msg.textContent = "Could not prepare the file: " + (e && e.message || e); }
}

// ---------------------------------------------------------------- ask Claude (claude.ai only)
let SAMPLE = null;
(async () => { SAMPLE = await claudeCap("sample"); if (SAMPLE) $("#ask").hidden = false; })();
async function ask() {
  const q = $("#q").value.trim(), out = $("#ask-out");
  if (!q) { out.textContent = "Type a question in the search box first, e.g. “how do I check punching at an edge column?”"; return; }
  const cat = Object.values(D.objects).map(o => `${o.id} | ${o.text} | ${o.name} | ${o.ref} | ${(o.path || []).slice(-1)[0] || ""}`).join("\n");
  const prompt = `You are the search assistant of a knowledge base of structural design calculation objects (Eurocodes 2, 3 and 4). `
    + `The catalogue lists every object as: id | symbol | name | code and clause | chapter.\n\nQuestion from an engineer: ${q}\n\n`
    + `Answer with JSON only: {"answer": "two or three sentences: which objects to use and in what order, with clauses; say plainly what the knowledge base does not cover", `
    + `"objects": [{"id": "an id from the catalogue", "why": "a few words"}]} with at most six objects, most relevant first, using only ids from the catalogue.\n\nCatalogue:\n${cat}`;
  out.textContent = "Thinking…";
  $("#ask-btn").disabled = true;
  try {
    const r = await SAMPLE.json(prompt, {modelTier: "quick"});
    const hits = (r && r.objects || []).filter(h => D.objects[h.id]);
    out.innerHTML = `<p class="ans">${esc(r && r.answer || "")}</p>` + hits.map(h => {
      const o = D.objects[h.id];
      return `<button class="hit" type="button" data-id="${esc(o.id)}">${dot(o)} <b>${esc(o.text)}</b> ${esc(o.name)}<div class="r">${esc(o.ref)} · ${esc(h.why || "")}</div></button>`;
    }).join("") + `<p class="muted">Answered by Claude from the object list; check the clause before you rely on it.</p>`;
  } catch (e) {
    if (e && e.code === "not_granted") { $("#ask").hidden = true; return; }
    out.textContent = e && e.code === "rate_limited" ? "Too many questions at once; try again in a moment." : "No answer this time.";
  } finally { $("#ask-btn").disabled = false; }
}

// ---------------------------------------------------------------- Design background
const KINDS = [["scope", "Scope"], ["limitation", "Limitations"], ["pitfall", "Pitfalls"], ["guidance", "Guidance"], ["practice", "From practice"], ["history", "History"]];
function noteHTML(b) {
  let refs = (b.refs || []).map(r => `<span title="${esc(r.text || D.references[r.id] || "")}">${esc(r.id)}${r.at ? " " + esc(r.at) : ""}</span>`).join("; ");
  if (b.kind === "practice") refs = b.from === "engineer" ? "an engineer's answer to a question from the distillation" : "how the source calculations use it";
  return `<div class="note ${esc(b.kind)}"><div>${esc(b.text)}</div>${refs ? `<div class="src">${refs}</div>` : ""}</div>`;
}
function renderBackground() {
  const id = state.target, o = D.objects[id];
  let h = "";
  if (o.checks.length) h += `<h4>Conditions of application</h4><ul class="conds">${o.checks.map(c => `<li><span>${esc(c.text)} <span class="muted">(${esc(c.clause)})</span></span></li>`).join("")}</ul>`;
  for (const [k, l] of KINDS) {
    const notes = (o.background || []).filter(b => b.kind === k);
    if (notes.length) h += `<h4>${l}</h4>` + notes.map(noteHTML).join("");
  }
  if (o.alternatives.length) h += `<h4>Alternatives the code permits</h4>` + o.alternatives.map(a => `<div class="note"><math><mrow>${o.ml}<mo>=</mo>${a.ml}</mrow></math><div class="src">${esc(a.when)}</div></div>`).join("");
  const params = plan(id, new Set()).inputs.filter(p => D.quantities[p] && (D.quantities[p].background || []).length);
  if (params.length) h += `<h4>Parameters</h4>` + params.map(p => `<div><b><math>${symML(p)}</math> ${esc(D.quantities[p].name)}</b>${D.quantities[p].background.map(noteHTML).join("")}</div>`).join("");
  const shared = (o.refs || []);
  const users = Object.values(D.objects).filter(x => x.params.includes(id));
  h += `<h4>Where it is used</h4><ul class="small">`;
  h += `<li>Defined in ${esc(o.ref)}.</li>`;
  for (const r of shared) h += `<li>Also ${esc(r.code)} cl. ${esc(r.clause || "")}${r.symbol ? ` (written ${esc(r.symbol)})` : ""}: ${esc(r.how || "")}. Stored once; that code's values are applied when it is used there.</li>`;
  if (users.length) h += `<li>Used by ${users.map(u => `<button class="give" type="button" data-open="${esc(u.id)}">${esc(u.text)}</button>`).join(", ")}.</li>`;
  h += `</ul>`;
  h += `<h4>Dependency map</h4><p class="small muted">What ${esc(o.text)} is calculated from. Click an object to open it.</p><div class="depmap" id="depmap"></div>`;
  if (!h.includes("note")) h = `<p class="small muted">No design background recorded for this object yet.</p>` + h;
  $("#panel").innerHTML = h;
  drawDepMap();
}
function drawDepMap() {
  const id = state.target, {steps, inputs} = plan(id, new Set());
  const depth = {};
  for (const p of inputs) depth[p] = 0;
  for (const s of steps) depth[s] = 1 + Math.max(0, ...D.objects[s].params.filter(p => p in depth).map(p => depth[p]));
  const cols = {};
  for (const n of inputs.concat(steps)) (cols[depth[n]] = cols[depth[n]] || []).push(n);
  const nCols = Math.max(...Object.keys(cols).map(Number)) + 1, rows = Math.max(...Object.values(cols).map(c => c.length));
  const cw = 132, bw = 100, bh = 26, rh = 34, W = nCols * cw, H = rows * rh + 8, pos = {};
  for (const [c, list] of Object.entries(cols)) list.forEach((n, i) => { pos[n] = [c * cw + 4, 4 + i * rh + (rows - list.length) * rh / 2]; });
  let s = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Dependency map of ${esc(D.objects[id].text)}">`;
  for (const t of steps) for (const p of D.objects[t].params) {
    if (!(p in pos)) continue;
    const [x1, y1] = [pos[p][0] + bw, pos[p][1] + bh / 2], [x2, y2] = [pos[t][0], pos[t][1] + bh / 2], mx = (x1 + x2) / 2;
    s += `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" fill="none" style="stroke:var(--rule)" stroke-width="1.5"/>`;
  }
  for (const [n, [x, y]] of Object.entries(pos)) {
    const o = D.objects[n], isObj = !!o, cur = n === id;
    const fill = cur ? "var(--accent-soft)" : (isObj ? "var(--surface)" : "var(--raised)");
    s += `<g class="${isObj ? "node" : ""}" ${isObj ? `data-open="${esc(n)}" tabindex="0" role="button"` : ""}><title>${esc((item(n) || {}).name || n)}</title>`
      + `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="4" style="fill:${fill};stroke:${cur ? "var(--accent)" : "var(--rule)"}" stroke-width="1"/>`
      + (isObj ? `<circle cx="${x + 11}" cy="${y + bh / 2}" r="4" style="fill:var(--${conf(o).cls === "good" ? "good" : conf(o).cls === "warn" ? "warn" : "crit"})"/>` : "")
      + `<text x="${x + (isObj ? 21 : 9)}" y="${y + bh / 2 + 4}" font-size="12" style="fill:var(--ink)">${esc(symText(n))}</text></g>`;
  }
  $("#depmap").innerHTML = s + "</svg>";
}

// ---------------------------------------------------------------- Chart (parameter study)
function renderChart() {
  const id = state.target, o = D.objects[id], w = W(id);
  const {inputs, steps} = plan(id, w.given);
  const nums = inputs.filter(p => item(p));
  const c = w.chart;
  if (!c.x || !nums.includes(c.x)) c.x = nums.find(p => D.quantities[p] && D.quantities[p].kind === "input") || nums[0];
  const second = steps.filter(s => s !== id && D.objects[s].units[0][1] === o.units[0][1] && D.objects[s].unit === o.unit);
  if (c.y2 && !second.includes(c.y2)) c.y2 = "";
  const vals = valuesFor(id), x0 = vals[c.x], q = D.quantities[c.x];
  let lo = c.lo, hi = c.hi;
  if (lo == null || hi == null) {
    if (q && q.range) { lo = q.range[0]; hi = q.range[1]; }
    else { lo = 0.5 * (x0 || 1); hi = 1.5 * (x0 || 1); }
    if (typeof x0 === "number") { lo = Math.min(lo, x0); hi = Math.max(hi, x0); }
  }
  const ux = unitOf(c.x)[0];
  $("#panel").innerHTML = `<div class="ctrls">
    <label>Vary<select id="cx">${nums.map(p => `<option value="${esc(p)}" ${p === c.x ? "selected" : ""}>${esc(symText(p))} – ${esc(item(p).name)}</option>`).join("")}</select></label>
    <label>from [${esc(ulabel(ux))}]<input id="clo" inputmode="decimal" value="${esc(fmtShort(shown(c.x, lo)))}"></label>
    <label>to [${esc(ulabel(ux))}]<input id="chi" inputmode="decimal" value="${esc(fmtShort(shown(c.x, hi)))}"></label>
    <label>Also show<select id="cy2"><option value="">nothing else</option>${second.map(s => `<option value="${esc(s)}" ${s === c.y2 ? "selected" : ""}>${esc(D.objects[s].text)} – ${esc(D.objects[s].name)}</option>`).join("")}</select></label>
  </div>
  <p class="small muted">${esc(o.text)} as ${esc(item(c.x).name.toLowerCase())} varies; every other input as on the Calculate tab. The dot is the current calculation.</p>
  <div id="chart"></div><details><summary>Values as a table</summary><div id="chart-table" class="scroll"></div></details>`;
  drawSweep();
}
function drawSweep() {
  const id = state.target, o = D.objects[id], w = W(id), c = w.chart, vals = valuesFor(id);
  const xin = parseFloat(String($("#clo").value).replace(",", ".")), xhi = parseFloat(String($("#chi").value).replace(",", "."));
  const f = unitOf(c.x)[1];
  if (!(isFinite(xin) && isFinite(xhi) && xhi > xin)) return;
  const lo = xin * f, hi = xhi * f, N = 80, xs = [], s1 = [], s2 = [];
  for (let i = 0; i <= N; i++) {
    const xv = lo + (hi - lo) * i / N, v = Object.assign({}, vals);
    v[c.x] = xv;
    try {
      const r = evaluate(id, v, w.given);
      xs.push(shown(c.x, xv)); s1.push(typeof r.value === "number" ? shown(id, r.value) : null);
      if (c.y2) s2.push(shown(c.y2, r.env[c.y2]));
    } catch (e) { /* outside the formula's domain */ }
  }
  const series = [{name: o.text, ys: s1, color: "var(--s1)"}];
  if (c.y2) series.push({name: D.objects[c.y2].text, ys: s2, color: "var(--s2)"});
  let cur = null;
  try { const r = evaluate(id, vals, w.given); cur = [shown(c.x, vals[c.x]), shown(id, r.value)]; } catch (e) {}
  const ref = o.check && w.check != null ? {label: symText(o.check), y: shown(o.check, w.check)} : null;
  lineChart($("#chart"), {xs, series, xLabel: `${symText(c.x)} [${ulabel(unitOf(c.x)[0])}]`, yUnit: ulabel(unitOf(id)[0]), marker: cur, ref});
  let t = `<table class="cases"><tr><th>${esc(symText(c.x))}</th>${series.map(s => `<th>${esc(s.name)}</th>`).join("")}</tr>`;
  for (let i = 0; i < xs.length; i += 8) t += `<tr><td>${esc(fmt(xs[i]))}</td>${series.map(s => `<td>${esc(fmt(s.ys[i]))}</td>`).join("")}</tr>`;
  $("#chart-table").innerHTML = t + "</table>";
}
function nice(lo, hi, n) {
  if (!(hi > lo)) hi = lo + 1;
  const raw = (hi - lo) / (n || 5), mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
  const out = [];
  for (let t = Math.ceil(lo / step - 1e-9) * step; t <= hi + 1e-9 * step; t += step) out.push(+t.toPrecision(12));
  return out;
}
const tick = v => Math.abs(v) >= 1000 || Number.isInteger(v) ? v.toFixed(0) : (+v.toPrecision(3)).toString();
function lineChart(el, opt) {
  const W = Math.max(320, el.clientWidth || 640), H = 300, ml = 58, mr = 16, mt = 14, mb = 42;
  const pw = W - ml - mr, ph = H - mt - mb, xs = opt.xs;
  if (!xs.length) { el.innerHTML = `<p class="small muted">No values in this range.</p>`; return; }
  const ys = opt.series.flatMap(s => s.ys).filter(v => v != null && isFinite(v)).concat(opt.ref ? [opt.ref.y] : []);
  let y0 = Math.min(0, ...ys), y1 = Math.max(...ys) * 1.08 || 1;
  const yt = nice(y0, y1, 5); y0 = Math.min(y0, yt[0]); y1 = Math.max(y1, yt[yt.length - 1]);
  const x0 = xs[0], x1 = xs[xs.length - 1], xt = nice(x0, x1, 6);
  const sx = v => ml + (v - x0) / (x1 - x0 || 1) * pw, sy = v => mt + ph - (v - y0) / (y1 - y0 || 1) * ph;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.series.map(x => x.name).join(", "))} against ${esc(opt.xLabel)}">`;
  for (const t of yt) s += `<line x1="${ml}" x2="${ml + pw}" y1="${sy(t)}" y2="${sy(t)}" style="stroke:var(--soft)" stroke-width="1"/><text x="${ml - 6}" y="${sy(t) + 4}" text-anchor="end" font-size="11" style="fill:var(--muted)">${tick(t)}</text>`;
  for (const t of xt) if (t >= x0 - 1e-9 && t <= x1 + 1e-9) s += `<text x="${sx(t)}" y="${mt + ph + 16}" text-anchor="middle" font-size="11" style="fill:var(--muted)">${tick(t)}</text>`;
  s += `<line x1="${ml}" x2="${ml + pw}" y1="${mt + ph}" y2="${mt + ph}" style="stroke:var(--muted)" stroke-width="1"/>`;
  s += `<text x="${ml + pw / 2}" y="${H - 6}" text-anchor="middle" font-size="12" style="fill:var(--ink)">${esc(opt.xLabel)}</text>`;
  s += `<text x="${ml - 50}" y="${mt + 2}" font-size="11" style="fill:var(--muted)">${esc(opt.yUnit ? "[" + opt.yUnit + "]" : "")}</text>`;
  if (opt.ref) s += `<line x1="${ml}" x2="${ml + pw}" y1="${sy(opt.ref.y)}" y2="${sy(opt.ref.y)}" style="stroke:var(--ink)" stroke-width="1" stroke-dasharray="4 3"/><text x="${ml + pw - 2}" y="${sy(opt.ref.y) - 5}" text-anchor="end" font-size="11" style="fill:var(--ink)">${esc(opt.ref.label)} = ${esc(fmt(opt.ref.y))}</text>`;
  for (const se of opt.series) {
    let d = "";
    se.ys.forEach((y, i) => { if (y != null && isFinite(y)) d += (d ? "L" : "M") + sx(xs[i]).toFixed(1) + "," + sy(y).toFixed(1); });
    s += `<path d="${d}" fill="none" style="stroke:${se.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  }
  if (opt.marker && isFinite(opt.marker[1])) s += `<circle cx="${sx(opt.marker[0])}" cy="${sy(opt.marker[1])}" r="5" style="fill:var(--s1);stroke:var(--surface)" stroke-width="2"/>`;
  s += `<g id="hover" style="display:none"><line id="hx" y1="${mt}" y2="${mt + ph}" style="stroke:var(--muted)" stroke-width="1"/>${opt.series.map((se, k) => `<circle id="hd${k}" r="4.5" style="fill:${se.color};stroke:var(--surface)" stroke-width="2"/>`).join("")}</g>`;
  s += `<rect x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="transparent" id="hit"/></svg>`;
  const key = opt.series.length > 1 ? `<div class="series-key">${opt.series.map(se => `<span><i style="background:${se.color}"></i>${esc(se.name)}</span>`).join("")}</div>` : "";
  el.innerHTML = key + `<div class="chartbox">${s}</div>`;
  const box = el.querySelector(".chartbox"), svg = box.querySelector("svg"), tip = $("#tip");
  const move = ev => {
    const r = svg.getBoundingClientRect(), k = W / r.width, px = (ev.clientX - r.left) * k;
    let i = Math.round((px - ml) / pw * (xs.length - 1)); i = Math.max(0, Math.min(xs.length - 1, i));
    const g = svg.querySelector("#hover"); g.style.display = "";
    svg.querySelector("#hx").setAttribute("x1", sx(xs[i])); svg.querySelector("#hx").setAttribute("x2", sx(xs[i]));
    opt.series.forEach((se, n) => { const c = svg.querySelector("#hd" + n), y = se.ys[i]; if (y == null) { c.style.display = "none"; return; } c.style.display = ""; c.setAttribute("cx", sx(xs[i])); c.setAttribute("cy", sy(y)); });
    tip.innerHTML = `${esc(opt.xLabel)}: <b>${esc(fmt(xs[i]))}</b>` + opt.series.map(se => `<br><span style="color:${se.color}">━</span> ${esc(se.name)}: <b>${esc(fmt(se.ys[i]))}</b> ${esc(opt.yUnit)}`).join("");
    showTip(ev, tip);
  };
  const hit = svg.querySelector("#hit");
  hit.addEventListener("pointermove", move); hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", () => { svg.querySelector("#hover").style.display = "none"; tip.style.display = "none"; });
}
function showTip(ev, tip) {
  tip.style.display = "block";
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let x = ev.clientX + 14 + window.scrollX, y = ev.clientY - th - 10 + window.scrollY;
  if (ev.clientX + 14 + tw > window.innerWidth - 8) x = ev.clientX - tw - 14 + window.scrollX;
  if (ev.clientY - th - 10 < 4) y = ev.clientY + 16 + window.scrollY;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}

// ---------------------------------------------------------------- Code
function renderCode() {
  const o = D.objects[state.target];
  $("#panel").innerHTML = `<h4>Python code block</h4><p class="small muted">Design logic only: the expression, its clause and units, and one line that identifies the version.</p>
    <pre class="code">${esc(o.python)}</pre>
    <h4>The function this page runs</h4><pre class="code">${esc(F[o.id].toString())}</pre>
    <h4>LaTeX</h4><p class="small muted">For a LaTeX document, or Word's equation editor in LaTeX mode.</p><pre class="code">${esc(o.tex)}</pre>
    <h4>The same logic as a file</h4><p class="small">Every output is printed from the same formula tree and carries the version <code>${esc(o.version)}</code>:</p>
    <pre class="code">python -m ckb excel ${esc(o.id)}            # Excel calculator, named ranges, live formulas
python -m ckb mathcad ${esc(o.id)}          # Mathcad Prime worksheet
python -m ckb report ${esc(o.id)} --pdf     # calculation report (or --template for many cases)
python -m ckb verify &lt;file&gt;              # is this file still the same logic?</pre>`;
}

// ---------------------------------------------------------------- Status (evidence, out of the way)
function renderStatus() {
  const o = D.objects[state.target], c = conf(o), ev = o.ev, b = o.bench, ref = o.reference || {};
  let h = `<h3>${dot(o)} ${esc(c.label)}</h3><ul class="small">${(o.conf.reasons || []).map(r => `<li>${esc(r)}</li>`).join("")}</ul>
    <div class="tiles">
      <div class="tile"><div class="v">${ev.sources}</div><div class="l">source files that apply it</div></div>
      <div class="tile"><div class="v">${ev.formulas}</div><div class="l">formulas found in them</div></div>
      <div class="tile"><div class="v">${b.total ? b.agree + " / " + b.total : "–"}</div><div class="l">source values reproduced</div></div>
      <div class="tile"><div class="v">${esc(ref.status || "–")}</div><div class="l">independent reference</div></div>
    </div>`;
  if (ev.variants.length) {
    h += `<h4>How the sources apply it</h4><div class="scroll"><table class="cases"><tr><th>Relation to the code</th><th>Formulas</th><th style="text-align:left">As written</th><th style="text-align:left">Differences</th></tr>`
      + ev.variants.map(v => `<tr><td>${esc(v.relation || "")}</td><td>${v.instances}</td><td style="text-align:left;white-space:normal">${esc(v.text)}</td><td style="text-align:left;white-space:normal">${esc((v.differences || []).concat(v.reason ? [v.reason] : []).join("; "))}</td></tr>`).join("") + `</table></div>`;
  }
  if (ev.practice.length) h += `<h4>Practice seen in the sources</h4><ul class="small">${ev.practice.map(p => `<li>${esc(p)}</li>`).join("")}</ul>`;
  if (b.pts.length) h += `<h4>Benchmarks</h4><p class="small muted">Each dot is a value a source shows, against what the code expression gives for the same inputs. On the line: reproduced.</p><div id="bench"></div>`;
  if (ref.library) h += `<h4>Independent reference</h4><p class="small">${esc(ref.status)} with ${esc(ref.library)} <code>${esc(ref.function || "")}</code> over ${ref.agreeing_samples || 0} of ${ref.samples || 0} samples.${ref.note ? " " + esc(ref.note) : ""}</p>`;
  h += `<h4>Use</h4><p class="small muted">Version ${esc(o.version)}. Uses and ratings are not recorded in this single-file copy; a shared deployment (an internal server or Azure) can count downloads and collect ratings per object.</p>`;
  $("#panel").innerHTML = h;
  if (b.pts.length) drawBench(o);
}
function drawBench(o) {
  const el = $("#bench"), W = Math.max(300, Math.min(560, el.clientWidth || 480)), H = W * 0.72, m = 52, pw = W - m - 14, ph = H - 14 - 40;
  const f = o.units[0][1], u = o.units[0][0];
  const pts = o.bench.pts.map(p => [p[0] / f * (p[3] ? 1000 : 1), p[1] / f * (p[3] ? 1000 : 1), p[2], p[4], p[5], p[6], p[3]]);
  const all = pts.flatMap(p => [p[0], p[1]]);
  let lo = Math.min(0, ...all), hi = Math.max(...all) * 1.05 || 1;
  const t = nice(lo, hi, 5); lo = Math.min(lo, t[0]); hi = Math.max(hi, t[t.length - 1]);
  const sx = v => m + (v - lo) / (hi - lo) * pw, sy = v => 14 + ph - (v - lo) / (hi - lo) * ph;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Source values against code values">`;
  for (const v of t) s += `<line x1="${m}" x2="${m + pw}" y1="${sy(v)}" y2="${sy(v)}" style="stroke:var(--soft)"/><text x="${m - 6}" y="${sy(v) + 4}" text-anchor="end" font-size="11" style="fill:var(--muted)">${tick(v)}</text><text x="${sx(v)}" y="${14 + ph + 16}" text-anchor="middle" font-size="11" style="fill:var(--muted)">${tick(v)}</text>`;
  s += `<line x1="${sx(lo)}" y1="${sy(lo)}" x2="${sx(hi)}" y2="${sy(hi)}" style="stroke:var(--muted)" stroke-width="1"/>`;
  pts.forEach((p, i) => { s += `<circle data-i="${i}" cx="${sx(p[0])}" cy="${sy(p[1])}" r="4.5" style="fill:${p[2] === "agree" ? "var(--s1)" : "var(--s2)"};stroke:var(--surface)" stroke-width="2"/>`; });
  s += `<text x="${m + pw / 2}" y="${H - 6}" text-anchor="middle" font-size="12" style="fill:var(--ink)">value in the source [${esc(u)}${pts.some(p => p[6]) ? " or " + esc(u) + "/m" : ""}]</text>`;
  s += `<text x="${m - 46}" y="10" font-size="11" style="fill:var(--muted)">code</text></svg>`;
  el.innerHTML = `<div class="series-key"><span><i style="background:var(--s1);height:8px;width:8px;border-radius:50%"></i>reproduced</span><span><i style="background:var(--s2);height:8px;width:8px;border-radius:50%"></i>differs</span></div><div class="chartbox" style="max-width:${W}px">${s}</div>`;
  const svg = el.querySelector("svg"), tip = $("#tip");
  svg.addEventListener("pointermove", ev => {
    const r = svg.getBoundingClientRect(), k = W / r.width, px = (ev.clientX - r.left) * k, py = (ev.clientY - r.top) * k;
    let best = -1, bd = 14 * 14;
    pts.forEach((p, i) => { const d = (sx(p[0]) - px) ** 2 + (sy(p[1]) - py) ** 2; if (d < bd) { bd = d; best = i; } });
    if (best < 0) { tip.style.display = "none"; return; }
    const p = pts[best];
    tip.innerHTML = `${esc(p[3])} ${esc(p[4])}<br>source <b>${esc(fmt(p[0]))}</b> · code <b>${esc(fmt(p[1]))}</b>${p[5] ? "<br>" + esc(p[5]).slice(0, 120) : ""}`;
    showTip(ev, tip);
  });
  svg.addEventListener("pointerleave", () => { tip.style.display = "none"; });
}

// ---------------------------------------------------------------- Overview
function renderOverview() {
  const objs = Object.values(D.objects), n = {high: 0, medium: 0, low: 0};
  for (const o of objs) n[(o.conf || {}).level || "medium"]++;
  let h = `<section class="card"><h3>What this is</h3><p class="small">Design-code expressions as small calculation objects, written from the codes themselves and checked against how real calculation files apply them. Pick a quantity on the left or search for it; every calculation shows its equations, substituted values and the code's conditions. The evidence behind each object is on its Status tab.</p>
    <div class="tiles"><div class="tile"><div class="v">${objs.length}</div><div class="l">calculation objects</div></div>
      <div class="tile"><div class="v">${Object.keys(D.quantities).length}</div><div class="l">parameters</div></div>
      <div class="tile"><div class="v">${D.codes.length}</div><div class="l">codes</div></div>
      <div class="tile"><div class="v">${D.sources}</div><div class="l">source files distilled</div></div></div></section>`;
  h += `<section class="card"><h3>Coverage and confidence by chapter</h3>
    <div class="series-key"><span><i class="dot good" style="width:9px;height:9px"></i>checked (${n.high})</span><span><i class="dot warn" style="width:9px;height:9px"></i>not yet checked (${n.medium})</span><span><i class="dot crit" style="width:9px;height:9px"></i>review needed (${n.low})</span></div>
    <div class="bars" id="bars" style="margin-top:8px"></div></section>`;
  h += `<section class="card"><h3>Codes and what they share</h3><div class="scroll"><table class="cases"><tr><th>Code</th><th style="text-align:left">Title</th><th>Objects</th><th>Shared</th><th style="text-align:left">Values it fixes</th></tr>`
    + D.codes.map(c => {
      const own = objs.filter(o => o.code === c.code).length, sh = objs.filter(o => (o.refs || []).some(r => r.code === c.code)).length;
      const fx = Object.entries(c.fixed || {}).map(([k, v]) => `${symText(k)} = ${fmtShort(v)}`).join(", ");
      return `<tr><td>${esc(c.code)}</td><td style="text-align:left;white-space:normal">${esc(c.title || "")}</td><td>${own}</td><td>${sh}</td><td style="text-align:left">${esc(fx || "–")}</td></tr>`;
    }).join("") + `</table></div>
    <p class="small muted">A later code that writes an expression already stored (EN 1994-1-1 f_cd = f_ck/γ_C) is linked to the existing object as a special case, with its own fixed values (α_cc = 1), so no formula is stored twice.</p></section>`;
  $("#main").innerHTML = h;
  // bars: one row per chapter, segments by confidence
  const groups = [];
  for (const c of D.codes) {
    const by = {};
    for (const o of objs.filter(o => o.code === c.code)) { const k = o.topic.split(".").slice(0, 2).join("."); (by[k] = by[k] || {high: 0, medium: 0, low: 0, ids: []})[(o.conf || {}).level || "medium"]++; by[k].ids.push(o.id); }
    for (const k of Object.keys(by).sort(cmpTopic)) groups.push({label: `${c.code.replace("EN ", "")} · ${topicTitle(c.code, k)}`, ...by[k]});
  }
  const max = Math.max(...groups.map(g => g.high + g.medium + g.low));
  $("#bars").innerHTML = groups.map((g, i) => {
    const segs = [["high", "good", "checked"], ["medium", "warn", "not yet checked"], ["low", "crit", "review needed"]].filter(([k]) => g[k])
      .map(([k, cls, l]) => `<span class="seg" data-g="${i}" data-l="${l}" data-n="${g[k]}" style="width:${g[k] / max * 100}%;background:var(--${cls})"></span>`).join("");
    return `<div class="row"><div class="lab" title="${esc(g.label)}">${esc(g.label)}</div><div class="track">${segs}<span class="n">${g.high + g.medium + g.low}</span></div></div>`;
  }).join("");
  const tip = $("#tip");
  for (const sg of document.querySelectorAll("#bars .seg")) {
    sg.addEventListener("pointermove", ev => { const g = groups[+sg.dataset.g]; tip.innerHTML = `${esc(g.label)}<br><b>${sg.dataset.n}</b> ${esc(sg.dataset.l)}`; showTip(ev, tip); });
    sg.addEventListener("pointerleave", () => { tip.style.display = "none"; });
  }
}

// ---------------------------------------------------------------- settings
function renderSettings() {
  $("#set-dec").innerHTML = [0, 1, 2, 3, 4].map(d => `<option ${d === S.decimals ? "selected" : ""}>${d}</option>`).join("");
  $("#set-sig").innerHTML = [2, 3, 4].map(d => `<option ${d === S.minsig ? "selected" : ""}>${d}</option>`).join("");
  let ids = [];
  if (state.view === "object") { const w = W(state.target), p = plan(state.target, w.given); ids = p.steps.slice().reverse().concat(p.inputs); if (D.objects[state.target].check) ids.push(D.objects[state.target].check); }
  ids = ids.filter((x, i) => ids.indexOf(x) === i && item(x) && item(x).units.length > 1);
  $("#set-units").innerHTML = ids.length ? ids.map(i => `<div class="setrow"><span><math>${symML(i)}</math> ${esc(item(i).name)}</span><select data-unit="${esc(i)}">${item(i).units.map(u => `<option ${u[0] === unitOf(i)[0] ? "selected" : ""}>${esc(u[0])}</option>`).join("")}</select></div>`).join("")
    : `<p class="muted">Open a calculation to choose its units.</p>`;
}

// ---------------------------------------------------------------- events
document.addEventListener("click", ev => {
  const t = ev.target.closest("button, [data-open]");
  if (!t) return;
  const d = t.dataset;
  if (d.id) { open(d.id); return; }
  if (d.open) { open(d.open); return; }
  if (d.code) { state.code = d.code; store.set("code", d.code); renderCodes(); renderTree(); return; }
  if (d.tab) { state.tab = d.tab; renderMain(); return; }
  const id = state.target;
  if (d.set) { const w = W(id); w.values[d.set] = +d.v; w.entered.add(d.set); saveWork(id); renderInputs(); renderSheet(); return; }
  if (d.give) { const w = W(id), r = evaluate(id, valuesFor(id), w.given); w.given.add(d.give); w.values[d.give] = r.env[d.give]; w.entered.add(d.give); saveWork(id); renderInputs(); renderSheet(); return; }
  if (d.ungive) { const w = W(id); w.given.delete(d.ungive); w.entered.delete(d.ungive); saveWork(id); renderInputs(); renderSheet(); return; }
  if (d.load) { const c = cases()[+d.load], w = W(id); w.values = Object.assign({}, c.values); w.entered = new Set(Object.keys(c.values)); w.given = new Set(c.given || []); w.check = c.check; saveWork(id); renderCalc(); return; }
  if (d.del) { const l = cases(); l.splice(+d.del, 1); setCases(l); renderCases(); return; }
  if (t.id === "ovw") { state.view = "overview"; renderTree(); renderMain(); return; }
  if (t.id === "reset") { const w = W(id); w.values = {}; w.entered = new Set(); w.given = new Set(); w.check = null; saveWork(id); renderInputs(); renderSheet(); return; }
  if (t.id === "add-case") { const l = cases(); l.push(currentCase(`Case ${l.length + 1}`)); setCases(l); renderCases(); return; }
  if (t.id === "clear-cases") { setCases([]); renderCases(); return; }
  if (t.id === "tpl") { renderBuilder(); return; }
  if (t.id === "dl-xlsx") { download("xlsx"); return; }
  if (t.id === "dl-mcdx") { download("mcdx"); return; }
  if (t.id === "dl-html") { download("html"); return; }
  if (t.id === "ask-btn") { ask(); return; }
  if (t.id === "copy") {
    const ta = $("#yaml"); ta.select();
    let ok = false;
    try { navigator.clipboard.writeText(ta.value).then(() => { $("#copied").textContent = "copied"; }, () => { $("#copied").textContent = "selected: press Ctrl+C"; }); ok = true; } catch (e) {}
    if (!ok) $("#copied").textContent = "selected: press Ctrl+C";
    return;
  }
  if (t.id === "settings-btn") { renderSettings(); try { $("#settings").showModal(); } catch (e) { $("#settings").setAttribute("open", ""); } return; }
  if (t.id === "set-close") { $("#settings").close(); return; }
  if (t.id === "set-reset") { S.decimals = 2; S.minsig = 3; S.units = {}; store.set("style", S); renderSettings(); renderMain(); return; }
});
document.addEventListener("keydown", ev => {
  const t = ev.target.closest && ev.target.closest("[data-open]");
  if (t && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); open(t.dataset.open); }
});
document.addEventListener("input", ev => {
  const t = ev.target;
  if (t.id === "q") { state.q = t.value; renderTree(); return; }
  if (t.dataset.in) {
    const id = state.target, o = D.objects[id], w = W(id), p = t.dataset.in;
    const raw = t.value.trim().replace(",", ".");
    const v = parseFloat(raw);
    if (raw === "" && p === o.check) { w.check = null; saveWork(id); renderSheet(); return; }
    if (!isFinite(v)) return;
    const c = v * unitOf(p)[1];
    if (p === o.check) w.check = c; else { w.values[p] = c; w.entered.add(p); }
    saveWork(id); renderSheet();
    // refresh this row's hints (recommended, usual range) without re-rendering the inputs
    const row = t.closest(".inp"), tmp = document.createElement("div");
    tmp.innerHTML = inputRow(p, c, p === o.check);
    const old = row.querySelector(".hint"), nu = tmp.querySelector(".hint");
    if (old && nu) old.replaceWith(nu); else if (old) old.remove(); else if (nu) row.appendChild(nu);
    return;
  }
  if (t.dataset.rb !== undefined || t.dataset.rem !== undefined) {
    const rb = reportOpts();
    if (t.dataset.rem !== undefined) rb.remarks[t.dataset.rem] = t.value;
    else rb[t.dataset.rb] = t.type === "checkbox" ? t.checked : t.value;
    $("#yaml").value = templateYAML();
    return;
  }
  if (t.id === "clo" || t.id === "chi") { const w = W(state.target), f = unitOf(w.chart.x)[1]; const a = parseFloat($("#clo").value.replace(",", ".")), b = parseFloat($("#chi").value.replace(",", ".")); if (isFinite(a) && isFinite(b)) { w.chart.lo = a * f; w.chart.hi = b * f; } drawSweep(); return; }
});
document.addEventListener("change", ev => {
  const t = ev.target;
  if (t.dataset.show) { const w = W(state.target); w.show[t.dataset.show] = t.checked; saveWork(state.target); renderSheet(); return; }
  if (t.id === "only-result") { const w = W(state.target); w.steps = t.checked ? "result" : "all"; saveWork(state.target); renderSheet(); return; }
  if (t.dataset.unit) { S.units[t.dataset.unit] = t.value; store.set("style", S); if ($("#settings").open) renderSettings(); renderMain(); return; }
  if (t.id === "set-dec") { S.decimals = +t.value; store.set("style", S); renderMain(); return; }
  if (t.id === "set-sig") { S.minsig = +t.value; store.set("style", S); renderMain(); return; }
  if (t.id === "cx") { const w = W(state.target); w.chart = {x: t.value, y2: w.chart.y2}; renderChart(); return; }
  if (t.id === "cy2") { W(state.target).chart.y2 = t.value; drawSweep(); return; }
});
let rz = null;
window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { if (state.view === "object" && state.tab === "chart") drawSweep(); }, 150); });

// ---------------------------------------------------------------- start
(function start() {
  const nObj = Object.keys(D.objects).length;
  $("#sub").textContent = `${nObj} objects from ${D.codes.map(c => c.code).join(" and ")}: expressions from the codes, checked against ${D.sources} calculation file${D.sources === 1 ? "" : "s"}`;
  if (!D.codes.some(c => c.code === state.code)) state.code = "all";
  renderCodes(); renderTree(); renderMain();
})();
</script>"""
