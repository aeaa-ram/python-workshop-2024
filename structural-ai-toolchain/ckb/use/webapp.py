"""The web calculator: the knowledge base as one self-contained HTML file.

No server and no installation: the file holds the objects, their formulas as plain
JavaScript functions, the design background and - out of the way, on a Status tab -
the evidence behind each object.  An engineer finds a quantity in the code tree or
by searching ("concrete shear"), types the inputs and reads a clean calculation that
updates as they type.  Dependencies are resolved in the page, and any intermediate
value can be entered directly instead of being calculated.

Per object there are six tabs:

    Calculate           inputs and the calculation, one line per step
    Cases and report    several sets of inputs; a report as PDF or Word, made in the page
    Design background   scope, limitations, pitfalls and guidance with their sources;
                        where the object is shared with other codes; a dependency map
    Chart               the result against any input (a parameter study)
    Code                the Python code block and the LaTeX of the expression
    Status              confidence, sources, simplifications found, benchmarks,
                        independent reference check

Excel calculators and Mathcad worksheets embedded with ``files`` download from the page; reports
are written in the page itself (HTML to print as PDF, and Word with editable equations).

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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&family=Noto+Sans+Math&display=swap">
<style>
:root{
  --bg:#ecf0f2; --surface:#ffffff; --raised:#f5f8f9; --tint:#eff5f7; --ink:#14212a; --ink2:#3c4b56; --muted:#66757f; --rule:#d2dbe0; --soft:#e5ebee;
  --brand:#0f4757; --brand2:#17687a; --accent:#0f6b80; --accent-ink:#0b5566; --accent-soft:#e0eff3;
  --gold:#a86b12; --gold-soft:#fbf0dc;
  --s1:#2a78d6; --s2:#eb6834;
  --good:#1e8e3e; --good-soft:#e7f4eb; --warn:#c07f0e; --warn-soft:#fdf3df; --crit:#c5221f; --crit-soft:#fce9e7;
  --ec2:#0f7b8a; --ec3:#2f62b8; --ec4:#7a4fb3; --gen:#8a6a12;
  --shadow:0 1px 2px rgba(15,40,52,.06),0 2px 8px rgba(15,40,52,.05);
  --font:"IBM Plex Sans","Segoe UI",system-ui,Arial,sans-serif; --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  --math:"Cambria Math","STIX Two Math","Latin Modern Math","Noto Sans Math",math;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#0e1316; --surface:#162027; --raised:#1c272f; --tint:#172830; --ink:#e5ecef; --ink2:#b9c6cd; --muted:#8998a1; --rule:#2b3a43; --soft:#22303a;
  --brand:#0b3440; --brand2:#124a58; --accent:#5cc0d6; --accent-ink:#86d3e4; --accent-soft:#15343e;
  --gold:#e2aa4c; --gold-soft:#30260f; --s1:#3987e5; --s2:#d95926;
  --good:#4cc36f; --good-soft:#14301d; --warn:#e2aa4c; --warn-soft:#30260f; --crit:#f07a74; --crit-soft:#3a1a19;
  --ec2:#4fc1cf; --ec3:#86a9ee; --ec4:#b89bf0; --gen:#d8b65a; --shadow:none; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0e1316; --surface:#162027; --raised:#1c272f; --tint:#172830; --ink:#e5ecef; --ink2:#b9c6cd; --muted:#8998a1; --rule:#2b3a43; --soft:#22303a;
  --brand:#0b3440; --brand2:#124a58; --accent:#5cc0d6; --accent-ink:#86d3e4; --accent-soft:#15343e;
  --gold:#e2aa4c; --gold-soft:#30260f; --s1:#3987e5; --s2:#d95926;
  --good:#4cc36f; --good-soft:#14301d; --warn:#e2aa4c; --warn-soft:#30260f; --crit:#f07a74; --crit-soft:#3a1a19;
  --ec2:#4fc1cf; --ec3:#86a9ee; --ec4:#b89bf0; --gen:#d8b65a; --shadow:none; color-scheme:dark}
*{box-sizing:border-box}
html,body{background:var(--bg)}
body{color:var(--ink);font:14px/1.5 var(--font);margin:0}
math{font-family:var(--math);font-size:1.1em}
button,input,select,textarea{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.wrap{max-width:1480px;margin:0 auto;padding-block:max(14px,env(safe-area-inset-top,0px)) 40px;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header.top{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:center;justify-content:space-between;margin-bottom:14px;
  background:linear-gradient(120deg,var(--brand),var(--brand2));color:#fff;border-radius:12px;padding:14px 20px;box-shadow:var(--shadow)}
header.top h1{font-size:20px;margin:0;font-weight:600;letter-spacing:-.01em;color:#fff}
header.top p{margin:2px 0 0;color:rgba(255,255,255,.8);font-size:13px}
header.top .btn{background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.35);color:#fff}
header.top .btn:hover{background:rgba(255,255,255,.22);border-color:#fff}
.btn{display:inline-flex;gap:7px;align-items:center;background:var(--surface);border:1px solid var(--rule);padding:6px 13px;cursor:pointer;border-radius:8px;font-weight:500;font-size:13.5px}
.btn:hover{border-color:var(--accent);color:var(--accent-ink)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--surface)}
.btn.primary:hover{filter:brightness(1.08);color:var(--surface)}
.btn.ghost{background:none}
.btn svg{width:16px;height:16px;flex:none}
.btn[disabled]{opacity:.6;cursor:progress}
.icon-btn{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:6px;border:1px solid transparent;background:none;cursor:pointer;color:var(--muted);flex:none;font-size:14px}
.icon-btn:hover{border-color:var(--rule);color:var(--accent-ink);background:var(--raised)}
.shell{display:grid;grid-template-columns:300px minmax(0,1fr);gap:16px;align-items:start}
nav.side{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:12px;position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto;box-shadow:var(--shadow)}
.search{width:100%;padding:8px 11px;border:1px solid var(--rule);background:var(--raised);border-radius:8px}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin:10px 0 6px}
.chip{border:1px solid var(--rule);background:var(--raised);border-radius:999px;padding:2px 10px;font-size:12px;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--surface)}
.t-code{font-weight:600;font-size:12.5px;color:var(--cc,var(--ink));margin:14px 0 4px;padding:3px 0 3px 9px;border-left:3px solid var(--cc,var(--rule))}
.t-code small{display:block;font-weight:400;color:var(--muted);font-size:11.5px}
.t-chap{font-weight:600;margin:9px 0 2px;font-size:13px}
.t-sec{color:var(--muted);font-size:12px;margin:6px 0 1px 4px}
.t-obj{display:flex;gap:8px;align-items:center;width:100%;text-align:left;background:none;border:0;border-left:2px solid var(--soft);padding:3px 8px;cursor:pointer;margin-left:4px;border-radius:0 6px 6px 0}
.t-obj:hover{background:var(--raised)} .t-obj[aria-current="true"]{border-left-color:var(--accent);background:var(--accent-soft)}
.t-obj .s{min-width:4.8em;font-size:13px} .t-obj .n{color:var(--muted);font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dot{width:9px;height:9px;border-radius:50%;flex:none;display:inline-block}
.dot.good{background:var(--good)} .dot.warn{background:var(--warn)} .dot.crit{background:var(--crit)}
.legend-dots{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--muted);margin-top:12px;padding-top:8px;border-top:1px solid var(--soft)}
.legend-dots span{display:inline-flex;gap:5px;align-items:center}
.ovw{display:block;width:100%;text-align:left;background:var(--raised);border:1px solid var(--rule);padding:7px 10px;cursor:pointer;margin-top:10px;border-radius:8px;font-weight:500}
.ovw[aria-current="true"]{border-color:var(--accent);color:var(--accent-ink)}
.hit{display:block;width:100%;text-align:left;background:none;border:0;border-bottom:1px solid var(--soft);padding:7px 4px;cursor:pointer}
.hit:hover{background:var(--raised)} .hit .r{color:var(--muted);font-size:12px}
main{min-width:0;display:flex;flex-direction:column;gap:14px}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)}
.head{border-top:4px solid var(--cc,var(--accent))}
.head-grid{display:flex;flex-wrap:wrap;gap:12px 24px;justify-content:space-between;align-items:flex-start}
.crumb{color:var(--muted);font-size:12.5px}
.head h2{margin:3px 0 8px;font-size:21px;font-weight:600;line-height:1.3;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.head h2 math{color:var(--cc,var(--accent-ink))}
.meta{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center}
.pill{display:inline-flex;gap:6px;align-items:center;border-radius:999px;padding:2px 11px;font-size:12.5px;background:var(--tint);color:var(--ink2);border:1px solid var(--soft)}
button.pill{cursor:pointer}
.actions{display:flex;flex-wrap:wrap;gap:8px}
[role="tablist"]{display:flex;gap:4px;margin-top:14px;overflow-x:auto;padding-bottom:2px}
[role="tab"]{background:none;border:1px solid transparent;border-radius:999px;padding:6px 14px;cursor:pointer;color:var(--ink2);white-space:nowrap;font-weight:500}
[role="tab"]:hover{background:var(--raised)}
[role="tab"][aria-selected="true"]{background:var(--accent);color:var(--surface)}
h3{font-size:15px;margin:0 0 10px;font-weight:600;color:var(--accent-ink);display:flex;gap:8px;align-items:center}
h4{font-size:13.5px;margin:16px 0 6px;font-weight:600;color:var(--accent-ink)}
.calc-grid{display:grid;grid-template-columns:minmax(250px,320px) minmax(0,1fr);gap:18px;align-items:start}
.inputs{background:var(--tint);border:1px solid var(--soft);border-radius:10px;padding:14px 14px 12px}
.inputs h3.sub{margin-top:16px}
.inp{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 8px;align-items:center;padding:7px 0;border-bottom:1px solid var(--soft)}
.inp:last-of-type{border-bottom:0}
.inp label{font-size:13px;color:var(--ink2);display:flex;align-items:center;gap:4px;min-width:0}
.inp .sym{text-align:right;color:var(--accent-ink)}
.ctl{grid-column:1/-1;display:flex;gap:6px;align-items:center}
.ctl input{flex:1;min-width:0;padding:5px 9px;border:1px solid var(--rule);background:var(--surface);border-radius:6px;font-variant-numeric:tabular-nums}
.ctl input.out{border-color:var(--warn);background:var(--warn-soft)}
.ctl select,.ctl .u{min-width:4.4em;padding:5px 6px;border:1px solid var(--rule);background:var(--surface);border-radius:6px;font-size:12.5px}
.ctl .u{border-color:transparent;background:none;color:var(--muted)}
.info{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;border:1px solid var(--muted);color:var(--muted);font:600 10px/1 var(--font);cursor:help;flex:none;font-style:normal}
.info.warn{border-color:var(--warn);color:var(--surface);background:var(--warn)}
.fixed{font-size:13px;color:var(--ink2);margin:10px 0 0}
.sheet-h{display:flex;flex-wrap:wrap;gap:8px 16px;justify-content:space-between;align-items:center;margin-bottom:4px}
.sheet-h h3{margin:0}
.seg-ctl{display:inline-flex;border:1px solid var(--rule);border-radius:8px;overflow:hidden;background:var(--surface)}
.seg-ctl button{border:0;border-left:1px solid var(--rule);background:none;padding:4px 12px;font-size:12.5px;cursor:pointer;color:var(--ink2)}
.seg-ctl button:first-child{border-left:0}
.seg-ctl button[aria-pressed="true"]{background:var(--accent-soft);color:var(--accent-ink);font-weight:600}
.st{display:grid;grid-template-columns:minmax(140px,26%) minmax(0,1fr);gap:4px 20px;padding:10px 0;border-bottom:1px solid var(--soft);align-items:center}
.st .nm{display:block;font-size:13.5px;color:var(--ink)} .st .cl{display:block;font-size:12px;color:var(--muted)}
.st .row{display:flex;gap:8px;align-items:center;justify-content:space-between;min-width:0}
.chain{display:flex;flex-wrap:wrap;align-items:center;column-gap:.55em;row-gap:8px;min-width:0}
.chain .seg{white-space:nowrap;max-width:100%;overflow-x:auto}
.chain .res math{color:var(--accent-ink);font-weight:700}
.verdict{margin:16px 0 8px;padding:12px 16px;border-radius:10px;display:flex;flex-wrap:wrap;gap:8px 28px;align-items:center;background:var(--raised);border:1px solid var(--rule)}
.verdict.pass{background:var(--good-soft);border-color:var(--good)} .verdict.fail{background:var(--crit-soft);border-color:var(--crit)}
.verdict math{font-size:1.15em}
.badge{display:inline-flex;gap:6px;align-items:center;font-weight:700;padding:3px 12px;border-radius:999px;font-size:13px;letter-spacing:.02em}
.badge.ok{background:var(--good);color:#fff} .badge.bad{background:var(--crit);color:#fff}
.conds ul{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.conds li{display:flex;gap:9px;align-items:baseline;font-size:13.5px}
.conds .mk{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;font-size:11px;font-weight:700;background:var(--soft);color:var(--ink2);flex:none;cursor:help}
.conds li.met .mk{background:var(--good);color:#fff} .conds li.unmet .mk{background:var(--crit);color:#fff}
.muted{color:var(--muted)} .small{font-size:12.5px}
.ok{color:var(--good)} .bad{color:var(--crit)}
.rep-grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(300px,1fr);gap:22px;align-items:start}
.rep-grid section{min-width:0}
.empty{color:var(--ink2);background:var(--tint);border:1px dashed var(--rule);border-radius:10px;padding:14px 16px;margin:0}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 12px}
.form label{display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--ink2);font-weight:500}
.form label.wide{grid-column:1/-1}
.form input,.form select,.ctrls input,.ctrls select{padding:6px 9px;border:1px solid var(--rule);background:var(--surface);border-radius:6px;min-width:0}
fieldset{border:1px solid var(--soft);border-radius:10px;margin:14px 0 0;padding:10px 14px 12px;display:grid;gap:7px;min-width:0}
legend{font-weight:600;font-size:13px;color:var(--accent-ink);padding:0 4px}
fieldset label{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center;font-size:13.5px;cursor:pointer;min-width:0}
fieldset select{padding:3px 6px;border:1px solid var(--rule);border-radius:6px;background:var(--surface);flex:1 1 180px;width:0;min-width:0;max-width:100%}
table.cases{width:100%;border-collapse:collapse;font-size:13px}
table.cases th,table.cases td{border-bottom:1px solid var(--soft);padding:6px 8px;text-align:right;white-space:nowrap}
table.cases th:first-child,table.cases td:first-child{text-align:left}
table.cases th{font-weight:600;border-bottom:2px solid var(--rule);color:var(--ink2);background:var(--raised)} table.cases th small{display:block;font-weight:400;color:var(--muted)}
table.cases tr.gov td{background:var(--accent-soft);font-weight:600}
.linkish{background:none;border:0;padding:0;color:var(--accent-ink);cursor:pointer;font-weight:500;text-decoration:underline;text-decoration-color:var(--rule);text-underline-offset:3px}
.scroll{overflow-x:auto}
#ask{margin:8px 0 2px} #ask-out{margin-top:6px} #ask-out .ans{margin:4px 0 6px;color:var(--ink2)}
pre.code{font:12.5px/1.55 var(--mono);background:var(--raised);border:1px solid var(--soft);padding:12px 14px;overflow:auto;border-radius:8px;margin:0}
.code-h{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:16px 0 6px}
.code-h:first-child{margin-top:0} .code-h h4{margin:0}
.note{border-left:3px solid var(--rule);padding:6px 0 6px 12px;margin:8px 0;background:linear-gradient(90deg,var(--raised),transparent 70%);border-radius:0 6px 6px 0}
.note.pitfall{border-left-color:var(--crit)} .note.limitation{border-left-color:var(--warn)} .note.scope{border-left-color:var(--accent)} .note.practice{border-left-color:var(--gold)} .note.guidance{border-left-color:var(--good)}
.note .src{font-size:12px;color:var(--muted);margin-top:3px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:10px 0 4px}
.tile{background:var(--tint);border:1px solid var(--soft);border-radius:10px;padding:10px 12px}
.tile .v{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--accent-ink)} .tile .l{font-size:12.5px;color:var(--ink2)}
.chartbox{position:relative;margin-top:8px}
.chartbox svg{display:block;width:100%;height:auto;overflow:visible}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:7px 10px;font-size:12.5px;box-shadow:0 4px 14px rgba(0,0,0,.14);max-width:340px;white-space:pre-line;display:none;z-index:5;color:var(--ink)}
.tip b{font-variant-numeric:tabular-nums}
.ctrls{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:end;font-size:13px}
.ctrls label{display:flex;flex-direction:column;gap:3px;color:var(--ink2);font-size:12.5px;font-weight:500}
.series-key{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;margin-top:8px}
.series-key span{display:inline-flex;gap:6px;align-items:center}
.series-key i{display:inline-block;width:16px;height:2px}
.bars .row{display:grid;grid-template-columns:minmax(120px,260px) minmax(0,1fr);gap:10px;align-items:center;padding:3px 0}
.bars .lab{font-size:12.5px;color:var(--ink2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bars .track{display:flex;align-items:center;gap:2px;min-height:16px}
.bars .seg{height:14px}
.bars .seg:last-of-type{border-radius:0 4px 4px 0}
.bars .n{font-size:12px;color:var(--ink2);margin-left:6px;font-variant-numeric:tabular-nums}
.depmap{overflow-x:auto;margin-top:6px}
.depmap svg{display:block}
.depmap .node{cursor:pointer}
dialog{border:1px solid var(--rule);border-radius:12px;background:var(--surface);color:var(--ink);max-width:min(520px,calc(100vw - 32px));padding:18px}
dialog::backdrop{background:rgba(0,0,0,.35)}
.setrow{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:5px 0;font-size:13.5px;border-bottom:1px solid var(--soft)}
.setrow select{padding:3px 6px;border:1px solid var(--rule);background:var(--raised);border-radius:6px}
.toast{position:fixed;right:max(16px,env(safe-area-inset-right,0px));bottom:max(16px,env(safe-area-inset-bottom,0px));max-width:min(420px,calc(100vw - 32px));background:var(--ink);color:var(--surface);padding:10px 14px;border-radius:10px;font-size:13.5px;box-shadow:0 6px 20px rgba(0,0,0,.2);opacity:0;transform:translateY(8px);transition:opacity .2s,transform .2s;pointer-events:none;z-index:9}
.toast.show{opacity:1;transform:none}
@media (max-width:1100px){.rep-grid{grid-template-columns:minmax(0,1fr)}}
@media (max-width:900px){.shell{grid-template-columns:minmax(0,1fr)} nav.side{position:static;max-height:46vh}
  .calc-grid{grid-template-columns:minmax(0,1fr)}}
@media (max-width:640px){.st{grid-template-columns:minmax(0,1fr)} .form{grid-template-columns:minmax(0,1fr)}}
@media (prefers-reduced-motion:reduce){.toast{transition:none}}
</style>
<div class="wrap">
<header class="top">
  <div><h1>Calculation Knowledge Base</h1><p id="sub"></p></div>
  <button class="btn" id="settings-btn" type="button">Settings</button>
</header>
<div class="shell">
  <nav class="side" aria-label="Codes and calculation objects">
    <input class="search" id="q" type="search" placeholder="Search: concrete shear, V_Rd,c, 6.2.2" aria-label="Search">
    <div id="ask" hidden><button class="btn" type="button" id="ask-btn">Ask Claude</button><div id="ask-out" class="small"></div></div>
    <div class="chips" id="codes"></div>
    <div id="tree"></div>
    <button class="ovw" id="ovw" type="button">Overview</button>
    <div class="legend-dots"><span><i class="dot good"></i>Checked</span><span><i class="dot warn"></i>Not yet checked</span><span><i class="dot crit"></i>Review needed</span></div>
  </nav>
  <main id="main"></main>
</div>
</div>
<dialog id="settings">
  <h3>Settings</h3>
  <div class="setrow"><span>Decimal places</span><select id="set-dec"></select></div>
  <div class="setrow"><span>Significant digits for small values</span><select id="set-sig"></select></div>
  <h4>Units</h4>
  <div id="set-units"></div>
  <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
    <button class="btn" id="set-reset" type="button">Reset</button><button class="btn primary" id="set-close" type="button">Done</button>
  </div>
</dialog>
<div class="tip" id="tip" role="tooltip"></div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>

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

// ---------------------------------------------------------------- confidence
const CONF = {high: {cls: "good", label: "Checked"}, medium: {cls: "warn", label: "Not yet checked"}, low: {cls: "crit", label: "Review needed"}};
const conf = o => CONF[(o.conf || {}).level] || CONF.medium;
const dot = o => { const c = conf(o); return `<span class="dot ${c.cls}" role="img" aria-label="${c.label}" title="${c.label}"></span>`; };
const CODE_COLOR = {"EN 1992": "var(--ec2)", "EN 1993": "var(--ec3)", "EN 1994": "var(--ec4)"};
const codeColor = code => (code ? CODE_COLOR[String(code).slice(0, 7)] : "var(--gen)") || "var(--accent)";
const ICON_DL = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 2.5v8M4.5 7.5 8 11l3.5-3.5M3 13.5h10"/></svg>`;
const ICON_DOC = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.8h5.5L12.5 5v9.2h-8.5z"/><path d="M9.3 1.8V5h3.2M6.2 8.5h4M6.2 11h4"/></svg>`;

// ---------------------------------------------------------------- state
const state = {view: "overview", target: null, tab: "calc", code: store.get("code", "all"), q: ""};
const DETAIL = [["full", "Full"], ["equations", "Without substitution"], ["result", "Results only"]];
const work = {};      // per object: {values, entered:Set, given:Set, check, detail, chart, report}
function W(id) {
  if (!work[id]) {
    const saved = store.get("work:" + id, null);
    const w = {values: {}, entered: new Set(), given: new Set(), check: null, detail: "full", chart: {}};
    if (saved) {
      w.given = new Set(saved.given || []);
      Object.assign(w.values, saved.values || {});
      w.entered = new Set(Object.keys(saved.values || {}));
      w.check = saved.check == null ? null : saved.check;
      if (DETAIL.some(d => d[0] === saved.detail)) w.detail = saved.detail;
      if (saved.report) w.report = saved.report;
    }
    work[id] = w;
  }
  return work[id];
}
function saveWork(id) {
  const w = work[id];
  const vals = {};
  for (const k of w.entered) if (k in w.values) vals[k] = w.values[k];
  store.set("work:" + id, {values: vals, given: [...w.given], check: w.check, detail: w.detail, report: w.report});
}
function valuesFor(id) {
  const w = W(id);
  const v = defaults(id, w.given);
  for (const k of w.entered) if (k in w.values) v[k] = w.values[k];
  return v;
}
let toastTimer = null;
function toast(text) {
  const el = $("#toast");
  if (!text) return;
  el.textContent = text; el.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 6500);
}

// ---------------------------------------------------------------- page
function openObject(id, tab) {
  state.view = "object"; state.target = id; state.tab = tab || "calc";
  renderTree(); renderMain();
  try {   // on a phone the tree sits above the page: go to the calculation
    if (window.matchMedia("(max-width: 900px)").matches) $("#main").scrollIntoView({block: "start"});
    else window.scrollTo({top: 0});
  } catch (e) {}
}
const TABS = [["calc", "Calculate"], ["report", "Cases and report"], ["background", "Design background"], ["chart", "Chart"], ["code", "Code"], ["status", "Status"]];
function renderMain() {
  $("#ovw").setAttribute("aria-current", String(state.view === "overview"));
  if (state.view !== "object") { renderOverview(); return; }
  const o = D.objects[state.target], c = conf(o), f = D.files && D.files[o.id];
  const crumb = (o.code ? [o.code] : ["Definitions used by every code"]).concat(o.path || []).join(" › ");
  const actions = (f ? `<button class="btn" type="button" id="dl-xlsx">${ICON_DL}Download Excel</button><button class="btn" type="button" id="dl-mcdx">${ICON_DL}Download Mathcad</button>` : "")
    + `<button class="btn primary" type="button" data-tab="report">${ICON_DOC}Create report</button>`;
  $("#main").innerHTML = `<section class="card head" style="--cc:${codeColor(o.code)}"><div class="head-grid"><div>
      <div class="crumb">${esc(crumb)}</div>
      <h2><math>${o.ml}</math><span>${esc(o.name)}</span></h2>
      <div class="meta"><span class="pill">${esc(o.ref)}</span><button class="pill" type="button" data-tab="status">${dot(o)}${esc(c.label)}</button></div>
    </div><div class="actions">${actions}</div></div>
    <div role="tablist" aria-label="Views">${TABS.map(([k, l]) => `<button role="tab" type="button" data-tab="${k}" aria-selected="${state.tab === k}">${l}</button>`).join("")}</div>
  </section><section class="card" id="panel"></section>`;
  ({calc: renderCalc, report: renderReport, background: renderBackground, chart: renderChart, code: renderCode, status: renderStatus})[state.tab]();
}

// ---------------------------------------------------------------- Calculate
function renderCalc() {
  $("#panel").innerHTML = `<div class="calc-grid"><div class="inputs" id="inputs"></div><div id="sheet"></div></div>`;
  renderInputs(); renderSheet();
}
function inputInfo(p, value) {
  const it = item(p), [u] = unitOf(p), q = D.quantities[p], w = W(state.target), tip = [];
  let out = false;
  if (q && q.ref) tip.push(q.ref);
  if (q && q.kind === "coefficient" && q.value != null) tip.push(`Recommended value: ${fmtShort(shown(p, q.value))} ${ulabel(u)}`.trim());
  if (q && q.ndp) tip.push("Nationally determined parameter: check the National Annex.");
  if (q && q.choices && q.choices.length) tip.push("Common values: " + q.choices.map(ch => `${fmtShort(shown(p, ch.value))} (${ch.label})`).join(", "));
  const practice = new Set();
  for (const s of plan(state.target, w.given).steps) for (const b of D.objects[s].background || [])
    if (b.kind === "practice" && b.about === p) practice.add(b.text.split(": ")[0]);
  for (const t of practice) tip.push(t);
  if (q && q.range && typeof value === "number" && (value < q.range[0] - 1e-9 || value > q.range[1] + 1e-9)) {
    out = true;
    tip.push(`Outside the usual range of ${fmtShort(shown(p, q.range[0]))} to ${fmtShort(shown(p, q.range[1]))} ${ulabel(u)}.`);
  }
  if (D.objects[p] && w.given.has(p)) tip.push("Entered directly instead of calculated.");
  const html = tip.length ? `<span class="info${out ? " warn" : ""}" tabindex="0" data-tip="${esc(tip.join("\n"))}" aria-label="${esc(tip.join(". "))}">i</span>` : "";
  return {html, out, it};
}
function inputRow(p, value) {
  const [u] = unitOf(p), q = D.quantities[p], w = W(state.target), info = inputInfo(p, value), it = info.it;
  const sel = it && it.units.length > 1
    ? `<select data-unit="${esc(p)}" aria-label="Unit of ${esc(it.name)}">${it.units.map(x => `<option ${x[0] === u ? "selected" : ""}>${esc(x[0])}</option>`).join("")}</select>`
    : `<span class="u">${esc(ulabel(u))}</span>`;
  const choices = q && q.choices && q.choices.length;
  const list = choices ? `<datalist id="dl-${esc(p)}">${q.choices.map(ch => `<option value="${esc(fmtShort(shown(p, ch.value)))}" label="${esc(ch.label)}"></option>`).join("")}</datalist>` : "";
  const undo = D.objects[p] && w.given.has(p) ? `<button class="icon-btn" type="button" data-ungive="${esc(p)}" data-tip="Calculate this value instead" aria-label="Calculate ${esc(symText(p))} instead">↺</button>` : "";
  return `<div class="inp" data-row="${esc(p)}"><label for="in-${esc(p)}"><span>${esc(it ? it.name : p)}</span>${info.html}</label><span class="sym"><math>${symML(p)}</math></span>
    <div class="ctl"><input id="in-${esc(p)}" class="${info.out ? "out" : ""}" data-in="${esc(p)}" inputmode="decimal" autocomplete="off"${choices ? ` list="dl-${esc(p)}"` : ""} value="${value == null ? "" : esc(fmtShort(shown(p, value)))}">${sel}${undo}</div>${list}</div>`;
}
function renderInputs() {
  const id = state.target, o = D.objects[id], w = W(id), vals = valuesFor(id), {inputs} = plan(id, w.given);
  let h = `<h3>Input</h3>` + inputs.map(p => inputRow(p, vals[p])).join("");
  if (o.check) h += `<h3 class="sub">Design value to check</h3>` + inputRow(o.check, w.check);
  const fixed = Object.entries(o.fixed || {});
  if (fixed.length) h += `<p class="fixed">Fixed by ${esc(o.code)}: ${fixed.map(([k, v]) => `<math>${symML(k)}<mo>=</mo>${mathNum(v)}</math>`).join(", ")}</p>`;
  h += `<div class="btns"><button class="btn ghost" type="button" id="reset">Reset inputs</button></div>`;
  $("#inputs").innerHTML = h;
}
// one step of a calculation: equation, substituted values and result on one line
function subML(so, env) {
  return so.mlS.replace(/<mn class="slot" data-s="([^"]+)"><\/mn>/g, (m, s) => {
    const v = env[s], t = typeof v === "number" ? fmtShort(v) : String(v);
    return t.startsWith("-") ? `<mo>(</mo><mo>&#x2212;</mo><mn>${esc(t.slice(1))}</mn><mo>)</mo>` : `<mn>${esc(t)}</mn>`;
  });
}
function stepParts(target, t, detail) {
  const so = D.objects[t.id], [u] = unitOf(t.id), segs = [];
  if (detail !== "result") segs.push(so.mlF);
  if (detail === "full" && so.params.length) segs.push(subML(so, t.env));
  const ref = so.code === D.objects[target].code ? so.ref.replace(so.code + " ", "") : so.ref;
  return {so, segs, res: mathNum(shown(t.id, t.v)) + mathUnit(u), ref};
}
const chainHTML = p => `<div class="chain"><span class="seg"><math>${p.so.ml}</math></span>`
  + p.segs.map(s => `<span class="seg"><math displaystyle="true"><mo>=</mo>${s}</math></span>`).join("")
  + `<span class="seg res"><math><mo>=</mo>${p.res}</math></span></div>`;
function verdictOf(id, value, check) {
  const o = D.objects[id];
  if (!(o.check && check != null && typeof value === "number" && value !== 0)) return null;
  const eta = o.sense === "resistance" ? check / value : value / check;
  return {eta, ok: eta <= 1};
}
function verdictHTML(id, value, check) {
  const o = D.objects[id], v = verdictOf(id, value, check);
  let h = `<div class="verdict${v ? (v.ok ? " pass" : " fail") : ""}"><span><math>${o.ml}<mo>=</mo>${mathNum(shown(id, value))}${mathUnit(unitOf(id)[0])}</math></span>`;
  if (v) h += `<span><math>${symML(o.check)}<mo>=</mo>${mathNum(shown(o.check, check))}${mathUnit(unitOf(o.check)[0])}</math></span>`
    + `<span><math><mi>η</mi><mo>=</mo>${o.sense === "resistance" ? symML(o.check) + "<mo>/</mo>" + o.ml : o.ml + "<mo>/</mo>" + symML(o.check)}<mo>=</mo><mn>${v.eta.toFixed(2)}</mn></math></span>`
    + `<span class="badge ${v.ok ? "ok" : "bad"}">${v.ok ? "✓ OK" : "✗ Not OK"}</span>`;
  return h + `</div>`;
}
const COND = {ok: ["✓", "met", "Met"], violated: ["✗", "unmet", "Not met"], "not checked": ["?", "", "Not checked: a value it needs is not part of this calculation"]};
function renderSheet() {
  const id = state.target, w = W(id);
  let r;
  try { r = evaluate(id, valuesFor(id), w.given); }
  catch (e) { $("#sheet").innerHTML = `<p class="bad">${esc(e.message)}</p>`; return; }
  let h = `<div class="sheet-h"><h3>Calculation <span class="info" tabindex="0" data-tip="Substituted values are in N, mm and MPa. Results are in the units chosen in Settings.">i</span></h3>
    <div class="seg-ctl" role="group" aria-label="Detail">${DETAIL.map(([k, l]) => `<button type="button" data-detail="${k}" aria-pressed="${w.detail === k}">${l}</button>`).join("")}</div></div>`;
  for (const t of r.trace) {
    const p = stepParts(id, t, w.detail);
    const edit = t.id !== id ? `<button class="icon-btn" type="button" data-give="${esc(t.id)}" data-tip="Enter this value directly instead of calculating it" aria-label="Enter ${esc(p.so.text)} directly">✎</button>` : "";
    h += `<div class="st"><div><span class="nm">${esc(p.so.name)}</span><span class="cl">${esc(p.ref)}</span></div><div class="row">${chainHTML(p)}${edit}</div></div>`;
  }
  h += verdictHTML(id, r.value, w.check);
  const checks = checksFor(id, r.env, w.given);
  if (checks.length) h += `<div class="conds"><h4>Conditions</h4><ul>` + checks.map(c => {
    const m = COND[c.status];
    return `<li class="${m[1]}"><span class="mk" tabindex="0" data-tip="${esc(m[2])}" aria-label="${esc(m[2])}">${m[0]}</span><span>${esc(c.text)} <span class="muted">${esc(c.clause)}</span></span></li>`;
  }).join("") + `</ul></div>`;
  $("#sheet").innerHTML = h;
}

// ---------------------------------------------------------------- Cases and report
function cases() { return store.get("cases:" + state.target, []); }
function setCases(c) { store.set("cases:" + state.target, c); }
function caseResult(id, cs) {
  const v = Object.assign(defaults(id, new Set(cs.given || [])), cs.values);
  try {
    const r = evaluate(id, v, new Set(cs.given || []));
    return {r, values: v, eta: (verdictOf(id, r.value, cs.check) || {}).eta};
  } catch (e) { return {error: e.message}; }
}
function governing(id, res) {
  const o = D.objects[id];
  let gov = 0, best = null;
  res.forEach((x, i) => {
    if (x.error) return;
    const m = x.eta != null ? x.eta : (o.sense === "resistance" ? -x.r.value : x.r.value);
    if (best == null || m > best) { best = m; gov = i; }
  });
  return gov;
}
function currentCase(name) {
  const id = state.target, w = W(id), vals = valuesFor(id), {inputs} = plan(id, w.given), values = {};
  for (const p of inputs) {
    const q = D.quantities[p];
    if (w.entered.has(p) || !(q && q.kind === "coefficient")) values[p] = vals[p];
  }
  return {name, values, given: [...w.given], check: w.check};
}
function caseKeys(id, list) {
  const keys = [];
  for (const c of list) for (const k of Object.keys(c.values)) if (!keys.includes(k) && k !== D.objects[id].check) keys.push(k);
  return keys;
}
function casesTable(id, list, res, gov, editable) {
  const o = D.objects[id], keys = caseKeys(id, list);
  const th = k => `<th><math>${symML(k)}</math><small>${esc(ulabel(unitOf(k)[0])) || "&nbsp;"}</small></th>`;
  let h = `<div class="scroll"><table class="cases"><tr><th>Case</th>${keys.map(th).join("")}${th(id)}`
    + (o.check ? `${th(o.check)}<th><math><mi>η</mi></math><small>&nbsp;</small></th><th></th>` : "") + (editable ? `<th></th>` : "") + `</tr>`;
  list.forEach((c, i) => {
    const x = res[i];
    const name = editable ? `<button class="linkish" type="button" data-load="${i}" data-tip="Open this case on the Calculate tab">${esc(c.name)}</button>` : esc(c.name);
    const cells = keys.map(k => `<td>${k in c.values ? esc(fmt(shown(k, c.values[k]))) : "–"}</td>`).join("");
    const val = x.error ? `<td class="bad">${esc(x.error)}</td>` : `<td>${esc(fmt(shown(id, x.r.value)))}</td>`;
    const chk = o.check ? `<td>${c.check == null ? "–" : esc(fmt(shown(o.check, c.check)))}</td><td>${x.eta == null ? "–" : x.eta.toFixed(2)}</td><td>${x.eta == null ? "" : (x.eta <= 1 ? '<span class="ok">OK</span>' : '<span class="bad">Not OK</span>')}</td>` : "";
    const del = editable ? `<td><button class="icon-btn" type="button" data-del="${i}" aria-label="Remove ${esc(c.name)}" data-tip="Remove this case">×</button></td>` : "";
    h += `<tr class="${i === gov && list.length > 1 ? "gov" : ""}"><td>${name}</td>${cells}${val}${chk}${del}</tr>`;
  });
  return h + `</table></div>`;
}
function reportOpts() {
  const id = state.target, o = D.objects[id], w = W(id);
  if (!w.report) {
    const x = plan(id, w.given).inputs.find(p => D.quantities[p] && D.quantities[p].kind === "input") || "";
    w.report = {title: o.name, project: "", number: "", made_by: "", checked_by: "", calc: true, table: true, chart: false, x, detail: "full"};
  }
  return w.report;
}
function renderReport() {
  const id = state.target, w = W(id), rb = reportOpts(), list = cases(), {inputs} = plan(id, w.given);
  const res = list.map(c => caseResult(id, c)), gov = governing(id, res);
  const xs = inputs.filter(p => D.quantities[p] && D.quantities[p].kind === "input");
  const fld = (k, l, cls) => `<label class="${cls || ""}">${l}<input data-rb="${k}" value="${esc(rb[k])}"></label>`;
  const chk = (k, l) => `<label><input type="checkbox" data-rb="${k}" ${rb[k] ? "checked" : ""}>${l}</label>`;
  let h = `<div class="rep-grid"><section><h3>Cases <span class="info" tabindex="0" data-tip="Each case is a set of inputs. Set them on the Calculate tab and add them here. The governing case is highlighted.">i</span></h3>`;
  h += list.length ? casesTable(id, list, res, gov, true) : `<p class="empty">No cases yet. Without cases the report shows the inputs on the Calculate tab.</p>`;
  h += `<div class="btns"><button class="btn" type="button" id="add-case">Add current inputs as a case</button>${list.length ? `<button class="btn ghost" type="button" id="clear-cases">Remove all cases</button>` : ""}</div></section>`;
  h += `<section><h3>Report</h3><div class="form">${fld("title", "Title", "wide")}${fld("project", "Project")}${fld("number", "Calculation no.")}${fld("made_by", "Made by")}${fld("checked_by", "Checked by")}</div>
    <fieldset><legend>Contents</legend>${chk("calc", list.length > 1 ? "Calculation of the governing case" : "Calculation")}
      ${list.length > 1 ? chk("table", "Summary of all cases") : ""}
      <label><input type="checkbox" data-rb="chart" ${rb.chart ? "checked" : ""}>Chart against <select data-rb="x" aria-label="Chart against">${xs.map(p => `<option value="${esc(p)}" ${p === rb.x ? "selected" : ""}>${esc(item(p).name)}</option>`).join("")}</select></label></fieldset>
    <fieldset><legend>Detail of each step</legend><div class="seg-ctl" role="group" aria-label="Detail of each step">${DETAIL.map(([k, l]) => `<button type="button" data-rdetail="${k}" aria-pressed="${rb.detail === k}">${l}</button>`).join("")}</div></fieldset>
    <div class="btns"><button class="btn primary" type="button" id="rep-pdf">${ICON_DL}Download PDF</button><button class="btn primary" type="button" id="rep-docx">${ICON_DL}Download Word</button>
      <button class="btn ghost" type="button" id="rep-yaml" data-tip="A template for running many cases with the Python package: python -m ckb report --template">Batch template</button></div></section></div>`;
  $("#panel").innerHTML = h;
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
    h += `<div class="t-code" style="--cc:var(--gen)">Definitions used by every code</div>` + general.map(o =>
      `<button class="t-obj" type="button" data-id="${esc(o.id)}" aria-current="${state.view === "object" && state.target === o.id}">`
      + `${dot(o)}<span class="s">${esc(o.text)}</span><span class="n">${esc(o.name)}</span></button>`).join("");
  }
  for (const c of D.codes) {
    if (state.code !== "all" && state.code !== c.code) continue;
    h += `<div class="t-code" style="--cc:${codeColor(c.code)}">${esc(c.code)}${c.title ? `<small>${esc(c.title)}</small>` : ""}</div>`;
    let chap = null, sec = null;
    for (const e of entries(c.code)) {
      const ch = e.topic.split(".")[0];
      if (ch !== chap) { chap = ch; sec = null; h += `<div class="t-chap">${esc(topicTitle(c.code, ch))}</div>`; }
      if (e.topic !== ch && e.topic !== sec) { sec = e.topic; h += `<div class="t-sec">${esc(topicTitle(c.code, e.topic))}</div>`; }
      const o = D.objects[e.id];
      h += `<button class="t-obj" type="button" data-id="${esc(e.id)}" aria-current="${state.view === "object" && state.target === e.id}">`
        + `${dot(o)}<span class="s">${esc(e.label)}</span><span class="n">${esc(e.via ? "From " + e.via : e.name)}</span></button>`;
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
    if (key && e.keys.includes(key)) { hits.push([100, id, "Symbol"]); continue; }
    if (q === (o.ref.match(/cl\. ([^,]+)/) || [])[1]) { hits.push([90, id, "Clause"]); continue; }
    if (!tokens.length) continue;
    let score = 0, found = 0, weak = false;
    for (const t of tokens) for (const [f, w] of FIELDS) { if (hitWord(t, e[f].split(" "))) { score += w; found++; weak = weak || f === "weak"; break; } }
    if (!found) continue;
    score = score / tokens.length + (found === tokens.length ? 20 : 5 * found / tokens.length) + 1.5 * e.rank;
    hits.push([score, id, (found === tokens.length ? "All words" : `${found} of ${tokens.length} words`) + (weak ? ", partly in the background" : "")]);
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

// ---------------------------------------------------------------- files: zip, downloads
// Excel calculators and Mathcad worksheets are embedded in the page (python -m ckb share), so nobody
// needs Python. Zip packages are read and written here with the browser's own (de)compression.
const b64bytes = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
const CRC_T = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function crc32(b) { let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = CRC_T[(c ^ b[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
async function streamBytes(bytes, stream) { return new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(stream)).arrayBuffer()); }
async function deflateRaw(b) { try { return typeof CompressionStream === "undefined" ? null : await streamBytes(b, new CompressionStream("deflate-raw")); } catch (e) { return null; } }
async function inflateRaw(b) { if (typeof DecompressionStream === "undefined") throw new Error("this browser cannot unpack the file"); return streamBytes(b, new DecompressionStream("deflate-raw")); }
async function zipRead(bytes) {
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength), dec = new TextDecoder(), out = [];
  let e = bytes.length - 22;
  while (e >= 0 && v.getUint32(e, true) !== 0x06054b50) e--;
  if (e < 0) throw new Error("not a zip package");
  let p = v.getUint32(e + 16, true);
  for (let i = 0, n = v.getUint16(e + 10, true); i < n; i++) {
    const method = v.getUint16(p + 10, true), csize = v.getUint32(p + 20, true), nlen = v.getUint16(p + 28, true);
    const name = dec.decode(bytes.subarray(p + 46, p + 46 + nlen)), lh = v.getUint32(p + 42, true);
    const start = lh + 30 + v.getUint16(lh + 26, true) + v.getUint16(lh + 28, true), raw = bytes.subarray(start, start + csize);
    out.push([name, method === 8 ? await inflateRaw(raw) : raw.slice()]);
    p += 46 + nlen + v.getUint16(p + 30, true) + v.getUint16(p + 32, true);
  }
  return out;
}
async function zipWrite(files) {
  const enc = new TextEncoder(), parts = [], central = [], now = new Date();
  const time = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
  const date = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
  let off = 0;
  for (let [name, data] of files) {
    if (typeof data === "string") data = enc.encode(data);
    const nm = enc.encode(name), crc = crc32(data);
    let body = await deflateRaw(data), method = 8;
    if (!body || body.length >= data.length) { body = data; method = 0; }
    const h = new DataView(new ArrayBuffer(30));
    [[0, 0x04034b50, 4], [4, 20, 2], [6, 0, 2], [8, method, 2], [10, time, 2], [12, date, 2], [14, crc, 4], [18, body.length, 4], [22, data.length, 4], [26, nm.length, 2], [28, 0, 2]]
      .forEach(([o, x, s]) => s === 4 ? h.setUint32(o, x, true) : h.setUint16(o, x, true));
    const c = new DataView(new ArrayBuffer(46));
    [[0, 0x02014b50, 4], [4, 20, 2], [6, 20, 2], [8, 0, 2], [10, method, 2], [12, time, 2], [14, date, 2], [16, crc, 4], [20, body.length, 4], [24, data.length, 4], [28, nm.length, 2], [42, off, 4]]
      .forEach(([o, x, s]) => s === 4 ? c.setUint32(o, x, true) : c.setUint16(o, x, true));
    parts.push(new Uint8Array(h.buffer), nm, body);
    central.push(new Uint8Array(c.buffer), nm);
    off += 30 + nm.length + body.length;
  }
  const size = central.reduce((s, b) => s + b.length, 0), end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, files.length, true); end.setUint16(10, files.length, true);
  end.setUint32(12, size, true); end.setUint32(16, off, true);
  return new Uint8Array(await new Blob(parts.concat(central, [new Uint8Array(end.buffer)])).arrayBuffer());
}
async function claudeCap(name) {
  try { return window.claude && window.claude.use ? await window.claude.use(name) : null; } catch (e) { return null; }
}
async function saveFile(filename, data, mime) {
  const dl = await claudeCap("downloads");             // inside claude.ai: the viewer confirms each file
  if (dl) {
    try { await dl.save({filename, data: data instanceof Uint8Array ? new Blob([data], {type: mime}) : data}); return "saved"; }
    catch (e) { return e && e.code === "declined" ? "declined" : `Not saved (${(e && e.code) || "error"}).`; }
  }
  const blob = data instanceof Blob ? data : new Blob([data], {type: mime});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
  return "saved";
}
async function busy(btn, job) {
  if (btn) btn.disabled = true;
  try { await job(); } catch (e) { toast("The file could not be prepared: " + (e && e.message || e)); }
  finally { if (btn) btn.disabled = false; }
}
async function excelBytes(id) {
  const f = D.files[id], w = W(id), bytes = b64bytes(f.xlsx);
  if (w.given.size) return [bytes, "with example inputs, because a value was entered directly"];
  let files;
  try { files = await zipRead(bytes); } catch (e) { return [bytes, "with example inputs"]; }
  const vals = valuesFor(id), chk = D.objects[id].check, dec = new TextDecoder();
  const put = (xml, cell, v) => xml.replace(new RegExp('<c r="' + cell + '"([^>]*?)(?:/>|>[\\s\\S]*?</c>)'),
    (m, a) => `<c r="${cell}"${a.replace(/\s*t="[^"]*"/, "")} t="n"><v>${v}</v></c>`);
  files = files.map(([name, data]) => {
    if (name !== "xl/worksheets/sheet1.xml") return [name, data];
    let xml = dec.decode(data);
    for (const [sid, cell] of Object.entries(f.cells))
      if (!D.objects[sid] && typeof vals[sid] === "number") xml = put(xml, cell, +(vals[sid] / item(sid).units[0][1]).toPrecision(12));
    if (f.check && chk && w.check != null) xml = put(xml, f.check, +(w.check / item(chk).units[0][1]).toPrecision(12));
    return [name, xml];
  });
  return [await zipWrite(files), "with the inputs on the page"];
}
async function downloadExcel(btn) {
  const id = state.target;
  await busy(btn, async () => {
    const [bytes, how] = await excelBytes(id);
    const r = await saveFile(`${id}_calculator.xlsx`, bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    toast(r === "saved" ? `Excel calculator saved ${how}.` : r === "declined" ? "" : r);
  });
}
async function downloadMathcad(btn) {
  const id = state.target;
  await busy(btn, async () => {
    const bytes = b64bytes(D.files[id].mcdx);
    if (await claudeCap("downloads")) {        // claude.ai saves .zip but not .mcdx files
      const r = await saveFile(`${id}_mathcad.zip`, await zipWrite([[`${id}.mcdx`, bytes]]), "application/zip");
      toast(r === "saved" ? "Mathcad worksheet saved in a zip. Extract it (right-click, Extract All) and open the .mcdx file in Mathcad Prime." : r === "declined" ? "" : r);
    } else {
      const r = await saveFile(`${id}.mcdx`, bytes, "application/octet-stream");
      toast(r === "saved" ? "Mathcad Prime worksheet saved, with example inputs." : r);
    }
  });
}
function yamlNum(id, v) {
  const x = +(v / item(id).units[0][1]).toPrecision(8);
  return Number.isInteger(x) || Math.abs(x) >= 1e-4 ? String(x) : x.toExponential(6);   // YAML reads 1.0e-07, not 1e-7
}
function templateYAML() {
  const id = state.target, o = D.objects[id], rb = reportOpts();
  let list = cases();
  if (!list.length) list = [currentCase("Case 1")];
  const q = v => JSON.stringify(String(v || ""));
  const show = {full: "[equation, substituted, result]", equations: "[equation, result]", result: "[result]"}[rb.detail || "full"];
  const L = [`# Report template for ${o.text} (${o.ref}).`, `# Run: python -m ckb report --template ${id}_report_template.txt --pdf --docx`,
    `title: ${q(rb.title)}`, `project: ${q(rb.project)}`, `number: ${q(rb.number)}`, `made_by: ${q(rb.made_by)}`, `checked_by: ${q(rb.checked_by)}`,
    `style:`, `  decimals: ${S.decimals}`, `  min_significant: ${S.minsig}`,
    `  units: {${Object.entries(S.units).filter(([k]) => item(k)).map(([k, u]) => `${k}: ${u}`).join(", ")}}`, `cases:`];
  for (const c of list) {
    const cells = [`case: ${JSON.stringify(c.name)}`].concat(Object.entries(c.values).map(([k, v]) => `${k}: ${yamlNum(k, v)}`));
    if (o.check && c.check != null) cells.push(`${o.check}: ${yamlNum(o.check, c.check)}`);
    L.push(`  - {${cells.join(", ")}}`);
  }
  L.push(`blocks:`, `  - heading: ${q(rb.title)}`);
  if (rb.calc) L.push(`  - calc: ${id}`, `    case: governing`, `    show: ${show}`);
  if (rb.table && list.length > 1) L.push(`  - table: ${id}`, `    sort: ${o.check ? "utilisation desc" : ""}`);
  if (rb.chart && rb.x) L.push(`  - chart: ${id}`, `    x: ${rb.x}`);
  return L.join("\n") + "\n";
}

// ---------------------------------------------------------------- reports: one layout, printed as PDF (HTML) and Word
function reportData() {
  const id = state.target, o = D.objects[id], rb = reportOpts();
  let list = cases();
  const single = !list.length;
  if (single) list = [currentCase("Calculation")];
  const res = list.map(c => caseResult(id, c)), gov = governing(id, res), x = res[gov];
  if (x.error) throw new Error(x.error);
  const {inputs, steps} = plan(id, new Set(list[gov].given || []));
  const detail = rb.detail || "full";
  const rows = x.r.trace.map(t => stepParts(id, t, detail));
  const checks = checksFor(id, x.r.env, new Set(list[gov].given || []));
  const v = verdictOf(id, x.r.value, list[gov].check);
  const date = new Date().toISOString().slice(0, 10);
  const versions = steps.map(s => `ckb ${s} ${D.objects[s].version}`).join(" ");
  return {id, o, rb, list, res, gov, x, inputs, rows, checks, v, date, versions, single, detail};
}
function sweep(R) {
  const id = R.id, c = R.list[R.gov], given = new Set(c.given || []), xq = R.rb.x, q = D.quantities[xq];
  if (!R.rb.chart || !xq || !q) return null;
  const x0 = R.x.values[xq];
  let lo = q.range ? q.range[0] : 0.5 * (x0 || 1), hi = q.range ? q.range[1] : 1.5 * (x0 || 1);
  if (typeof x0 === "number") { lo = Math.min(lo, x0); hi = Math.max(hi, x0); }
  const xs = [], ys = [];
  for (let i = 0; i <= 60; i++) {
    const xv = lo + (hi - lo) * i / 60, vals = Object.assign({}, R.x.values, {[xq]: xv});
    try { const r = evaluate(id, vals, given); if (typeof r.value === "number") { xs.push(shown(xq, xv)); ys.push(shown(id, r.value)); } } catch (e) {}
  }
  if (!xs.length) return null;
  const ref = R.o.check && c.check != null ? {label: symText(R.o.check), y: shown(R.o.check, c.check)} : null;
  return {xs, ys, ref, marker: [shown(xq, x0), shown(id, R.x.r.value)], xLabel: `${item(xq).name} [${ulabel(unitOf(xq)[0])}]`, yLabel: `${R.o.text} [${ulabel(unitOf(id)[0])}]`};
}
function staticChart(ch) {      // plain SVG with fixed colours, for the printed report and Word
  const W = 640, H = 300, ml = 62, mr = 18, mt = 16, mb = 46, pw = W - ml - mr, ph = H - mt - mb;
  const all = ch.ys.concat(ch.ref ? [ch.ref.y] : []);
  let y0 = Math.min(0, ...all), y1 = Math.max(...all) * 1.08 || 1;
  const yt = nice(y0, y1, 5); y0 = Math.min(y0, yt[0]); y1 = Math.max(y1, yt[yt.length - 1]);
  const x0 = ch.xs[0], x1 = ch.xs[ch.xs.length - 1], xt = nice(x0, x1, 6);
  const sx = v => ml + (v - x0) / (x1 - x0 || 1) * pw, sy = v => mt + ph - (v - y0) / (y1 - y0 || 1) * ph;
  let s = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" font-family="Arial, Helvetica, sans-serif">`;
  s += `<rect width="${W}" height="${H}" fill="#ffffff"/>`;
  for (const t of yt) s += `<line x1="${ml}" x2="${ml + pw}" y1="${sy(t)}" y2="${sy(t)}" stroke="#e3e8eb"/><text x="${ml - 7}" y="${sy(t) + 4}" text-anchor="end" font-size="11" fill="#5f6d76">${tick(t)}</text>`;
  for (const t of xt) if (t >= x0 - 1e-9 && t <= x1 + 1e-9) s += `<text x="${sx(t)}" y="${mt + ph + 17}" text-anchor="middle" font-size="11" fill="#5f6d76">${tick(t)}</text>`;
  s += `<line x1="${ml}" x2="${ml + pw}" y1="${mt + ph}" y2="${mt + ph}" stroke="#5f6d76"/>`;
  s += `<text x="${ml + pw / 2}" y="${H - 8}" text-anchor="middle" font-size="12" fill="#14212a">${esc(ch.xLabel)}</text>`;
  s += `<text x="12" y="${mt + ph / 2}" text-anchor="middle" font-size="12" fill="#14212a" transform="rotate(-90 12 ${mt + ph / 2})">${esc(ch.yLabel)}</text>`;
  if (ch.ref) s += `<line x1="${ml}" x2="${ml + pw}" y1="${sy(ch.ref.y)}" y2="${sy(ch.ref.y)}" stroke="#14212a" stroke-dasharray="5 4"/><text x="${ml + pw - 2}" y="${sy(ch.ref.y) - 6}" text-anchor="end" font-size="11" fill="#14212a">${esc(ch.ref.label)} = ${esc(fmt(ch.ref.y))}</text>`;
  s += `<path d="${ch.xs.map((x, i) => (i ? "L" : "M") + sx(x).toFixed(1) + "," + sy(ch.ys[i]).toFixed(1)).join("")}" fill="none" stroke="#2a78d6" stroke-width="2.2" stroke-linejoin="round"/>`;
  if (ch.marker && isFinite(ch.marker[1])) s += `<circle cx="${sx(ch.marker[0])}" cy="${sy(ch.marker[1])}" r="5" fill="#2a78d6" stroke="#ffffff" stroke-width="2"/>`;
  return s + `</svg>`;
}
const REPORT_CSS = `@page{size:A4;margin:16mm 15mm 18mm}
body{margin:0;background:#e9eef0;color:#14212a;font:10.5pt/1.45 "IBM Plex Sans","Segoe UI",Arial,sans-serif}
.sheet{background:#fff;max-width:210mm;margin:14px auto;padding:16mm 15mm;box-shadow:0 1px 6px rgba(0,0,0,.15)}
.bar{max-width:210mm;margin:14px auto 0;display:flex;justify-content:flex-end}
.bar button{font:inherit;background:#0f6b80;color:#fff;border:0;border-radius:8px;padding:8px 16px;cursor:pointer}
math{font-family:"Cambria Math","STIX Two Math","Latin Modern Math",math;font-size:1.08em}
table.tb{width:100%;border-collapse:collapse;margin-bottom:7mm;font-size:9.5pt} table.tb td{border:1px solid #14212a;padding:3px 7px;width:33%;vertical-align:top}
table.tb small{display:block;color:#5f6d76;font-size:7pt;letter-spacing:.06em;text-transform:uppercase}
h1{font-size:16pt;margin:0 0 1mm;color:#0f4757} h2{font-size:12.5pt;margin:6mm 0 1mm} h3{font-size:11pt;margin:6mm 0 2mm;color:#0f6b80;border-bottom:1px solid #d2dbe0;padding-bottom:1mm}
.ref{color:#5f6d76;margin:0 0 2mm} .gov{margin:1mm 0 0}
.inputs{display:grid;grid-template-columns:1fr 1fr;column-gap:10mm}
.inputs div{display:flex;justify-content:space-between;gap:4mm;padding:1.2mm 0;border-bottom:1px solid #edf1f3;break-inside:avoid}
.inputs span{color:#3c4b56}
.st{display:grid;grid-template-columns:30% 1fr;gap:2mm 6mm;padding:2mm 0;border-bottom:1px solid #edf1f3;break-inside:avoid;align-items:center}
.st .cl{display:block;color:#5f6d76;font-size:8.5pt}
.chain{display:flex;flex-wrap:wrap;align-items:center;column-gap:.5em;row-gap:2mm}
.chain .seg{white-space:nowrap} .chain .res math{font-weight:700}
.verdict{margin:5mm 0 2mm;padding:3mm 4mm;border:1.5px solid #14212a;border-radius:2mm;display:flex;flex-wrap:wrap;gap:2mm 8mm;align-items:center;break-inside:avoid}
.verdict.pass{border-color:#1e8e3e;background:#f1f9f3} .verdict.fail{border-color:#c5221f;background:#fdf1f0}
.badge{font-weight:700} .verdict.pass .badge{color:#1e7a35} .verdict.fail .badge{color:#b3201d}
ul.conds{list-style:none;padding:0;margin:2mm 0} ul.conds li{display:flex;gap:3mm;padding:.5mm 0} ul.conds .m{min-width:5.5em;font-weight:600}
table.sum{width:100%;border-collapse:collapse;font-size:9.5pt} table.sum th,table.sum td{border-bottom:1px solid #d2dbe0;padding:1.2mm 2mm;text-align:right;white-space:nowrap}
table.sum th:first-child,table.sum td:first-child{text-align:left} table.sum th{border-bottom:1.5px solid #14212a;font-weight:600} table.sum small{display:block;font-weight:400;color:#5f6d76}
table.sum tr.g td{background:#e0eff3;font-weight:600}
.chart svg{width:100%;height:auto;display:block}
@media print{body{background:#fff}.sheet{box-shadow:none;margin:0;max-width:none;padding:0}.bar{display:none}}`;
function reportHTML(R) {
  const o = R.o, rb = R.rb, title = rb.title || o.name;
  const inp = R.inputs.map(p => `<div><span>${esc(item(p) ? item(p).name : p)}</span><math>${symML(p)}<mo>=</mo>${mathNum(shown(p, R.x.values[p]))}${mathUnit(unitOf(p)[0])}</math></div>`).join("");
  const conds = R.checks.length ? `<ul class="conds">${R.checks.map(c => `<li><span class="m">${COND[c.status][2].split(":")[0]}</span><span>${esc(c.text)} (${esc(c.clause)})</span></li>`).join("")}</ul>` : "";
  let body = `<table class="tb"><tr><td><small>Project</small>${esc(rb.project)}&nbsp;</td><td><small>Subject</small>${esc(title)}</td><td><small>Calculation no.</small>${esc(rb.number)}&nbsp;</td></tr>`
    + `<tr><td><small>Made by / date</small>${esc(rb.made_by)} ${R.date}</td><td><small>Checked by / date</small>${esc(rb.checked_by)}&nbsp;</td><td><small>Approved by / date</small>&nbsp;</td></tr></table>`
    + `<h1>${esc(title)}</h1><p class="ref">${esc(o.ref)}</p>`;
  if (rb.calc) {
    body += (title !== o.name ? `<h2><math>${o.ml}</math> ${esc(o.name)}</h2>` : "") + (R.list.length > 1 ? `<p class="gov">Governing case: ${esc(R.list[R.gov].name)}</p>` : "")
      + `<h3>Input</h3><div class="inputs">${inp}</div><h3>Calculation</h3>`
      + R.rows.map(p => `<div class="st"><div>${esc(p.so.name)}<span class="cl">${esc(p.ref)}</span></div>${chainHTML(p)}</div>`).join("")
      + verdictHTML(R.id, R.x.r.value, R.list[R.gov].check) + conds;
  }
  if (rb.table && R.list.length > 1) {
    const keys = caseKeys(R.id, R.list), th = k => `<th><math>${symML(k)}</math><small>${esc(ulabel(unitOf(k)[0])) || "&nbsp;"}</small></th>`;
    const order = R.list.map((c, i) => i).sort((a, b) => (R.res[b].eta || 0) - (R.res[a].eta || 0));
    body += `<h3>Summary of all cases</h3><table class="sum"><tr><th>Case</th>${keys.map(th).join("")}${th(R.id)}${o.check ? th(o.check) + "<th><math><mi>η</mi></math><small>&nbsp;</small></th><th></th>" : ""}</tr>`
      + order.map(i => {
        const c = R.list[i], x = R.res[i];
        return `<tr class="${i === R.gov ? "g" : ""}"><td>${esc(c.name)}</td>${keys.map(k => `<td>${k in c.values ? esc(fmt(shown(k, c.values[k]))) : "–"}</td>`).join("")}`
          + `<td>${x.error ? "–" : esc(fmt(shown(R.id, x.r.value)))}</td>`
          + (o.check ? `<td>${c.check == null ? "–" : esc(fmt(shown(o.check, c.check)))}</td><td>${x.eta == null ? "–" : x.eta.toFixed(2)}</td><td>${x.eta == null ? "" : x.eta <= 1 ? "OK" : "Not OK"}</td>` : "") + `</tr>`;
      }).join("") + `</table>`;
  }
  const ch = sweep(R);
  if (ch) body += `<h3>${esc(o.name)} against ${esc(item(rb.x).name.toLowerCase())}</h3><div class="chart">${staticChart(ch)}</div>`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">`
    + `<meta name="generator" content="${esc(R.versions)}"><title>${esc(title)}</title><style>${REPORT_CSS}</style></head><body>`
    + `<div class="bar"><button type="button" onclick="window.print()">Print or save as PDF</button></div><div class="sheet">${body}</div></body></html>`;
}
async function reportPDF(btn) {
  await busy(btn, async () => {
    const R = reportData(), html = reportHTML(R), name = `${R.id}_report.html`;
    if (!(await claudeCap("downloads"))) {
      const win = window.open("", "_blank");
      if (win) {
        win.document.open(); win.document.write(html); win.document.close();
        setTimeout(() => { try { win.focus(); win.print(); } catch (e) {} }, 900);
        toast("The report opened in a new tab. Choose “Save as PDF” as the printer.");
        return;
      }
    }
    const r = await saveFile(name, html, "text/html");
    toast(r === "saved" ? "Report saved. Open it in your browser and press “Print or save as PDF”." : r === "declined" ? "" : r);
  });
}

// Word: the same layout with native, editable equations (Office Math) converted from the MathML
const XE = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
function omml(ml) {
  const doc = new DOMParser().parseFromString(`<math xmlns="http://www.w3.org/1998/Math/MathML">${ml}</math>`, "application/xml");
  const run = (text, upright) => text ? `<m:r>${upright ? '<m:rPr><m:sty m:val="p"/></m:rPr>' : ""}<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/></w:rPr><m:t xml:space="preserve">${XE(text)}</m:t></m:r>` : "";
  const kids = n => [...n.children].map(go).join("");
  function go(n) {
    const tag = n.localName, kid = [...n.children];
    if (tag === "mi") return run(n.textContent, n.getAttribute("mathvariant") === "normal" || n.textContent.length > 1);
    if (tag === "mn" || tag === "mtext") return run(n.textContent.replace(/ /g, " "), true);
    if (tag === "mo") return run(n.textContent.replace(/⁡/g, ""), true);
    if (tag === "msub") return `<m:sSub><m:e>${go(kid[0])}</m:e><m:sub>${go(kid[1])}</m:sub></m:sSub>`;
    if (tag === "msup") return `<m:sSup><m:e>${go(kid[0])}</m:e><m:sup>${go(kid[1])}</m:sup></m:sSup>`;
    if (tag === "mfrac") return `<m:f><m:num>${go(kid[0])}</m:num><m:den>${go(kid[1])}</m:den></m:f>`;
    if (tag === "msqrt") return `<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>${kids(n)}</m:e></m:rad>`;
    if (tag === "mtable") return `<m:eqArr>${kid.map(r => `<m:e>${[...r.children].map(kids).join(run("  ", true))}</m:e>`).join("")}</m:eqArr>`;
    return kids(n);
  }
  return kids(doc.documentElement);
}
const wRun = (t, o = {}) => `<w:r><w:rPr>${o.b ? "<w:b/>" : ""}${o.color ? `<w:color w:val="${o.color}"/>` : ""}${o.sz ? `<w:sz w:val="${o.sz}"/>` : ""}</w:rPr><w:t xml:space="preserve">${XE(t)}</w:t></w:r>`;
const wP = (inner, style, o = {}) => `<w:p><w:pPr>${style ? `<w:pStyle w:val="${style}"/>` : ""}${o.keep ? "<w:keepNext/>" : ""}${o.shade ? `<w:shd w:val="clear" w:color="auto" w:fill="${o.shade}"/>` : ""}${o.after != null ? `<w:spacing w:after="${o.after}"/>` : ""}</w:pPr>${inner}</w:p>`;
const wMath = ml => `<m:oMath>${omml(ml)}</m:oMath>`;
function wTable(rows, o = {}) {
  const border = o.grid ? `<w:tblBorders>${["top", "left", "bottom", "right", "insideH", "insideV"].map(b => `<w:${b} w:val="single" w:sz="6" w:color="14212A"/>`).join("")}</w:tblBorders>`
    : `<w:tblBorders><w:top w:val="single" w:sz="8" w:color="14212A"/><w:bottom w:val="single" w:sz="6" w:color="D2DBE0"/><w:insideH w:val="single" w:sz="4" w:color="D2DBE0"/></w:tblBorders>`;
  const n = rows[0].cells.length, cw = Math.floor(9864 / n);
  return `<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>${border}<w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr>`
    + `<w:tblGrid>${`<w:gridCol w:w="${cw}"/>`.repeat(n)}</w:tblGrid>`
    + rows.map((r, i) => `<w:tr>${r.cells.map((c, j) => `<w:tc><w:tcPr>${r.fill ? `<w:shd w:val="clear" w:color="auto" w:fill="${r.fill}"/>` : ""}</w:tcPr><w:p><w:pPr><w:spacing w:before="20" w:after="20"/>${j && o.right ? '<w:jc w:val="right"/>' : ""}</w:pPr>${c}</w:p></w:tc>`).join("")}</w:tr>`).join("")
    + `</w:tbl>`;
}
async function svgPng(svg, w, h) {
  const img = new Image();
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  await img.decode();
  const c = document.createElement("canvas"); c.width = w * 2; c.height = h * 2;
  const g = c.getContext("2d"); g.scale(2, 2); g.drawImage(img, 0, 0, w, h);
  const blob = await new Promise(res => c.toBlob(res, "image/png"));
  return new Uint8Array(await blob.arrayBuffer());
}
async function reportDocx(R) {
  const o = R.o, rb = R.rb, title = rb.title || o.name, B = [];
  const cell = (k, v) => wRun(k.toUpperCase(), {sz: 14, color: "5F6D76"}) + "<w:br/>" + wRun(v || " ");
  B.push(wTable([{cells: [cell("Project", rb.project), cell("Subject", title), cell("Calculation no.", rb.number)]},
    {cells: [cell("Made by / date", `${rb.made_by} ${R.date}`), cell("Checked by / date", rb.checked_by), cell("Approved by / date", "")]}], {grid: true}));
  B.push(wP(wRun(title), "Title"), wP(wRun(o.ref, {color: "5F6D76"}), null, {after: 160}));
  if (rb.calc) {
    if (title !== o.name) B.push(wP(wMath(o.ml) + wRun("  " + o.name), "Heading1"));
    if (R.list.length > 1) B.push(wP(wRun("Governing case: " + R.list[R.gov].name)));
    B.push(wP(wRun("Input"), "Heading2"));
    B.push(wTable(R.inputs.map(p => ({cells: [wRun(item(p) ? item(p).name : p), wMath(`${symML(p)}<mo>=</mo>${mathNum(shown(p, R.x.values[p]))}${mathUnit(unitOf(p)[0])}`)]})), {right: true}));
    B.push(wP(wRun("Calculation"), "Heading2"));
    for (const p of R.rows) {
      B.push(wP(wRun(p.so.name) + wRun("   " + p.ref, {color: "5F6D76", sz: 17}), null, {keep: true, after: 20}));
      B.push(wP(wMath(`${p.so.ml}${p.segs.map(s => "<mo>=</mo>" + s).join("")}<mo>=</mo>${p.res}`), null, {after: 120}));
    }
    const v = R.v;
    let line = `${o.ml}<mo>=</mo>${mathNum(shown(R.id, R.x.r.value))}${mathUnit(unitOf(R.id)[0])}`;
    if (v) line += `<mtext>    </mtext><mi>η</mi><mo>=</mo>${o.sense === "resistance" ? symML(o.check) + "<mo>/</mo>" + o.ml : o.ml + "<mo>/</mo>" + symML(o.check)}<mo>=</mo><mn>${v.eta.toFixed(2)}</mn>`;
    B.push(wP(wMath(line) + (v ? wRun(v.ok ? "   OK" : "   Not OK", {b: true, color: v.ok ? "1E7A35" : "B3201D"}) : ""), null, {shade: v ? (v.ok ? "F1F9F3" : "FDF1F0") : "F5F8F9"}));
    for (const c of R.checks) B.push(wP(wRun(COND[c.status][2].split(":")[0] + ": ", {b: true}) + wRun(`${c.text} (${c.clause})`)));
  }
  if (rb.table && R.list.length > 1) {
    const keys = caseKeys(R.id, R.list), head = k => wMath(symML(k)) + (ulabel(unitOf(k)[0]) ? wRun(` [${unitOf(k)[0]}]`, {sz: 16, color: "5F6D76"}) : "");
    const order = R.list.map((c, i) => i).sort((a, b) => (R.res[b].eta || 0) - (R.res[a].eta || 0));
    B.push(wP(wRun("Summary of all cases"), "Heading2"));
    B.push(wTable([{cells: [wRun("Case", {b: true})].concat(keys.map(head), [head(R.id)], o.check ? [head(o.check), wMath("<mi>η</mi>"), wRun("")] : [])}].concat(order.map(i => {
      const c = R.list[i], x = R.res[i];
      return {fill: i === R.gov ? "E0EFF3" : null, cells: [wRun(c.name)].concat(keys.map(k => wRun(k in c.values ? fmt(shown(k, c.values[k])) : "–")),
        [wRun(x.error ? "–" : fmt(shown(R.id, x.r.value)))], o.check ? [wRun(c.check == null ? "–" : fmt(shown(o.check, c.check))), wRun(x.eta == null ? "–" : x.eta.toFixed(2)), wRun(x.eta == null ? "" : x.eta <= 1 ? "OK" : "Not OK")] : [])};
    })), {right: true}));
  }
  const files = [], rels = [`<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>`,
    `<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>`];
  const ch = sweep(R);
  if (ch) {
    try {
      const png = await svgPng(staticChart(ch), 640, 300), cx = 5760000, cy = Math.round(cx * 300 / 640);
      files.push(["word/media/chart.png", png]);
      rels.push(`<Relationship Id="rIdChart" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/chart.png"/>`);
      B.push(wP(wRun(`${o.name} against ${item(rb.x).name.toLowerCase()}`), "Heading2"));
      B.push(`<w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="${cx}" cy="${cy}"/><wp:docPr id="1" name="Chart"/><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="1" name="chart.png"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rIdChart"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>`);
    } catch (e) { /* the chart is left out when the browser cannot draw it */ }
  }
  const NS = `xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"`;
  const doc = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ${NS}><w:body>${B.join("")}<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1021" w:right="1021" w:bottom="1134" w:left="1021" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr></w:body></w:document>`;
  const style = (id, name, rpr, ppr = "") => `<w:style w:type="paragraph" w:styleId="${id}"><w:name w:val="${name}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/>${ppr}</w:pPr><w:rPr>${rpr}</w:rPr></w:style>`;
  const styles = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="21"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="60" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>`
    + `<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>`
    + style("Title", "Title", `<w:b/><w:color w:val="0F4757"/><w:sz w:val="34"/>`, `<w:spacing w:before="240" w:after="40"/>`)
    + style("Heading1", "heading 1", `<w:b/><w:sz w:val="26"/>`, `<w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="0"/>`)
    + style("Heading2", "heading 2", `<w:b/><w:color w:val="0F6B80"/><w:sz w:val="22"/>`, `<w:pBdr><w:bottom w:val="single" w:sz="4" w:space="1" w:color="D2DBE0"/></w:pBdr><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="1"/>`)
    + `</w:styles>`;
  const footer = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:pPr><w:jc w:val="right"/></w:pPr>${wRun("Page ", {sz: 16, color: "5F6D76"})}<w:fldSimple w:instr="PAGE">${wRun("1", {sz: 16, color: "5F6D76"})}</w:fldSimple>${wRun(" of ", {sz: 16, color: "5F6D76"})}<w:fldSimple w:instr="NUMPAGES">${wRun("1", {sz: 16, color: "5F6D76"})}</w:fldSimple></w:p></w:ftr>`;
  const core = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>${XE(title)}</dc:title><dc:description>${XE(R.versions)}</dc:description></cp:coreProperties>`;
  return zipWrite([
    ["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>`],
    ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>`],
    ["word/_rels/document.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${rels.join("")}</Relationships>`],
    ["word/document.xml", doc], ["word/styles.xml", styles], ["word/footer1.xml", footer], ["docProps/core.xml", core]].concat(files));
}
async function reportWord(btn) {
  await busy(btn, async () => {
    const R = reportData();
    const r = await saveFile(`${R.id}_report.docx`, await reportDocx(R), "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
    toast(r === "saved" ? "Word report saved. The equations can be edited in Word." : r === "declined" ? "" : r);
  });
}
async function batchTemplate(btn) {
  await busy(btn, async () => {
    const name = `${state.target}_report_template.txt`;   // YAML; claude.ai saves .txt but not .yaml files
    const r = await saveFile(name, templateYAML(), "text/plain");
    toast(r === "saved" ? `Batch template saved. Run it with: python -m ckb report --template ${name} --pdf --docx` : r === "declined" ? "" : r);
  });
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
  if (b.kind === "practice") refs = b.from === "engineer" ? "Answer from an engineer" : "From the source calculations";
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
  h += `<h4>Dependency map</h4><div class="depmap" id="depmap"></div>`;
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
    <label>Vary <select id="cx">${nums.map(p => `<option value="${esc(p)}" ${p === c.x ? "selected" : ""}>${esc(symText(p))} – ${esc(item(p).name)}</option>`).join("")}</select></label>
    <label>From [${esc(ulabel(ux))}]<input id="clo" inputmode="decimal" value="${esc(fmtShort(shown(c.x, lo)))}"></label>
    <label>To [${esc(ulabel(ux))}]<input id="chi" inputmode="decimal" value="${esc(fmtShort(shown(c.x, hi)))}"></label>
    <label>Also show<select id="cy2"><option value="">Nothing else</option>${second.map(s => `<option value="${esc(s)}" ${s === c.y2 ? "selected" : ""}>${esc(D.objects[s].text)} – ${esc(D.objects[s].name)}</option>`).join("")}</select></label>
  </div>
  <span class="info" tabindex="0" data-tip="Every other input is as on the Calculate tab. The dot marks the current calculation.">i</span>
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

// ---------------------------------------------------------------- Status (evidence, out of the way)
function renderStatus() {
  const o = D.objects[state.target], c = conf(o), ev = o.ev, b = o.bench, ref = o.reference || {};
  let h = `<h3>${dot(o)} ${esc(c.label)}</h3><ul class="small">${(o.conf.reasons || []).map(r => `<li>${esc(r)}</li>`).join("")}</ul>
    <div class="tiles">
      <div class="tile"><div class="v">${ev.sources}</div><div class="l">Source files that apply it</div></div>
      <div class="tile"><div class="v">${ev.formulas}</div><div class="l">Formulas found in them</div></div>
      <div class="tile"><div class="v">${b.total ? b.agree + " / " + b.total : "–"}</div><div class="l">Source values reproduced</div></div>
      <div class="tile"><div class="v">${esc(ref.status || "–")}</div><div class="l">Independent reference</div></div>
    </div>`;
  if (ev.variants.length) {
    h += `<h4>How the sources apply it</h4><div class="scroll"><table class="cases"><tr><th>Relation to the code</th><th>Formulas</th><th style="text-align:left">As written</th><th style="text-align:left">Differences</th></tr>`
      + ev.variants.map(v => `<tr><td>${esc(v.relation || "")}</td><td>${v.instances}</td><td style="text-align:left;white-space:normal">${esc(v.text)}</td><td style="text-align:left;white-space:normal">${esc((v.differences || []).concat(v.reason ? [v.reason] : []).join("; "))}</td></tr>`).join("") + `</table></div>`;
  }
  if (ev.practice.length) h += `<h4>Practice seen in the sources</h4><ul class="small">${ev.practice.map(p => `<li>${esc(p)}</li>`).join("")}</ul>`;
  if (b.pts.length) h += `<h4>Benchmarks</h4><p class="small">Each dot is a value shown in a source, against the code expression for the same inputs.</p><div id="bench"></div>`;
  if (ref.library) h += `<h4>Independent reference</h4><p class="small">${esc(ref.status)} with ${esc(ref.library)} <code>${esc(ref.function || "")}</code> over ${ref.agreeing_samples || 0} of ${ref.samples || 0} samples.${ref.note ? " " + esc(ref.note) : ""}</p>`;
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
  s += `<text x="${m + pw / 2}" y="${H - 6}" text-anchor="middle" font-size="12" style="fill:var(--ink)">Value in the source [${esc(u)}${pts.some(p => p[6]) ? " or " + esc(u) + "/m" : ""}]</text>`;
  s += `<text x="${m - 46}" y="10" font-size="11" style="fill:var(--muted)">Code</text></svg>`;
  el.innerHTML = `<div class="series-key"><span><i style="background:var(--s1);height:8px;width:8px;border-radius:50%"></i>Reproduced</span><span><i style="background:var(--s2);height:8px;width:8px;border-radius:50%"></i>Differs</span></div><div class="chartbox" style="max-width:${W}px">${s}</div>`;
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
  let h = `<section class="card"><h3>Overview</h3><p>Design-code expressions as calculation objects, written from the codes and checked against how real calculation files apply them. Choose a quantity on the left or search for it.</p>
    <div class="tiles"><div class="tile"><div class="v">${objs.length}</div><div class="l">Calculation objects</div></div>
      <div class="tile"><div class="v">${Object.keys(D.quantities).length}</div><div class="l">Parameters</div></div>
      <div class="tile"><div class="v">${D.codes.length}</div><div class="l">Codes</div></div>
      <div class="tile"><div class="v">${D.sources}</div><div class="l">Source files distilled</div></div></div></section>`;
  h += `<section class="card"><h3>Coverage and confidence by chapter</h3>
    <div class="series-key"><span><i class="dot good" style="width:9px;height:9px"></i>Checked (${n.high})</span><span><i class="dot warn" style="width:9px;height:9px"></i>Not yet checked (${n.medium})</span><span><i class="dot crit" style="width:9px;height:9px"></i>Review needed (${n.low})</span></div>
    <div class="bars" id="bars" style="margin-top:8px"></div></section>`;
  h += `<section class="card"><h3>Codes and what they share</h3><div class="scroll"><table class="cases"><tr><th>Code</th><th style="text-align:left">Title</th><th>Objects</th><th>Shared</th><th style="text-align:left">Values it fixes</th></tr>`
    + D.codes.map(c => {
      const own = objs.filter(o => o.code === c.code).length, sh = objs.filter(o => (o.refs || []).some(r => r.code === c.code)).length;
      const fx = Object.entries(c.fixed || {}).map(([k, v]) => `${symText(k)} = ${fmtShort(v)}`).join(", ");
      return `<tr><td>${esc(c.code)}</td><td style="text-align:left;white-space:normal">${esc(c.title || "")}</td><td>${own}</td><td>${sh}</td><td style="text-align:left">${esc(fx || "–")}</td></tr>`;
    }).join("") + `</table></div></section>`;
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
    const segs = [["high", "good", "Checked"], ["medium", "warn", "Not yet checked"], ["low", "crit", "Review needed"]].filter(([k]) => g[k])
      .map(([k, cls, l]) => `<span class="seg" data-g="${i}" data-l="${l}" data-n="${g[k]}" style="width:${g[k] / max * 100}%;background:var(--${cls})"></span>`).join("");
    return `<div class="row"><div class="lab" title="${esc(g.label)}">${esc(g.label)}</div><div class="track">${segs}<span class="n">${g.high + g.medium + g.low}</span></div></div>`;
  }).join("");
  const tip = $("#tip");
  for (const sg of document.querySelectorAll("#bars .seg")) {
    sg.addEventListener("pointermove", ev => { const g = groups[+sg.dataset.g]; tip.innerHTML = `${esc(g.label)}<br><b>${sg.dataset.n}</b> ${esc(sg.dataset.l.toLowerCase())}`; showTip(ev, tip); });
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
    : `<p>Open a calculation to choose its units.</p>`;
}

// ---------------------------------------------------------------- Code
function renderCode() {
  const o = D.objects[state.target];
  $("#panel").innerHTML = `<div class="code-h"><h4>Python</h4><button class="btn ghost" type="button" data-copy="py">Copy</button></div><pre class="code" id="code-py">${esc(o.python)}</pre>
    <div class="code-h"><h4>LaTeX</h4><button class="btn ghost" type="button" data-copy="tex">Copy</button></div><pre class="code" id="code-tex">${esc(o.tex)}</pre>`;
}
function copyText(id, btn) {
  const text = $("#code-" + id).textContent;
  const done = ok => { btn.textContent = ok ? "Copied" : "Select and press Ctrl+C"; setTimeout(() => { btn.textContent = "Copy"; }, 2000); };
  try { navigator.clipboard.writeText(text).then(() => done(true), () => done(false)); } catch (e) { done(false); }
}

// ---------------------------------------------------------------- tooltips: any element with data-tip
function tipShow(el, ev) {
  const tip = $("#tip");
  tip.textContent = el.dataset.tip;
  tip.style.display = "block";
  const r = el.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
  let x = r.left + r.width / 2 - tw / 2, y = r.top - th - 8;
  x = Math.max(8, Math.min(x, window.innerWidth - tw - 8));
  if (y < 8) y = r.bottom + 8;
  tip.style.left = (x + window.scrollX) + "px"; tip.style.top = (y + window.scrollY) + "px";
}
const tipHide = () => { $("#tip").style.display = "none"; };
document.addEventListener("pointerover", ev => { const el = ev.target.closest && ev.target.closest("[data-tip]"); if (el) tipShow(el, ev); });
document.addEventListener("pointerout", ev => { const el = ev.target.closest && ev.target.closest("[data-tip]"); if (el && !el.contains(ev.relatedTarget)) tipHide(); });
document.addEventListener("focusin", ev => { const el = ev.target.closest && ev.target.closest("[data-tip]"); if (el) tipShow(el, ev); });
document.addEventListener("focusout", tipHide);
window.addEventListener("scroll", tipHide, {passive: true});

// ---------------------------------------------------------------- events
document.addEventListener("click", ev => {
  const t = ev.target.closest("button, [data-open]");
  if (!t) return;
  const d = t.dataset;
  if (d.id) { openObject(d.id); return; }
  if (d.open) { openObject(d.open); return; }
  if (d.code) { state.code = d.code; store.set("code", d.code); renderCodes(); renderTree(); return; }
  if (d.tab) { state.tab = d.tab; tipHide(); renderMain(); return; }
  const id = state.target;
  if (d.detail) { const w = W(id); w.detail = d.detail; saveWork(id); renderSheet(); return; }
  if (d.rdetail) { const rb = reportOpts(); rb.detail = d.rdetail; saveWork(id); renderReport(); return; }
  if (d.copy) { copyText(d.copy, t); return; }
  if (d.give) { const w = W(id), r = evaluate(id, valuesFor(id), w.given); w.given.add(d.give); w.values[d.give] = r.env[d.give]; w.entered.add(d.give); saveWork(id); tipHide(); renderInputs(); renderSheet(); return; }
  if (d.ungive) { const w = W(id); w.given.delete(d.ungive); w.entered.delete(d.ungive); saveWork(id); tipHide(); renderInputs(); renderSheet(); return; }
  if (d.load) { const c = cases()[+d.load], w = W(id); w.values = Object.assign({}, c.values); w.entered = new Set(Object.keys(c.values)); w.given = new Set(c.given || []); w.check = c.check; saveWork(id); state.tab = "calc"; tipHide(); renderMain(); return; }
  if (d.del) { const l = cases(); l.splice(+d.del, 1); setCases(l); tipHide(); renderReport(); return; }
  if (t.id === "ovw") { state.view = "overview"; renderTree(); renderMain(); return; }
  if (t.id === "reset") { const w = W(id); w.values = {}; w.entered = new Set(); w.given = new Set(); w.check = null; saveWork(id); renderInputs(); renderSheet(); return; }
  if (t.id === "add-case") { const l = cases(); l.push(currentCase(`Case ${l.length + 1}`)); setCases(l); renderReport(); toast(`Case ${l.length} added.`); return; }
  if (t.id === "clear-cases") { setCases([]); renderReport(); return; }
  if (t.id === "dl-xlsx") { downloadExcel(t); return; }
  if (t.id === "dl-mcdx") { downloadMathcad(t); return; }
  if (t.id === "rep-pdf") { reportPDF(t); return; }
  if (t.id === "rep-docx") { reportWord(t); return; }
  if (t.id === "rep-yaml") { batchTemplate(t); return; }
  if (t.id === "ask-btn") { ask(); return; }
  if (t.id === "settings-btn") { renderSettings(); try { $("#settings").showModal(); } catch (e) { $("#settings").setAttribute("open", ""); } return; }
  if (t.id === "set-close") { $("#settings").close(); return; }
  if (t.id === "set-reset") { S.decimals = 2; S.minsig = 3; S.units = {}; store.set("style", S); renderSettings(); renderMain(); return; }
});
document.addEventListener("keydown", ev => {
  const t = ev.target.closest && ev.target.closest("[data-open]");
  if (t && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); openObject(t.dataset.open); }
  if (ev.key === "Escape") tipHide();
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
    // refresh this row's information mark without re-rendering the input being typed in
    const row = t.closest(".inp"), info = inputInfo(p, c), old = row.querySelector(".info");
    t.classList.toggle("out", info.out);
    const tmp = document.createElement("span"); tmp.innerHTML = info.html;
    if (old && tmp.firstChild) old.replaceWith(tmp.firstChild); else if (old) old.remove(); else if (tmp.firstChild) row.querySelector("label").appendChild(tmp.firstChild);
    return;
  }
  if (t.dataset.rb !== undefined && t.type !== "checkbox" && t.tagName !== "SELECT") { reportOpts()[t.dataset.rb] = t.value; saveWork(state.target); return; }
  if (t.id === "clo" || t.id === "chi") { const w = W(state.target), f = unitOf(w.chart.x)[1]; const a = parseFloat($("#clo").value.replace(",", ".")), b = parseFloat($("#chi").value.replace(",", ".")); if (isFinite(a) && isFinite(b)) { w.chart.lo = a * f; w.chart.hi = b * f; } drawSweep(); return; }
});
document.addEventListener("change", ev => {
  const t = ev.target;
  if (t.dataset.rb !== undefined && (t.type === "checkbox" || t.tagName === "SELECT")) { const rb = reportOpts(); rb[t.dataset.rb] = t.type === "checkbox" ? t.checked : t.value; saveWork(state.target); return; }
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
  $("#sub").textContent = `${nObj} calculation objects · ${D.codes.map(c => c.code).join(" · ")}`;
  if (!D.codes.some(c => c.code === state.code)) state.code = "all";
  renderCodes(); renderTree(); renderMain();
})();
</script>
"""
