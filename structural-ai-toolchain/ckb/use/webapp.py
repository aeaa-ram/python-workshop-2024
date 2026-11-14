"""The web calculator: the knowledge base as one self-contained HTML file.

No server and no installation: the file holds the objects, their formulas as
plain JavaScript functions and the evidence behind them.  An engineer picks a
quantity from the clause tree, types the inputs, and reads a self-documenting
calculation that updates as they type.  Dependencies are resolved in the
page, and any intermediate value can be entered directly instead of being
calculated.

The JavaScript functions are printed from the same formula trees as the
Python code blocks, so the calculator cannot drift from the knowledge base.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import expr as X
from .. import units as U
from ..kb.codegen import module_source
from ..kb.objects import KnowledgeBase

MAX_ROWS = 14        # benchmark rows shown per object (deviations first)


def payload(kb: KnowledgeBase) -> dict:
    objects = {}
    for o in kb.objects.values():
        rows = sorted(o.benchmarks.get("items", []), key=lambda r: (r["status"] != "deviation", r["kind"] != "printed"))
        objects[o.id] = {
            "id": o.id, "text": o.text, "ml": o.ml, "name": o.name, "unit": o.unit,
            "factor": U.parse_unit(o.unit).factor, "ref": o.reference_text, "topic": o.topic,
            "path": o.topic_path, "status": o.status, "support": o.support, "params": o.params,
            "mlF": X.to_mathml(o.tree, kb.ml), "mlS": X.to_mathml(o.tree, kb.ml, slots=True),
            "txtF": X.to_text(o.tree, kb.name),
            "warnings": o.warnings, "findings": o.findings, "notes": o.notes,
            "variants": [{k: v[k] for k in ("text", "instances", "sources", "merged", "differences", "reason") if k in v}
                         for v in o.variants],
            "bench": {k: o.benchmarks.get(k, 0) for k in ("total", "agree", "deviation", "not_comparable")},
            "rows": [{k: r[k] for k in ("source", "where", "case", "kind", "expected", "got", "status", "detail",
                                        "per_width") if k in r} for r in rows[:MAX_ROWS]],
            "reference": o.reference, "examples": o.examples, "python": module_source(kb, o),
            "check": o.check, "version": o.version,
        }
    quantities = {}
    for q in kb.quantities.values():
        ref = ""
        if q.clause:
            ref = f"{kb.meta.get('code', '')} " + (q.clause if q.clause.lower().startswith("table") else f"cl. {q.clause}")
        quantities[q.id] = {"id": q.id, "text": q.text, "ml": q.ml, "name": q.name, "unit": q.unit,
                            "factor": U.parse_unit(q.unit).factor, "typical": q.typical, "range": q.range,
                            "kind": q.kind, "ref": ref}
    return {"meta": kb.meta, "topics": kb.topics, "sources": kb.sources, "objects": objects,
            "quantities": quantities}


def functions_js(kb: KnowledgeBase) -> str:
    lines = ["const F = {"]
    for o in kb.objects.values():
        body = X.to_js(o.tree, lambda s: f"e.{s}")
        lines.append(f"  {json.dumps(o.id)}: function (e) {{ return {body}; }},")
    lines.append("};")
    return "\n".join(lines)


def render(kb: KnowledgeBase, standalone: bool = True) -> str:
    data = json.dumps(payload(kb), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = (TEMPLATE.replace("/*__FUNCTIONS__*/", functions_js(kb)).replace("/*__DATA__*/", data)
            .replace("__STANDALONE__", "true" if standalone else "false"))
    if not standalone:
        return page
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            "</head>\n<body>\n" + page + "\n</body>\n</html>\n")


def write(kb: KnowledgeBase, path: Path, standalone: bool = True) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(kb, standalone), encoding="utf-8")
    return path


TEMPLATE = r"""<title>Calculation Knowledge Base</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Noto+Sans+Math&display=swap">
<style>
/* layout: clause tree on the left, one object at a time on the right: inputs beside a calculation sheet, evidence below */
:root{
  --bg:#eef1ef; --surface:#ffffff; --raised:#f6f8f7; --ink:#15211f; --muted:#5b6966; --rule:#cfd8d5; --soft:#e6ebe9;
  --accent:#0b5d73; --accent-ink:#ffffff; --accent-soft:#dcedf1;
  --ok:#1b7446; --okbg:#e0f2e8; --warn:#9a5b00; --warnbg:#fbeed6; --bad:#b3261e; --badbg:#fbe5e3; --info:#3d5a80; --infobg:#e4ebf5;
  --font:"IBM Plex Sans","Segoe UI",system-ui,Arial,sans-serif; --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  --math:"Cambria Math","STIX Two Math","Latin Modern Math","Noto Sans Math",math;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#101615; --surface:#182120; --raised:#1f2a28; --ink:#e6edeb; --muted:#9aaaa6; --rule:#34423f; --soft:#263230;
  --accent:#6cc3d8; --accent-ink:#06222a; --accent-soft:#173940;
  --ok:#6fd09a; --okbg:#143524; --warn:#f0b65a; --warnbg:#3a2a0d; --bad:#f2928b; --badbg:#431b18; --info:#a9c0e4; --infobg:#1e2b40;
  color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#101615; --surface:#182120; --raised:#1f2a28; --ink:#e6edeb; --muted:#9aaaa6; --rule:#34423f; --soft:#263230;
  --accent:#6cc3d8; --accent-ink:#06222a; --accent-soft:#173940;
  --ok:#6fd09a; --okbg:#143524; --warn:#f0b65a; --warnbg:#3a2a0d; --bad:#f2928b; --badbg:#431b18; --info:#a9c0e4; --infobg:#1e2b40;
  color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:14px/1.5 var(--font);margin:0}
math{font-family:var(--math);font-size:1.1em}
button,input,select{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.wrap{max-width:1500px;margin:0 auto;padding-block:16px 40px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header.top{display:flex;flex-wrap:wrap;gap:8px 24px;align-items:baseline;margin-bottom:14px}
header.top h1{font-size:20px;margin:0;font-weight:600;letter-spacing:-.01em}
header.top p{margin:0;color:var(--muted)}
.shell{display:grid;grid-template-columns:290px minmax(0,1fr);gap:18px;align-items:start}
nav.tree{background:var(--surface);border:1px solid var(--rule);padding:12px;position:sticky;top:calc(env(safe-area-inset-top,0px) + 12px);max-height:calc(100vh - 24px);overflow:auto}
nav.tree input{width:100%;padding:7px 9px;border:1px solid var(--rule);background:var(--raised);margin-bottom:10px}
.t-chap{font-weight:600;margin:10px 0 2px;font-size:13px}
.t-sec{color:var(--muted);font-size:12.5px;margin:6px 0 2px}
.t-sec.has{color:var(--ink)}
.t-obj{display:flex;gap:8px;align-items:baseline;width:100%;text-align:left;background:none;border:0;border-left:2px solid var(--rule);padding:3px 8px;cursor:pointer;margin-left:6px}
.t-obj:hover{background:var(--raised)} .t-obj[aria-current="true"]{border-left-color:var(--accent);background:var(--accent-soft)}
.t-obj .s{min-width:5.2em} .t-obj .n{color:var(--muted);font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;flex:none;align-self:center}
.dot.ok{background:var(--ok)} .dot.warn{background:var(--warn)} .dot.bad{background:var(--bad)}
.ovw{display:block;width:100%;text-align:left;background:var(--raised);border:1px solid var(--rule);padding:7px 9px;cursor:pointer;margin-bottom:6px}
.ovw[aria-current="true"]{border-color:var(--accent)}
main{min-width:0;display:flex;flex-direction:column;gap:16px}
.head{background:var(--surface);border:1px solid var(--rule);padding:14px 16px}
.head h2{margin:0;font-size:19px;font-weight:600;line-height:1.3;text-wrap:balance}
.head .ref{color:var(--muted);margin:2px 0 8px}
.pill{display:inline-block;padding:1px 9px;border-radius:10px;font-size:12px;font-weight:600;white-space:nowrap}
.pill.ok{background:var(--okbg);color:var(--ok)} .pill.warn{background:var(--warnbg);color:var(--warn)} .pill.bad{background:var(--badbg);color:var(--bad)} .pill.info{background:var(--infobg);color:var(--info)}
.facts{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--muted);font-size:13px;align-items:center}
.work{display:grid;grid-template-columns:330px minmax(0,1fr);gap:16px;align-items:start}
.panel{background:var(--surface);border:1px solid var(--rule);padding:14px 16px;min-width:0}
.panel h3{margin:0 0 10px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.fld{display:grid;grid-template-columns:minmax(0,1fr) 108px 44px;gap:2px 8px;align-items:center;padding:5px 0;border-bottom:1px solid var(--soft)}
.fld label{min-width:0} .fld label small{display:block;color:var(--muted);font-size:11.5px;line-height:1.3}
.fld input{width:100%;padding:5px 7px;border:1px solid var(--rule);background:var(--raised);text-align:right;font-family:var(--mono);font-size:13px;font-variant-numeric:tabular-nums}
.fld input.out{border-color:var(--warn)}
.fld .u{color:var(--muted);font-size:12.5px}
.fld .x{grid-column:1/-1;font-size:11.5px;color:var(--warn)}
.fld button.lnk,.row button.lnk{background:none;border:0;padding:0;color:var(--accent);cursor:pointer;font-size:11.5px;text-decoration:underline}
select.ex{width:100%;padding:6px 7px;border:1px solid var(--rule);background:var(--raised);margin-bottom:6px}
.exnote{font-size:12.5px;margin:0 0 10px;padding:6px 8px;background:var(--raised);border-left:3px solid var(--rule)}
.exnote.ok{border-left-color:var(--ok)} .exnote.bad{border-left-color:var(--bad)}
.sheet .tb{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border:1px solid var(--ink);margin-bottom:14px}
.sheet .tb label{border:0 solid var(--ink);border-right-width:1px;border-bottom-width:1px;padding:3px 7px;display:block;min-width:0}
.sheet .tb label:nth-child(3n){border-right-width:0} .sheet .tb label:nth-child(n+4){border-bottom-width:0}
.sheet .tb small{display:block;color:var(--muted);font-size:9.5px;letter-spacing:.05em;text-transform:uppercase}
.sheet .tb input{width:100%;border:0;background:transparent;padding:0;font-size:13px}
.row{display:grid;grid-template-columns:23% minmax(0,1fr) 15%;gap:0 12px;padding:8px 0;border-bottom:1px solid var(--soft)}
.row .d small{display:flex;gap:8px;align-items:center;margin-top:3px;flex-wrap:wrap}
.row .c{color:var(--muted);font-size:12px;text-align:right}
.row .e{min-width:0;overflow-x:auto;overflow-y:hidden;padding-bottom:2px}
.eq{display:flex;gap:6px;align-items:baseline;margin:3px 0;white-space:nowrap}
.eq .lhs{min-width:4.8em;text-align:right;flex:none}
.eq.res{font-weight:600}
.result{margin-top:14px;padding:12px 14px;border:1.5px solid var(--ink);display:flex;gap:10px 18px;align-items:center;flex-wrap:wrap}
.result .big{font-size:19px;font-weight:600}
.chk{display:flex;gap:8px;align-items:center;flex-wrap:wrap;flex:1;min-width:230px}
.chk input{width:96px;padding:5px 7px;border:1px solid var(--rule);background:var(--raised);text-align:right;font-family:var(--mono)}
.bar{height:10px;background:var(--soft);border:1px solid var(--rule);position:relative;flex:1;min-width:120px}
.bar i{position:absolute;inset:0 auto 0 0;display:block;background:var(--ok)} .bar.warn i{background:var(--warn)} .bar.bad i{background:var(--bad)}
.msg{margin:10px 0 0;padding-left:18px} .msg li{margin:3px 0} .msg li.w{color:var(--warn)} .msg li.err{color:var(--bad)}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.btn{border:1px solid var(--accent);background:var(--accent);color:var(--accent-ink);padding:6px 12px;cursor:pointer;font-weight:500}
.btn.ghost{background:transparent;color:var(--accent)}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--rule);margin-bottom:12px;flex-wrap:wrap}
.tabs button{border:0;background:none;padding:7px 12px;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;font-weight:500}
.tabs button[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--accent)}
.scroll{overflow-x:auto}
table.t{border-collapse:collapse;width:100%;font-size:13px}
table.t th,table.t td{border-bottom:1px solid var(--soft);padding:5px 8px;text-align:left;vertical-align:top}
table.t th{color:var(--muted);font-weight:500;font-size:12px;white-space:nowrap}
table.t td.num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.note{padding:7px 10px;margin:0 0 8px;border-left:3px solid var(--rule);background:var(--raised)}
.note.w{border-left-color:var(--warn)} .note.f{border-left-color:var(--info)} .note.b{border-left-color:var(--bad)}
pre{margin:0;background:var(--raised);border:1px solid var(--rule);padding:12px;overflow-x:auto;font:12.5px/1.5 var(--mono)}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.stat{border:1px solid var(--rule);padding:10px 12px;background:var(--raised)}
.stat b{display:block;font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.stat span{color:var(--muted);font-size:12.5px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--rule);background:var(--raised);padding:1px 8px;cursor:pointer;border-radius:10px}
@media (max-width:1050px){.work{grid-template-columns:1fr}}
@media (max-width:820px){.shell{grid-template-columns:1fr} nav.tree{position:static;max-height:340px} .row{grid-template-columns:1fr} .row .c{text-align:left}}
@media print{nav.tree,header.top,.head,.inputs,.evid,.tools,.row button{display:none!important} .shell,.work{display:block} .panel{border:0;padding:0} body{background:#fff}}
</style>

<div class="wrap">
  <header class="top">
    <h1>Calculation Knowledge Base</h1>
    <p id="tagline"></p>
  </header>
  <div class="shell">
    <nav class="tree" aria-label="Code structure">
      <input id="q" type="search" placeholder="Search: symbol, name or clause" aria-label="Search objects">
      <button class="ovw" id="ovw" type="button">Overview: sources and coverage</button>
      <div id="tree"></div>
    </nav>
    <main id="main"></main>
  </div>
</div>

<script type="application/json" id="kbdata">/*__DATA__*/</script>
<script>
/*__FUNCTIONS__*/
const KB = JSON.parse(document.getElementById('kbdata').textContent);
const STANDALONE = __STANDALONE__;
const O = KB.objects, Q = KB.quantities;
const state = {id: null, vals: {}, given: {}, check: {}, tab: 'evidence', ex: {}, view: 'object'};
const $ = (s, r) => (r || document).querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const item = id => O[id] || Q[id];
const statusClass = s => ({consensus: 'ok', unified: 'ok', 'single source': 'warn', disagreement: 'bad'}[s] || 'warn');
const statusText = s => ({consensus: 'consensus', unified: 'unified', 'single source': 'one source', disagreement: 'sources disagree'}[s] || s);

function fmt(v, sig) {
  sig = sig || 5;
  if (typeof v === 'string') return v;
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  if (!Number.isFinite(v)) return v > 0 ? '∞' : '−∞';
  if (v === 0) return '0';
  const a = Math.abs(v);
  if (a >= Math.pow(10, sig)) return v.toFixed(0);
  if (a < 1e-4) return v.toExponential(sig - 2).replace('e-', '·10^-');
  const digits = Math.max(0, sig - 1 - Math.floor(Math.log10(a)));
  let s = v.toFixed(digits);
  if (s.indexOf('.') >= 0) s = s.replace(/0+$/, '').replace(/\.$/, '');
  return s;
}
const unitText = u => (u === '-' || !u) ? '' : u;
const show = (id, v) => typeof v === 'number' ? v / item(id).factor : v;

function plan(target, given) {
  const steps = [], inputs = [], done = {};
  (function visit(id, trail) {
    if (done[id]) return;
    if (trail.indexOf(id) >= 0) throw new Error('objects refer to each other in a circle');
    O[id].params.forEach(p => {
      if (O[p] && !given[p]) visit(p, trail.concat(id));
      else if (inputs.indexOf(p) < 0) inputs.push(p);
    });
    done[id] = 1; steps.push(id);
  })(target, []);
  return {steps, inputs};
}

function startValue(id) {
  const q = Q[id];
  if (q && q.typical !== null && q.typical !== undefined) return q.typical;
  if (q && q.range) return (q.range[0] + q.range[1]) / 2;
  return undefined;
}

function loadExample(id, k) {
  const ex = O[id].examples[k];
  if (!ex) return;
  state.given[id] = {};
  (ex.given || []).forEach(g => { state.given[id][g] = true; });
  Object.keys(ex.inputs).forEach(p => { state.vals[p] = ex.inputs[p]; });
  state.ex[id] = k;
}

function select(id) {
  state.view = 'object'; state.id = id;
  if (!state.given[id]) state.given[id] = {};
  const o = O[id];
  if (state.ex[id] === undefined && o.examples.length) {
    let k = o.examples.findIndex(e => e.matches_source && !(e.given || []).length);
    if (k < 0) k = o.examples.findIndex(e => e.matches_source);
    loadExample(id, k < 0 ? 0 : k);
  }
  plan(id, state.given[id]).inputs.forEach(p => { if (state.vals[p] === undefined) state.vals[p] = startValue(p); });
  renderTree(); renderObject();
}

function compute(id) {
  const given = state.given[id] || {};
  const pl = plan(id, given), env = {}, out = {steps: [], inputs: pl.inputs, error: null, warn: []};
  pl.inputs.forEach(p => { env[p] = state.vals[p]; });
  for (const p of pl.inputs) {
    if (typeof env[p] !== 'number' || Number.isNaN(env[p])) { out.error = 'Enter a value for ' + item(p).text + '.'; return out; }
    const q = Q[p];
    if (q && q.range && (env[p] < q.range[0] - 1e-9 || env[p] > q.range[1] + 1e-9))
      out.warn.push(item(p).text + ' = ' + fmt(show(p, env[p])) + ' ' + unitText(q.unit) + ' is outside the usual range ' +
        fmt(show(p, q.range[0])) + ' to ' + fmt(show(p, q.range[1])) + ' ' + unitText(q.unit) + '.');
  }
  for (const s of pl.steps) {
    let v;
    try { v = F[s](env); } catch (err) { v = NaN; }
    const snap = {}; O[s].params.forEach(p => { snap[p] = env[p]; });
    out.steps.push({id: s, value: v, env: snap});
    if (typeof v !== 'number' || !Number.isFinite(v)) {
      out.error = O[s].text + (typeof v === 'string' ? ': ' + v : ' cannot be evaluated with these inputs.');
      return out;
    }
    env[s] = v;
  }
  out.value = env[id];
  return out;
}

function fillSlots(root, env) {
  root.querySelectorAll('mn.slot').forEach(n => {
    const v = env[n.getAttribute('data-s')];
    const t = fmt(v);
    n.textContent = (typeof v === 'number' && v < 0) ? '(' + t.replace('-', '−') + ')' : t;
  });
}

/* ---------- tree ---------- */
function renderTree() {
  const needle = ($('#q').value || '').trim().toLowerCase();
  const byTopic = {};
  Object.values(O).forEach(o => {
    const hay = (o.text + ' ' + o.id + ' ' + o.name + ' ' + o.ref + ' ' + o.path.join(' ')).toLowerCase().replace(/[_,.]/g, '');
    if (needle && hay.indexOf(needle.replace(/[_,.]/g, '')) < 0) return;
    (byTopic[o.topic] = byTopic[o.topic] || []).push(o);
  });
  let h = '';
  KB.topics.forEach(t => {
    const depth = t.id.split('.').length;
    const has = Object.keys(byTopic).some(k => k === t.id || k.indexOf(t.id + '.') === 0);
    if (needle && !has) return;
    if (depth === 1) h += '<div class="t-chap">' + esc(t.id + ' ' + t.title) + '</div>';
    else h += '<div class="t-sec' + (has ? ' has' : '') + '" style="padding-left:' + (depth - 2) * 10 + 'px">' + esc(t.id + ' ' + t.title) + (has ? '' : ' <span title="no object yet">·</span>') + '</div>';
    (byTopic[t.id] || []).forEach(o => {
      h += '<button type="button" class="t-obj" data-id="' + o.id + '"' + (state.view === 'object' && o.id === state.id ? ' aria-current="true"' : '') +
        ' style="margin-left:' + (6 + (depth - 2) * 10) + 'px"><span class="dot ' + statusClass(o.status) + '" title="' + esc(statusText(o.status)) + '"></span><span class="s"><math>' + o.ml + '</math></span><span class="n">' + esc(o.name) + '</span></button>';
    });
  });
  $('#tree').innerHTML = h || '<p style="color:var(--muted)">Nothing matches.</p>';
  $('#ovw').setAttribute('aria-current', state.view === 'overview' ? 'true' : 'false');
}

/* ---------- object view ---------- */
function renderObject() {
  const o = O[state.id], s = o.support;
  const facts = [
    '<span class="pill ' + statusClass(o.status) + '">' + esc(statusText(o.status)) + '</span>',
    (s.formula_instances || 0) + ' formulas in ' + (s.sources || 0) + ' independent source' + (s.sources === 1 ? '' : 's'),
    o.bench.agree + ' of ' + o.bench.total + ' source values reproduced',
    o.reference && o.reference.status ? 'independent reference: <b>' + esc(o.reference.status) + '</b>' : 'no independent reference'
  ];
  let h = '<section class="head"><h2><math>' + o.ml + '</math>&nbsp; ' + esc(o.name) + '</h2>' +
    '<p class="ref">' + esc(o.ref) + ' · ' + esc(o.path.join(' › ')) + '</p><div class="facts">' + facts.map(f => '<span>' + f + '</span>').join('') + '</div></section>';
  h += '<div class="work"><section class="panel inputs"><h3>Input</h3><div id="inputs"></div></section>' +
       '<section class="panel sheet"><div id="sheet"></div></section></div>';
  h += '<section class="panel evid"><div class="tabs" role="tablist">' +
    ['evidence', 'code'].map(t => '<button type="button" role="tab" data-tab="' + t + '" aria-selected="' + (state.tab === t) + '">' +
      ({evidence: 'Evidence', code: 'Code block'}[t]) + '</button>').join('') + '</div><div id="tab"></div></section>';
  $('#main').innerHTML = h;
  renderInputs(); renderSheet(); renderTab();
}

function renderInputs() {
  const id = state.id, o = O[id], pl = plan(id, state.given[id]);
  let h = '';
  if (o.examples.length) {
    h += '<label for="ex" style="font-size:12.5px;color:var(--muted)">Case from the sources</label><select class="ex" id="ex">' +
      o.examples.map((e, k) => '<option value="' + k + '"' + (state.ex[id] === k ? ' selected' : '') + '>' + esc(e.label) + '</option>').join('') +
      '<option value="-1"' + (state.ex[id] === -1 ? ' selected' : '') + '>My own values</option></select><div id="exnote"></div>';
  }
  pl.inputs.forEach(p => {
    const it = item(p), g = state.given[id][p];
    h += '<div class="fld"><label for="in-' + p + '"><math>' + it.ml + '</math><small>' + esc(it.name) + '</small></label>' +
      '<input id="in-' + p + '" data-p="' + p + '" type="number" step="any" inputmode="decimal" value="' + (state.vals[p] === undefined ? '' : fmt(show(p, state.vals[p]), 8)) + '">' +
      '<span class="u">' + esc(unitText(it.unit)) + '</span>' +
      (g ? '<span class="x">entered directly · <button type="button" class="lnk" data-calc="' + p + '">calculate it instead</button></span>' : '') + '</div>';
  });
  $('#inputs').innerHTML = h;
}

function renderSheet() {
  const id = state.id, o = O[id], r = compute(id);
  let h = '<div class="tb">' + [['project', 'Project'], ['subject', 'Subject'], ['number', 'Calc. no.'], ['made', 'Made by / date'], ['checked', 'Checked by / date'], ['approved', 'Approved by / date']]
    .map(f => '<label><small>' + f[1] + '</small><input id="tb-' + f[0] + '" data-tb="' + f[0] + '" value="' + esc(titleBlock[f[0]] || (f[0] === 'subject' ? o.name : '')) + '"></label>').join('') + '</div>';
  r.steps.forEach(st => {
    const so = O[st.id], isNum = typeof st.value === 'number';
    const canon = isNum && Math.abs(st.value - show(st.id, st.value)) > 1e-12 * Math.max(1, Math.abs(st.value));
    h += '<div class="row" data-step="' + st.id + '"><div class="d">' + esc(so.name) + '<small><span class="pill ' + statusClass(so.status) + '">' + esc(statusText(so.status)) + '</span>' +
      (st.id !== id ? '<button type="button" class="lnk" data-give="' + st.id + '">enter directly</button>' : '') +
      (st.id !== id ? '<button type="button" class="lnk" data-open="' + st.id + '">open</button>' : '') + '</small></div>' +
      '<div class="e"><div class="eq"><span class="lhs"><math>' + so.ml + '</math></span><math displaystyle="true"><mo>=</mo>' + so.mlF + '</math></div>' +
      '<div class="eq sub"><span class="lhs"></span><math displaystyle="true"><mo>=</mo>' + so.mlS + '</math></div>' +
      '<div class="eq res"><span class="lhs"></span><math><mo>=</mo>' + (canon ? '<mn>' + esc(fmt(st.value, 6)) + '</mn><mo>=</mo>' : '') +
      (isNum ? '<mn>' + esc(fmt(show(st.id, st.value))) + '</mn>' : '<mtext>' + esc(String(st.value)) + '</mtext>') +
      (unitText(so.unit) ? '<mtext>&#x2009;' + esc(so.unit) + '</mtext>' : '') + '</math></div></div>' +
      '<div class="c">' + esc(so.ref) + '</div></div>';
  });
  if (r.error) {
    h += '<ul class="msg"><li class="err">' + esc(r.error) + '</li></ul>';
  } else {
    const v = r.value;
    let box = '<div class="big"><math>' + o.ml + '<mo>=</mo><mn>' + esc(fmt(show(id, v))) + '</mn>' + (unitText(o.unit) ? '<mtext>&#x2009;' + esc(o.unit) + '</mtext>' : '') + '</math></div>';
    if (o.check && item(o.check)) {
      const c = item(o.check), cv = state.check[id];
      box += '<div class="chk"><label for="chk"><math>' + c.ml + '</math> =</label><input id="chk" type="number" step="any" inputmode="decimal" placeholder="optional" value="' + (cv === undefined ? '' : fmt(cv / c.factor, 8)) + '"><span>' + esc(unitText(c.unit)) + '</span>';
      if (typeof cv === 'number' && cv > 0 && v) {
        const action = /_Ed$/.test(o.check), u = action ? cv / v : v / cv;
        const cls = u <= 0.9 ? 'ok' : (u <= 1 ? 'warn' : 'bad');
        box += '<span>utilisation ' + esc(action ? c.text + ' / ' + o.text : o.text + ' / ' + c.text) + ' = <b>' + u.toFixed(2) + '</b></span><span class="pill ' + cls + '">' + (u <= 1 ? 'OK' : 'NOT OK') + '</span><div class="bar ' + cls + '"><i style="width:' + Math.min(u, 1) * 100 + '%"></i></div>';
      }
      box += '</div>';
    }
    h += '<div class="result">' + box + '</div>';
  }
  const msgs = [];
  r.warn.forEach(w => msgs.push('<li class="w">' + esc(w) + '</li>'));
  r.steps.forEach(st => O[st.id].warnings.forEach(w => msgs.push('<li class="w">' + esc(O[st.id].text + ': ' + w) + '</li>')));
  r.steps.forEach(st => O[st.id].notes.forEach(n => msgs.push('<li>' + esc(O[st.id].text + ': ' + n) + '</li>')));
  if (msgs.length) h += '<ul class="msg">' + msgs.join('') + '</ul>';
  h += '<p style="color:var(--muted);font-size:12px;margin:10px 0 0">Numbers are substituted in N, mm and MPa. Every step is one object of the knowledge base.</p>';
  h += '<div class="tools"><button type="button" class="btn ghost" id="copycalc">Copy calculation as text</button>' +
       (STANDALONE ? '<button type="button" class="btn ghost" id="print">Print or save as PDF</button>' : '') + '<span id="copied" style="align-self:center;color:var(--muted)"></span></div>';
  $('#sheet').innerHTML = h;
  r.steps.forEach(st => { const row = $('#sheet .row[data-step="' + st.id + '"] .sub'); if (row) fillSlots(row, st.env); });
  state.last = r;
  const note = $('#exnote');
  if (note) {
    const ex = o.examples[state.ex[id]];
    if (ex && !r.error) {
      const same = Math.abs(r.value - ex.result) <= 1e-9 * Math.abs(ex.result);
      if (!same) note.innerHTML = '';
      else if (ex.matches_source) note.innerHTML = '<p class="exnote ok">The source gives ' + esc(fmt(show(id, ex.expected))) + ' ' + esc(unitText(o.unit)) + '. Reproduced.</p>';
      else note.innerHTML = '<p class="exnote bad">The source gives ' + esc(fmt(show(id, ex.expected))) + ' ' + esc(unitText(o.unit)) + '; the unified logic gives ' + esc(fmt(show(id, ex.result))) + ' ' + esc(unitText(o.unit)) + '. See Evidence for the reason.</p>';
    } else note.innerHTML = '';
  }
}

function calcText() {
  const id = state.id, o = O[id], r = state.last, L = [];
  L.push(o.text + ' - ' + o.name); L.push(o.ref); L.push('');
  L.push('Input');
  r.inputs.forEach(p => L.push('  ' + item(p).text + ' = ' + fmt(show(p, state.vals[p]), 8) + ' ' + unitText(item(p).unit) + '    ' + item(p).name));
  L.push(''); L.push('Calculation');
  r.steps.forEach(st => {
    const so = O[st.id];
    L.push('  ' + so.text + ' = ' + so.txtF);
    L.push('      = ' + fmt(show(st.id, st.value)) + ' ' + unitText(so.unit) + '    [' + so.ref + '] (' + statusText(so.status) + ')');
  });
  if (!r.error) { L.push(''); L.push('Result: ' + o.text + ' = ' + fmt(show(id, r.value)) + ' ' + unitText(o.unit)); }
  return L.join('\n');
}

function renderTab() {
  const o = O[state.id];
  let h = '';
  if (state.tab === 'code') {
    h = '<p style="margin:0 0 8px;color:var(--muted)">Generated from the object file. Units: N, mm, MPa, rad. The same formula drives this page, the Excel calculator and the report.</p>' +
      '<pre id="py">' + esc(o.python) + '</pre><div class="tools"><button type="button" class="btn ghost" id="copypy">Copy Python</button><span id="copied2" style="align-self:center;color:var(--muted)"></span></div>' +
      '<p style="margin:12px 0 4px;color:var(--muted)">Other ways to use this object (from the project folder):</p><pre>python -m ckb run ' + o.id + '        # asks for the inputs in the terminal\npython -m ckb excel ' + o.id + '      # Excel calculator with live formulas\npython -m ckb report ' + o.id + '     # calculation sheet as HTML and PDF</pre>';
  } else {
    o.warnings.forEach(w => { h += '<p class="note w">' + esc(w) + '</p>'; });
    o.findings.forEach(w => { h += '<p class="note f">' + esc(w) + '</p>'; });
    h += '<h3>Variants found in the sources</h3><div class="scroll"><table class="t"><tr><th>Formula as written (consistent units)</th><th>Instances</th><th>Sources</th><th>Relation to the unified formula</th></tr>';
    o.variants.forEach(v => {
      const rel = v.merged ? (v.differences.length ? 'special case: ' + v.differences.join('; ') : 'identical') : 'not merged: ' + (v.reason || '');
      h += '<tr><td><code>' + esc(v.text) + '</code></td><td class="num">' + v.instances + '</td><td>' + esc(v.sources.join(', ')) + '</td><td>' +
        '<span class="pill ' + (v.merged ? 'ok' : 'bad') + '">' + (v.merged ? 'merged' : 'kept apart') + '</span> ' + esc(rel) + '</td></tr>';
    });
    h += '</table></div>';
    h += '<h3 style="margin-top:16px">Benchmarks</h3><p style="margin:0 0 8px">' + o.bench.agree + ' of ' + o.bench.total + ' source values are reproduced' +
      (o.bench.deviation ? ', ' + o.bench.deviation + ' differ' : '') + (o.bench.not_comparable ? ', ' + o.bench.not_comparable + ' cannot be compared' : '') + '.</p>';
    if (o.rows.length) {
      h += '<div class="scroll"><table class="t"><tr><th>Source</th><th>Where</th><th>Source value</th><th>Unified logic</th><th></th><th>Remark</th></tr>';
      o.rows.forEach(r => {
        const k = r.per_width ? 1000 : 1, u = unitText(o.unit) + (r.per_width ? '/m' : '');
        const val = x => typeof x === 'number' ? fmt(show(o.id, x) * k) + ' ' + u : (x === null || x === undefined ? '–' : String(x));
        const cls = r.status === 'agree' ? 'ok' : (r.status === 'deviation' ? 'bad' : 'info');
        h += '<tr><td>' + esc(r.source) + '</td><td>' + esc(r.where + (r.case ? ' · ' + r.case : '')) + '</td><td class="num">' + esc(val(r.expected)) + '</td><td class="num">' + esc(val(r.got)) +
          '</td><td><span class="pill ' + cls + '">' + esc(r.status === 'agree' ? (r.kind === 'printed' ? 'within print rounding' : 'reproduced') : r.status) + '</span></td><td>' + esc(r.detail || '') + '</td></tr>';
      });
      h += '</table></div>';
      if (o.bench.total > o.rows.length) h += '<p style="color:var(--muted);margin:6px 0 0">Showing ' + o.rows.length + ' of ' + o.bench.total + ' (differences first). The full list is in the object file.</p>';
    }
    h += '<h3 style="margin-top:16px">Independent reference</h3>';
    if (o.reference && o.reference.status) {
      const r = o.reference;
      h += '<p class="note ' + (r.status === 'agrees' ? '' : 'b') + '">' + esc(r.status === 'agrees' ? 'Agrees' : 'Differs') + ' with ' + esc(r.library) + ' <code>' + esc(r.function) + '</code>: ' +
        r.agreeing_samples + ' of ' + r.samples + ' random samples over the parameter range, largest relative difference ' + esc(String(r.max_relative_difference)) + '.' + (r.note ? ' ' + esc(r.note) + '.' : '') + '</p>';
    } else h += '<p class="note">No open-source implementation of this clause is wired in yet.</p>';
    const uses = o.params.filter(p => O[p]), usedBy = Object.values(O).filter(x => x.params.indexOf(o.id) >= 0);
    h += '<h3 style="margin-top:16px">Connections</h3><div class="chips">' +
      (uses.length ? '<span style="color:var(--muted)">uses</span>' + uses.map(p => '<button type="button" class="chip" data-open="' + p + '"><math>' + O[p].ml + '</math></button>').join('') : '') +
      (usedBy.length ? '<span style="color:var(--muted)">used by</span>' + usedBy.map(x => '<button type="button" class="chip" data-open="' + x.id + '"><math>' + x.ml + '</math></button>').join('') : '') +
      (!uses.length && !usedBy.length ? '<span style="color:var(--muted)">stands alone</span>' : '') + '</div>';
    h += '<p style="color:var(--muted);font-size:12px;margin:12px 0 0">Object version ' + esc(o.version) + '</p>';
  }
  $('#tab').innerHTML = h;
}

/* ---------- overview ---------- */
function renderOverview() {
  state.view = 'overview'; renderTree();
  const objs = Object.values(O), n = s => objs.filter(o => o.status === s).length;
  const withRef = objs.filter(o => o.reference && o.reference.status === 'agrees').length;
  const src = KB.sources;
  let h = '<section class="head"><h2>Sources and coverage</h2><p class="ref">' + esc(KB.meta.title || '') + ' · ' + esc(KB.meta.branch || '') + '</p></section>';
  h += '<section class="panel"><h3>What the knowledge base holds</h3><div class="cols">' +
    '<div class="stat"><b>' + objs.length + '</b><span>calculation objects</span></div>' +
    '<div class="stat"><b>' + (n('consensus') + n('unified')) + '</b><span>confirmed by two or more independent sources</span></div>' +
    '<div class="stat"><b>' + n('single source') + '</b><span>seen in one source only</span></div>' +
    '<div class="stat"><b>' + n('disagreement') + '</b><span>where sources disagree</span></div>' +
    '<div class="stat"><b>' + withRef + '</b><span>agree with the independent reference' + (KB.meta.reference_library ? ' (' + esc(KB.meta.reference_library) + ')' : '') + '</span></div>' +
    '<div class="stat"><b>' + objs.reduce((a, o) => a + o.bench.total, 0) + '</b><span>source values used as benchmarks</span></div></div></section>';
  h += '<section class="panel"><h3>Sources</h3><div class="scroll"><table class="t"><tr><th>Source</th><th>Converted with</th><th>Statements</th><th>Formulas re-evaluated</th><th>Recognised</th><th>Formulas of code quantities</th><th>Remark</th></tr>';
  src.forEach(s => {
    const rem = [];
    if (s.stored_results) rem.push(s.stored_results.agree + ' of ' + s.stored_results.compared + ' results stored by Mathcad reproduced');
    if (s.print_of) rem.push('a print of ' + s.print_of + ': benchmark only, not an independent source');
    if (s.printed_values) rem.push(s.printed_values + ' printed quantities');
    h += '<tr><td>' + esc(s.label) + '</td><td>' + esc(s.converter) + '</td><td class="num">' + s.statements + '</td><td class="num">' + (s.formulas ? s.formulas_verified + ' of ' + s.formulas + ' reproduce the source' : '–') +
      '</td><td class="num">' + s.recognised + '</td><td class="num">' + s.instances + '</td><td>' + esc(rem.join('; ')) + '</td></tr>';
  });
  h += '</table></div></section>';
  h += '<section class="panel"><h3>Objects by status</h3><div class="scroll"><table class="t"><tr><th>Object</th><th>Clause</th><th>Status</th><th>Sources</th><th>Benchmarks</th><th>Reference</th></tr>';
  objs.forEach(o => {
    h += '<tr><td><button type="button" class="chip" data-open="' + o.id + '"><math>' + o.ml + '</math></button> ' + esc(o.name) + '</td><td>' + esc(o.ref) + '</td><td><span class="pill ' + statusClass(o.status) + '">' + esc(statusText(o.status)) + '</span></td><td class="num">' +
      (o.support.sources || 0) + '</td><td class="num">' + o.bench.agree + ' / ' + o.bench.total + '</td><td>' + esc(o.reference && o.reference.status ? o.reference.status : '–') + '</td></tr>';
  });
  h += '</table></div></section>';
  $('#main').innerHTML = h;
}

/* ---------- events ---------- */
let titleBlock = {};
try { titleBlock = JSON.parse(localStorage.getItem('ckb-titleblock') || '{}'); } catch (e) { titleBlock = {}; }
function copy(text, where) {
  const done = ok => { const n = $(where); if (n) { n.textContent = ok ? 'Copied' : 'Select the text and copy it'; setTimeout(() => { n.textContent = ''; }, 2500); } };
  try { navigator.clipboard.writeText(text).then(() => done(true), () => done(false)); } catch (e) { done(false); }
}
document.addEventListener('click', ev => {
  const t = ev.target.closest('button'); if (!t) return;
  if (t.id === 'ovw') return renderOverview();
  if (t.dataset.id) return select(t.dataset.id);
  if (t.dataset.open) return select(t.dataset.open);
  if (t.dataset.tab) { state.tab = t.dataset.tab; return renderObject(); }
  if (t.dataset.give) {
    const g = t.dataset.give, r = state.last, st = r && r.steps.find(s => s.id === g);
    state.given[state.id][g] = true; if (st && typeof st.value === 'number') state.vals[g] = st.value;
    state.ex[state.id] = -1; renderInputs(); renderSheet(); return;
  }
  if (t.dataset.calc) {
    delete state.given[state.id][t.dataset.calc];
    plan(state.id, state.given[state.id]).inputs.forEach(p => { if (state.vals[p] === undefined) state.vals[p] = startValue(p); });
    state.ex[state.id] = -1; renderInputs(); renderSheet(); return;
  }
  if (t.id === 'copycalc') return copy(calcText(), '#copied');
  if (t.id === 'copypy') return copy(O[state.id].python, '#copied2');
  if (t.id === 'print') return window.print();
});
document.addEventListener('input', ev => {
  const t = ev.target;
  if (t.id === 'q') return renderTree();
  if (t.dataset && t.dataset.p) {
    const p = t.dataset.p, v = parseFloat(t.value);
    state.vals[p] = Number.isNaN(v) ? undefined : v * item(p).factor;
    if (state.ex[state.id] !== -1) { state.ex[state.id] = -1; const s = $('#ex'); if (s) s.value = '-1'; }
    return renderSheet();
  }
  if (t.id === 'chk') {
    const v = parseFloat(t.value); const c = item(O[state.id].check);
    state.check[state.id] = Number.isNaN(v) ? undefined : v * c.factor;
    const pos = t.selectionStart; renderSheet(); const n = $('#chk'); if (n) { n.focus(); }
    return;
  }
  if (t.dataset && t.dataset.tb) {
    titleBlock[t.dataset.tb] = t.value;
    try { localStorage.setItem('ckb-titleblock', JSON.stringify(titleBlock)); } catch (e) { /* storage unavailable */ }
  }
});
document.addEventListener('change', ev => {
  if (ev.target.id === 'ex') {
    const k = parseInt(ev.target.value, 10);
    if (k >= 0) loadExample(state.id, k); else state.ex[state.id] = -1;
    plan(state.id, state.given[state.id]).inputs.forEach(p => { if (state.vals[p] === undefined) state.vals[p] = startValue(p); });
    renderInputs(); renderSheet();
  }
});

(function start() {
  const objs = Object.values(O);
  const indep = KB.sources.filter(s => !s.print_of).length;
  $('#tagline').textContent = objs.length + ' calculation objects distilled from ' + KB.sources.length + ' source file' + (KB.sources.length === 1 ? '' : 's') +
    ' (' + indep + ' independent) · ' + (KB.meta.code || '') + ' · units inside: ' + (KB.meta.units || '');
  if (!objs.length) { $('#main').innerHTML = '<section class="panel">The knowledge base is empty. Put source files in the inbox and run the build.</section>'; return; }
  const rank = o => (o.status === 'unified' ? 0 : o.status === 'consensus' ? 1 : 2) * 1e6 - (o.support.formula_instances || 0) - o.params.length;
  select(objs.slice().sort((a, b) => rank(a) - rank(b))[0].id);
})();
</script>
"""
