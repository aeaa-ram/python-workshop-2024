"""Command line: ``python -m ckb <command>``.

    build            inbox -> knowledge base, code blocks, web calculator (all stages)
    convert          one file -> machine-readable statements and a Python script
    codes            the codes in the registry, their chapters and shared objects
    list             the objects, by code and chapter, with their confidence
    search           find an object by symbol, clause or words ("concrete shear")
    show             one object: formula, inputs, conditions, design background
    status           the evidence behind one object: sources, benchmarks, reference
    run              calculate in the terminal
    report           calculation report (HTML, PDF): one case, or a template over many cases
    report-template  a commented report template (YAML) to start from
    excel            Excel calculator with live formulas and named ranges
    mathcad          Mathcad Prime worksheet
    verify           does a file (xlsx, mcdx, py, html, pdf) carry the knowledge base's logic?
    app              rebuild the web calculator (--files: with Excel and Mathcad downloads inside)
    share            a package for people without Python: the web calculator with downloads, zipped
    check            place a new source file against the knowledge base
    questions        differences between the sources and the code that nothing explained
    answer           answer one of those questions (applied in the next build)
    tools            tool definitions for an AI assistant
    health           re-run every check on the knowledge base

Number style (every output): ``--decimals 3``, ``--unit V_Rd_c=kN --unit d=m``,
or ``--style style.yaml``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import sys
from pathlib import Path

from . import expr as X
from . import units as U

ROOT = Path(__file__).resolve().parent.parent
DOTS = {"high": "●", "medium": "◐", "low": "○"}


def _kb(args):
    from .kb.objects import KnowledgeBase
    try:
        return KnowledgeBase.load(args.kb)
    except FileNotFoundError as exc:
        sys.exit(str(exc))


def _target(kb, name: str) -> str:
    from .use.calc import lookup
    oid = lookup(kb, name, among=kb.objects)
    if oid is None:
        from .distill.taxonomy import load
        from .kb.search import search
        hits = search(kb, load(), name, 3)
        hint = ("  Did you mean: " + ", ".join(kb.objects[h[1]].text for h in hits)) if hits else ""
        sys.exit(f"No calculation object {name!r}.{hint}  (python -m ckb list)")
    return oid


def _style(args):
    from .use.style import Style
    style = Style.load(Path(args.style) if getattr(args, "style", None) else None)
    if getattr(args, "decimals", None) is not None:
        style.decimals = args.decimals
    for pair in getattr(args, "unit", None) or []:
        name, _, unit = pair.partition("=")
        style.units[name.strip()] = unit.strip()
    return style


def _log_use(args, oid: str, surface: str, kb) -> None:
    try:
        ws = Path(args.workspace)
        ws.mkdir(parents=True, exist_ok=True)
        with open(ws / "usage.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"time": _dt.datetime.now().isoformat(timespec="seconds"), "object": oid,
                                 "version": kb.objects[oid].version, "surface": surface}) + "\n")
    except OSError:
        pass


def _fidelity(s: dict) -> str:
    if s["formulas"] and s["formulas_unverified"] == s["formulas"]:
        return f"{s['formulas']} formulas evaluated here (the file stores no calculated values to compare with)"
    return (f"{s['formulas_verified']} of {s['formulas']} formulas reproduce the value the source shows"
            + (f"; {s['formulas_mismatch']} differ, {s['formulas_failed']} not evaluated"
               if s["formulas_mismatch"] + s["formulas_failed"] else ""))


def _topic_key(o):
    return [int(x) if x.isdigit() else 0 for x in o.topic.split(".")], o.id


# --------------------------------------------------------------------------
def cmd_build(args):
    from .pipeline import build
    from .use.webapp import write
    llm = None
    if args.vision or args.ask_model:
        from .llm import get_llm_client
        llm = get_llm_client()
    out = build(Path(args.inbox), Path(args.workspace), Path(args.kb), anonymous=args.anonymous, vision=args.vision,
                llm=llm, ask_model=args.ask_model)
    app = write(out.kb, Path(args.app))
    print(f"[6] web calculator -> {app}")
    print(f"    report of this run -> {Path(args.workspace) / 'distillation_report.md'}")
    for s in out.skipped:
        print(f"    skipped: {s['file']} - {s['reason']}")


def cmd_convert(args):
    from .convert import ConversionError, convert_file
    try:
        doc = convert_file(Path(args.file), vision=args.vision)
    except ConversionError as exc:
        sys.exit(f"Not converted: {exc}")
    out = Path(args.workspace) / "converted"
    stem = Path(args.file).stem
    doc.save(out / f"{stem}.json")
    if doc.python:
        (out / f"{stem}.py").write_text(doc.python, encoding="utf-8")
    s = doc.summary()
    print(f"{doc.name}: {doc.converter}")
    print(f"  {s['statements']} statements: {s['inputs']} inputs, {s['formulas']} formulas, {s['printed_values']} printed values")
    if s["formulas"]:
        print("  " + _fidelity(s))
    if doc.meta.get("stored_results"):
        r = doc.meta["stored_results"]
        print(f"  {r['agree']} of {r['compared']} results stored by Mathcad reproduced")
    for issue in doc.issues[:15]:
        print(f"  ! {issue}")
    print(f"  -> {out / (stem + '.json')}" + (f", {out / (stem + '.py')}" if doc.python else ""))
    if args.show:
        for st in doc.statements[:args.show]:
            v = st.best_value()
            shown = v if isinstance(v, str) or v is None else U.fmt(U.from_canonical(v, st.unit) if (st.canonical and st.unit) else v, 6)
            f = X.to_text(st.expr) if st.expr is not None and st.kind == "calc" else ""
            print(f"    {st.name[:18]:18} = {str(shown):>12} {st.unit:7} {st.fidelity:10} {st.label[:40]:40} {f[:70]}")


def cmd_codes(args):
    kb = _kb(args)
    for c in kb.codes:
        own = [o for o in kb.objects.values() if o.code == c["code"]]
        shared = [o for o in kb.objects.values() if any(r["code"] == c["code"] for r in o.refs)]
        print(f"\n{c['code']}  {c.get('title', '')}")
        print(f"  {len(own)} objects of its own" + (f", {len(shared)} shared with an earlier code" if shared else ""))
        if c.get("fixed"):
            print("  fixes: " + ", ".join(f"{kb.name(k)} = {U.fmt(v)}" for k, v in c["fixed"].items()))
        for o in shared:
            r = next(r for r in o.refs if r["code"] == c["code"])
            print(f"    {r.get('symbol', o.id):10} cl. {r.get('clause', ''):12} -> {o.text} of {o.code} ({r.get('how', '')})")


def cmd_list(args):
    kb = _kb(args)
    for code in [c["code"] for c in kb.codes] + [""]:
        objs = sorted((o for o in kb.objects.values() if o.code == code), key=_topic_key)
        if not objs:
            continue
        print(f"\n{code or 'Definitions used by every code'}")
        topic = None
        for o in objs:
            if o.topic != topic:
                topic = o.topic
                print(f"  {' > '.join(o.topic_path)}")
            dot = DOTS.get(o.confidence.get("level"), " ")
            print(f"    {dot} {o.id:12} {o.text:12} {o.reference_text.replace(o.code + ' ', ''):34} {o.name}")
    print(f"\n{len(kb.objects)} objects, {len(kb.quantities)} parameters.   "
          "● checked  ◐ not yet checked  ○ review needed   (python -m ckb status <object>)")


def cmd_search(args):
    from .distill.taxonomy import load
    from .kb.search import search
    kb = _kb(args)
    hits = search(kb, load(), " ".join(args.query))
    if not hits:
        print("Nothing found. `python -m ckb list` shows what the knowledge base holds.")
    for score, oid, why in hits:
        o = kb.objects[oid]
        print(f"  {o.id:12} {o.text:12} {o.reference_text:42} {o.name}   [{why}]")


def cmd_show(args):
    """The design logic of one object - what a calculation uses."""
    kb = _kb(args)
    o = kb.objects[_target(kb, args.object)]
    print(f"{o.text} - {o.name}\n{o.reference_text}\n{' > '.join(o.topic_path)}\n")
    print(f"  {o.text} = {X.to_text(o.tree, kb.name)}      [{o.unit}]")
    for a in o.alternatives:
        print(f"  alternative: {o.text} = {a.get('formula')}   {a.get('text', '')}")
    if o.fixed:
        print(f"  with {', '.join(f'{kb.name(k)} = {U.fmt(v)}' for k, v in o.fixed.items())} (fixed by {o.code})")
    for r in o.refs:
        print(f"  also {r['code']} cl. {r.get('clause', '')}: {r.get('how', '')}")
    steps, inputs = kb.plan(o.id)
    print(f"\nInputs: {', '.join(kb.name(p) for p in inputs)}")
    if len(steps) > 1:
        print(f"Calculated on the way: {', '.join(kb.name(p) for p in steps[:-1])}")
    if o.checks:
        print("\nConditions")
        for c in o.checks:
            print(f"  {c.get('text', c['when'])} ({c.get('clause', '')})")
    if o.background:
        print("\nDesign background")
        for b in o.background:
            refs = "; ".join(f"{r['id']} {r.get('at', '')}".strip() for r in b.get("refs", []))
            print(f"  [{b['kind']}] {b['text']}" + (f"  ({refs})" if refs else ""))
    print(f"\nversion {o.version}   (python -m ckb status {o.id} for the evidence)")


def cmd_status(args):
    """The evidence behind one object - kept out of every calculation."""
    kb = _kb(args)
    o = kb.objects[_target(kb, args.object)]
    c = o.confidence
    print(f"{o.text} - {o.name}  ({o.reference_text}, version {o.version})\n")
    print(f"Confidence: {c.get('label', '-')} {DOTS.get(c.get('level'), '')}")
    for r in c.get("reasons", []):
        print(f"  - {r}")
    ev = o.evidence
    print(f"\nSources: {ev.get('sources', 0)} file(s), {ev.get('formula_instances', 0)} formulas, "
          f"{ev.get('printed_values', 0)} printed values")
    for v in ev.get("variants", []):
        print(f"  {v.get('relation', ''):16} x{v.get('instances', 0):<3} {v.get('text', '')}")
        for d in v.get("differences", []):
            print(f"  {'':16}      - {d}")
        if v.get("reason"):
            print(f"  {'':16}      - {v['reason']}")
    for p in ev.get("practice", []):
        print(f"  practice: {p}")
    b = o.benchmarks
    if b.get("total"):
        print(f"\nBenchmarks: {b.get('agree', 0)} of {b['total']} source values reproduced"
              + (f", {b['deviation']} differ" if b.get("deviation") else "")
              + (f", {b['not_comparable']} not comparable" if b.get("not_comparable") else ""))
        for it in [i for i in b.get("items", []) if i["status"] == "deviation"][:args.rows]:
            k, unit = (1000.0, o.unit + "/m") if it.get("per_width") else (1.0, o.unit)
            print(f"  {it['source']} {it['where']}: source {U.fmt(kb.to_display(o.id, it['expected']) * k)}, "
                  f"code {U.fmt(kb.to_display(o.id, it['got']) * k)} {unit} - {it.get('detail', '')}")
    if o.reference:
        r = o.reference
        print(f"\nIndependent reference: {r.get('status')} with {r.get('library')} {r.get('function')} "
              f"({r.get('agreeing_samples', 0)} of {r.get('samples', 0)} samples)" + (f". {r['note']}" if r.get("note") else ""))


def _values(kb, oid, args):
    from .use.calc import parse_assignments, starting_values
    try:
        entered, given = parse_assignments(kb, oid, args.set or [])
    except ValueError as exc:
        sys.exit(str(exc))
    check = None
    obj = kb.objects[oid]
    if obj.check and obj.check in entered and obj.check not in kb.plan(oid, given)[1]:
        check = entered.pop(obj.check)
    values, origin = starting_values(kb, oid, given)
    for k, v in entered.items():
        values[k], origin[k] = v, "entered"
    if getattr(args, "check", None) is not None and obj.check:
        check = kb.from_display(obj.check, args.check)
    return values, origin, given, check


def cmd_run(args):
    from .kb.objects import ResolveError
    from .use.calc import run
    from .use.prompt import ask
    from .use.report import render_text
    kb = _kb(args)
    oid = _target(kb, args.object)
    values, origin, given, check = _values(kb, oid, args)
    style = _style(args)
    try:
        if args.ask or (not args.set and sys.stdin.isatty()):
            ask(kb, oid, preset={k: v for k, v in values.items() if origin.get(k) == "entered"}, given=given,
                style=style)
        else:
            print(render_text(kb, run(kb, oid, values, given, origin, check, style)))
    except ResolveError as exc:
        sys.exit(str(exc))
    _log_use(args, oid, "terminal", kb)


def cmd_report(args):
    from .use import report as R
    kb = _kb(args)
    style = _style(args)
    if args.template:
        path = Path(args.template)
        template = R.load_template(path)
        base = path.parent
    elif args.object:
        oid = _target(kb, args.object)
        values, origin, given, check = _values(kb, oid, args)
        entered = {k: v for k, v in values.items() if origin.get(k) == "entered"}
        template = R.quick_template(oid, entered, kb, check, style=style)
        base = Path.cwd()
    else:
        sys.exit("Name an object (python -m ckb report V_Rd_c d=450 ...) or a template (--template report.yaml).")
    if args.cases:
        template["cases"] = {"file": str(Path(args.cases).resolve())}
    if args.from_excel:
        template["cases"] = R.cases_from_calculator(kb, Path(args.from_excel))
    if args.decimals is not None or args.unit or args.style:
        merged = R.Style.load(template.get("style") or {})
        merged.decimals = style.decimals if args.decimals is not None or args.style else merged.decimals
        merged.units.update(style.units)
        template["style"] = merged.to_dict()
    for opt in ("project", "made_by", "checked_by", "number"):
        if getattr(args, opt, ""):
            template[opt] = getattr(args, opt)
    try:
        page, used = R.render(kb, template, base, with_objects=True)
    except ValueError as exc:
        sys.exit(str(exc))
    name = Path(args.template).stem if args.template else template["blocks"][0]["calc"]
    out = Path(args.output or Path(args.workspace) / "reports" / f"{name}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"report -> {out}")
    if args.pdf:
        pdf = out.with_suffix(".pdf")
        print(f"PDF (with bookmarks) -> {pdf}" if R.to_pdf(out, pdf) else
              "PDF not written: no Chromium-based browser found (open the HTML and print it to PDF).")
    if args.docx:
        from .use.report_docx import render_docx
        print(f"Word -> {render_docx(kb, template, out.with_suffix('.docx'), base)}")
    for oid in used:
        _log_use(args, oid, "report", kb)


def cmd_report_template(args):
    from .use.report import example_template
    kb = _kb(args)
    oid = _target(kb, args.object)
    text = example_template(kb, oid)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"report template -> {args.output}   (python -m ckb report --template {args.output} --pdf)")
    else:
        print(text)


def cmd_excel(args):
    from .use.excel_bridge import export_calculator, verify
    kb = _kb(args)
    oid = _target(kb, args.object)
    values, _, given, _ = _values(kb, oid, args)
    out = Path(args.output or Path(args.workspace) / "excel" / f"{oid}.xlsx")
    export_calculator(kb, oid, out, values, given, _style(args), refs=args.refs)
    print(f"Excel calculator -> {out}")
    if args.verify:
        _print_verify(verify(kb, out))
    _log_use(args, oid, "excel", kb)


def cmd_mathcad(args):
    from .use.mathcad_export import export_worksheet, verify
    kb = _kb(args)
    oid = _target(kb, args.object)
    values, _, given, _ = _values(kb, oid, args)
    out = Path(args.output or Path(args.workspace) / "mathcad" / f"{oid}.mcdx")
    export_worksheet(kb, oid, out, values, given, _style(args))
    print(f"Mathcad Prime worksheet -> {out}")
    if args.verify:
        _print_verify(verify(kb, out))
    _log_use(args, oid, "mathcad", kb)


def _print_verify(res: dict) -> None:
    if "reason" in res and not res.get("rows"):
        print(f"  not verified: {res['reason']}")
        return
    if "version_in_file" in res:
        same = res.get("same_version")
        print(f"  {res.get('object', '')}: version in the file {res['version_in_file']}, "
              f"in the knowledge base {res['version_now']}" + ("  (same)" if same else "  (CHANGED since)"))
    if res.get("edited"):
        print("  formulas edited in the file: " + ", ".join(res["edited"]))
    if isinstance(res.get("numbers"), str):
        print(f"  numbers {res['numbers']}")
    rows = res.get("rows", [])
    bad = [r for r in rows if not r.get("agree")]
    if rows:
        what = ("objects (versions)" if "version_in_file" in rows[0] else
                "test points" if "inputs" in rows[0] else "steps")
        print(f"  {len(rows) - len(bad)} of {len(rows)} {what} agree with the knowledge base")
    for r in bad[:10]:
        print("  differs: " + ", ".join(f"{k}={v}" for k, v in r.items() if k != "agree"))
    if res.get("note"):
        print(f"  ({res['note']})")
    print("  -> " + ("same logic" if res.get("ok") else "NOT the same logic, or not checkable (see above)"))


def cmd_verify(args):
    from .use.verify import verify
    kb = _kb(args)
    ok = True
    for f in args.files:
        print(f)
        res = verify(kb, Path(f))
        _print_verify(res)
        ok &= bool(res.get("ok"))
    if not ok:
        sys.exit(1)


def cmd_app(args):
    from .use.webapp import write
    kb = _kb(args)
    files = None
    if args.files:
        from .use.share import calculator_files
        files = calculator_files(kb)
    print(f"web calculator -> {write(kb, Path(args.output or args.app), standalone=not args.fragment, files=files)}")


def cmd_share(args):
    from .use.share import write_bundle
    kb = _kb(args)
    zip_path = write_bundle(kb, Path(args.output))
    print(f"workshop package -> {Path(args.output)}  and  {zip_path}")
    print("  open index.html in a browser; share the zip on SharePoint or Teams")


def cmd_check(args):
    from .convert import ConversionError, convert_file
    from .distill.taxonomy import load
    from .kb.search import classify
    from .use.excel_bridge import read_calculator
    kb = _kb(args)
    path = Path(args.file)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        rec = read_calculator(path)
        if rec:
            o = kb.objects.get(rec["object"])
            print(f"This workbook was generated from {o.text if o else rec['object']} (version {rec['version']}"
                  + (", current)" if o and o.version == rec["version"] else ", the object has changed since)"))
            print("  formulas: " + ("unchanged" if not rec["changed_formulas"] else
                                    "edited in " + ", ".join(kb.name(k) for k in rec["changed_formulas"])))
    try:
        doc = convert_file(path, vision=args.vision)
    except ConversionError as exc:
        sys.exit(f"Not converted: {exc}")
    doc.id = "NEW"
    res = classify(doc, kb, load())
    c = res["conversion"]
    print(f"{doc.name}: {c['statements']} statements; {_fidelity(c)}")
    print("  " + ", ".join(f"{n} {k}" for k, n in sorted(res["summary"].items())) if res["summary"] else "  no formulas found")
    order = {"differs": 0, "simplified": 1, "new object": 2, "as code": 3, "project-specific": 4, "new topic": 5}
    shown = 0
    for r in sorted(res["rows"], key=lambda r: order.get(r["verdict"], 9)):
        if r["verdict"] == "new topic" and not args.all:
            continue
        if shown >= args.rows:
            break
        rep = "" if "reproduced" not in r else ("  [object reproduces the value]" if r["reproduced"] else "  [object gives a different value]")
        print(f"  {r['verdict']:16} {r['quantity']:12} {r['where']}: {r['detail']}{rep}")
        shown += 1
    if not args.all and res["summary"].get("new topic"):
        print(f"  ({res['summary']['new topic']} formulas of unknown quantities not listed; --all shows them)")


def cmd_questions(args):
    import yaml
    f = Path(args.workspace) / "questions.yaml"
    qs = (yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else None) or []
    if not qs:
        print("No open questions: every difference between the sources and the code was explained.")
        return
    for q in qs:
        print(f"\n{q['id']}  {q['object']} at {q['source']} {q['where']}" + (f" ({q['case']})" if q.get("case") else ""))
        print(f"  source {q['source_value']:.6g}, code {q['code_value']:.6g}")
        if q.get("formula_in_source"):
            print(f"  source formula: {q['formula_in_source']}")
        for p, v in q.get("inputs", {}).items():
            print(f"    {p:10} = {v['value']:.6g}   ({v['from']})")
        print("  tried: " + "; ".join(q.get("tried", [])))
        for h in q.get("would_agree_if", []):
            print(f"  would agree if {h}")
        if q.get("ai_proposal"):
            print(f"  language model proposes: {q['ai_proposal']}")
    print(f"\n{len(qs)} question(s). Answer: python -m ckb answer <id> --verdict explained --text '...' [--lesson '...']")


def cmd_answer(args):
    import yaml
    f = Path(args.workspace) / "answers.yaml"
    data = (yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else None) or {}
    data[args.id] = {"verdict": args.verdict, "answer": args.text,
                     **({"lesson": args.lesson} if args.lesson else {}),
                     "date": _dt.date.today().isoformat()}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True), encoding="utf-8")
    print(f"answer to {args.id} saved in {f}; it is applied in the next build"
          + ("; the lesson becomes design background of the object" if args.lesson else ""))


def cmd_tools(args):
    from .use.toolschema import definitions
    kb = _kb(args)
    text = json.dumps(definitions(kb), indent=1, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"{len(kb.objects)} tool definitions -> {args.output}")
    else:
        print(text)


def cmd_health(args):
    from .maintain.health import check
    kb = _kb(args)
    res = check(kb, Path(args.kb))
    for r in res["rows"]:
        mark = "ok  " if not r["problems"] else "FAIL"
        print(f"  {mark} {r['object']:12} {r['benchmarks_rerun']:>3} benchmarks re-run   code block: {r.get('code_block', '-'):7} "
              f"reference: {r.get('reference', '-'):8} uses: {r['uses']}")
        for p in r["problems"]:
            print(f"         ! {p}")
    print(f"\n{res['healthy']} of {res['objects']} objects healthy" + (f" (reference: {res['reference_library']})" if res["reference_library"] else ""))
    if res["problems"]:
        sys.exit(1)


def _style_args(s):
    s.add_argument("--decimals", type=int, help="digits after the decimal point (default 2)")
    s.add_argument("--unit", action="append", metavar="name=unit", help="display unit, e.g. V_Rd_c=kN (repeatable)")
    s.add_argument("--style", help="a style YAML file (decimals, min_significant, units)")


def main(argv=None):
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="python -m ckb", description="Calculation knowledge base")
    p.add_argument("--kb", default=str(ROOT / "knowledge_base"), help="knowledge base folder")
    p.add_argument("--workspace", default=str(ROOT / "workspace"), help="folder for converted sources and outputs")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("build", help="inbox -> knowledge base and web calculator")
    s.add_argument("--inbox", default=str(ROOT / "inbox"))
    s.add_argument("--app", default=str(ROOT / "app" / "index.html"))
    s.add_argument("--anonymous", action="store_true", help="leave file and sheet names out of the knowledge base")
    s.add_argument("--vision", action="store_true", help="also read formulas from PDFs with a vision model")
    s.add_argument("--ask-model", action="store_true",
                   help="ask a language model for its reading of differences nothing else explains")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("convert", help="one file -> machine-readable statements")
    s.add_argument("file")
    s.add_argument("--show", type=int, default=0, metavar="N", help="print the first N statements")
    s.add_argument("--vision", action="store_true")
    s.set_defaults(fn=cmd_convert)

    sub.add_parser("codes", help="codes, chapters and shared objects").set_defaults(fn=cmd_codes)
    sub.add_parser("list", help="objects by code and chapter").set_defaults(fn=cmd_list)
    s = sub.add_parser("search", help="find an object")
    s.add_argument("query", nargs="+")
    s.set_defaults(fn=cmd_search)
    s = sub.add_parser("show", help="one object: formula, conditions, design background")
    s.add_argument("object")
    s.set_defaults(fn=cmd_show)
    s = sub.add_parser("status", help="the evidence behind one object")
    s.add_argument("object")
    s.add_argument("--rows", type=int, default=6)
    s.set_defaults(fn=cmd_status)

    for name, fn, text in (("run", cmd_run, "calculate in the terminal"),
                           ("excel", cmd_excel, "Excel calculator with live formulas"),
                           ("mathcad", cmd_mathcad, "Mathcad Prime worksheet")):
        s = sub.add_parser(name, help=text)
        s.add_argument("object")
        s.add_argument("set", nargs="*", metavar="name=value", help="inputs, e.g. d=450 f_ck=30 'b_w=0.3 m'")
        s.add_argument("--check", type=float, help="design value to check against (e.g. V_Ed in kN)")
        _style_args(s)
        if name == "run":
            s.add_argument("--ask", action="store_true", help="ask for every input")
        else:
            s.add_argument("-o", "--output")
            s.add_argument("--verify", action="store_true", help="read the file back and compare with the knowledge base")
        if name == "excel":
            s.add_argument("--refs", choices=["names", "cells"], default="names",
                           help="formulas with named ranges (=A_sl/(b_w*d)) or cell references (=C8/(C9*C7))")
        s.set_defaults(fn=fn)

    s = sub.add_parser("report", help="calculation report (HTML, PDF)")
    s.add_argument("object", nargs="?", help="one object, for a one-case report")
    s.add_argument("set", nargs="*", metavar="name=value")
    s.add_argument("--check", type=float, help="design value to check against (e.g. V_Ed in kN)")
    s.add_argument("--template", help="report template (YAML); see `report-template`")
    s.add_argument("--cases", help="cases table (xlsx, csv, yaml) replacing the template's cases")
    s.add_argument("--from-excel", help="take the inputs from an Excel calculator generated by `excel`")
    s.add_argument("-o", "--output")
    s.add_argument("--pdf", action="store_true", help="also print to PDF with bookmarks (needs Edge, Chrome or Chromium)")
    s.add_argument("--docx", action="store_true", help="also write a Word document with native equations")
    for opt in ("project", "made-by", "checked-by", "number"):
        s.add_argument(f"--{opt}", default="")
    _style_args(s)
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("report-template", help="a commented report template to start from")
    s.add_argument("object")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_report_template)

    s = sub.add_parser("verify", help="does a file carry the knowledge base's logic?")
    s.add_argument("files", nargs="+")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("app", help="rebuild the web calculator")
    s.add_argument("-o", "--output")
    s.add_argument("--app", default=str(ROOT / "app" / "index.html"))
    s.add_argument("--fragment", action="store_true", help="page content only (for embedding)")
    s.add_argument("--files", action="store_true",
                   help="embed an Excel calculator and a Mathcad worksheet per object (downloads without Python)")
    s.set_defaults(fn=cmd_app)

    s = sub.add_parser("share", help="a package for people without Python: the web calculator with downloads, zipped")
    s.add_argument("-o", "--output", default=str(ROOT / "workspace" / "workshop"))
    s.set_defaults(fn=cmd_share)

    s = sub.add_parser("check", help="place a new source against the knowledge base")
    s.add_argument("file")
    s.add_argument("--rows", type=int, default=25)
    s.add_argument("--all", action="store_true")
    s.add_argument("--vision", action="store_true")
    s.set_defaults(fn=cmd_check)

    sub.add_parser("questions", help="differences nothing explained, for an engineer").set_defaults(fn=cmd_questions)
    s = sub.add_parser("answer", help="answer a question (applied in the next build)")
    s.add_argument("id")
    s.add_argument("--verdict", default="explained", choices=["explained", "source-error", "project-specific"])
    s.add_argument("--text", default="", help="the explanation")
    s.add_argument("--lesson", default="", help="a general lesson to keep with the object (design background)")
    s.set_defaults(fn=cmd_answer)

    s = sub.add_parser("tools", help="tool definitions for an AI assistant")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_tools)
    sub.add_parser("health", help="re-run every check").set_defaults(fn=cmd_health)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
