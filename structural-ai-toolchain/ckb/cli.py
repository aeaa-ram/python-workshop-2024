"""Command line: ``python -m ckb <command>``.

    build     inbox -> knowledge base, web calculator (all stages)
    convert   one file -> machine-readable statements and a Python script
    list      the objects, by clause
    search    find an object by symbol, clause or words
    show      one object: formula, variants, benchmarks, reference
    run       calculate in the terminal (asks for the inputs)
    report    calculation sheet as HTML (and PDF)
    excel     Excel calculator with live formulas
    app       rebuild the web calculator
    check     place a new source file against the knowledge base
    tools     tool definitions for an AI assistant
    health    re-run every check on the knowledge base
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
        return (f"{s['formulas']} formulas evaluated here (the file stores no calculated values to compare with)")
    return (f"{s['formulas_verified']} of {s['formulas']} formulas reproduce the value the source shows"
            + (f"; {s['formulas_mismatch']} differ, {s['formulas_failed']} not evaluated"
               if s["formulas_mismatch"] + s["formulas_failed"] else ""))


def cmd_build(args):
    from .pipeline import build
    from .use.webapp import write
    out = build(Path(args.inbox), Path(args.workspace), Path(args.kb), anonymous=args.anonymous, vision=args.vision)
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


def cmd_list(args):
    kb = _kb(args)
    topic = None
    for o in sorted(kb.objects.values(), key=lambda o: ([int(x) for x in o.topic.split(".") if x.isdigit()], o.id)):
        if o.topic != topic:
            topic = o.topic
            print(f"\n{' > '.join(o.topic_path)}")
        b = o.benchmarks
        print(f"  {o.id:12} {o.text:12} {o.status:14} {b.get('agree', 0):>3}/{b.get('total', 0):<3} benchmarks  "
              f"ref: {(o.reference or {}).get('status', '-'):8} {o.name}")
    print(f"\n{len(kb.objects)} objects, {len(kb.quantities)} parameters. `python -m ckb show <object>` for the evidence.")


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
    kb = _kb(args)
    o = kb.objects[_target(kb, args.object)]
    print(f"{o.text} - {o.name}\n{o.reference_text}\n{' > '.join(o.topic_path)}\n")
    print(f"  {o.text} = {X.to_text(o.tree, kb.name)}\n")
    s = o.support
    print(f"Status: {o.status} - {s.get('formula_instances', 0)} formulas in {s.get('sources', 0)} independent source(s), "
          f"{s.get('variants_merged', 0)} variant(s) merged")
    print("\nVariants")
    for v in o.variants:
        print(f"  {'merged    ' if v['merged'] else 'kept apart'} x{v['instances']:<3} {v['text']}   ({', '.join(v['sources'])})")
        for d in v["differences"]:
            print(f"               - {d}")
        if v.get("reason"):
            print(f"               - {v['reason']}")
    b = o.benchmarks
    print(f"\nBenchmarks: {b.get('agree', 0)} of {b.get('total', 0)} source values reproduced"
          + (f", {b['deviation']} differ" if b.get("deviation") else "")
          + (f", {b['not_comparable']} not comparable" if b.get("not_comparable") else ""))
    for it in [i for i in b.get("items", []) if i["status"] == "deviation"][:args.rows]:
        k, unit = (1000.0, o.unit + "/m") if it.get("per_width") else (1.0, o.unit)
        print(f"  differs at {it['source']} {it['where']}: source {U.fmt(kb.to_display(o.id, it['expected']) * k)}, "
              f"unified {U.fmt(kb.to_display(o.id, it['got']) * k)} {unit} - {it.get('detail', '')}")
    if o.reference:
        r = o.reference
        print(f"\nReference: {r['status']} with {r['library']} {r['function']} "
              f"({r['agreeing_samples']} of {r['samples']} samples)" + (f". {r['note']}" if r.get("note") else ""))
    for w in o.warnings:
        print(f"\nWarning: {w}")
    for w in o.findings:
        print(f"Finding: {w}")
    for n in o.notes:
        print(f"Note: {n}")
    steps, inputs = kb.plan(o.id)
    print(f"\nInputs when resolved: {', '.join(kb.name(p) for p in inputs)}")
    if len(steps) > 1:
        print(f"Calculated on the way: {', '.join(kb.name(p) for p in steps[:-1])}")


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
    try:
        if args.ask or (not args.set and sys.stdin.isatty()):
            ask(kb, oid, preset={k: v for k, v in values.items() if origin.get(k) == "entered"}, given=given)
        else:
            print(render_text(kb, run(kb, oid, values, given, origin, check)))
    except ResolveError as exc:
        sys.exit(str(exc))
    _log_use(args, oid, "terminal", kb)


def cmd_report(args):
    from .kb.objects import ResolveError
    from .use.calc import run
    from .use.report import render_html, to_pdf
    kb = _kb(args)
    oid = _target(kb, args.object)
    values, origin, given, check = _values(kb, oid, args)
    try:
        res = run(kb, oid, values, given, origin, check)
    except ResolveError as exc:
        sys.exit(str(exc))
    out = Path(args.output or Path(args.workspace) / "reports" / f"{oid}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"project": args.project, "made_by": args.made_by, "checked_by": args.checked_by, "number": args.number}
    out.write_text(render_html(kb, res, meta), encoding="utf-8")
    print(f"calculation sheet -> {out}")
    if args.pdf:
        pdf = out.with_suffix(".pdf")
        print(f"PDF -> {pdf}" if to_pdf(out, pdf) else
              "PDF not written: no Chromium-based browser found (open the HTML and print it to PDF).")
    _log_use(args, oid, "report", kb)


def cmd_excel(args):
    from .use.excel_bridge import export_calculator, verify
    kb = _kb(args)
    oid = _target(kb, args.object)
    values, origin, given, _ = _values(kb, oid, args)
    out = Path(args.output or Path(args.workspace) / "excel" / f"{oid}.xlsx")
    export_calculator(kb, oid, out, values, given)
    print(f"Excel calculator -> {out}")
    if args.verify:
        v = verify(kb, oid, out, values, given)
        if v is None:
            print("not verified: LibreOffice is not installed (Excel itself will calculate the formulas)")
        else:
            print("verified with LibreOffice: every step matches the knowledge base" if v["agree"]
                  else "LibreOffice gives different values: " + ", ".join(r["id"] for r in v["rows"] if not r["agree"]))
    _log_use(args, oid, "excel", kb)


def cmd_app(args):
    from .use.webapp import write
    kb = _kb(args)
    print(f"web calculator -> {write(kb, Path(args.output or args.app), standalone=not args.fragment)}")


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
    order = {"extension": 0, "differs": 1, "new object": 2, "existing": 3, "new topic": 4}
    shown = 0
    for r in sorted(res["rows"], key=lambda r: order.get(r["verdict"], 9)):
        if r["verdict"] == "new topic" and not args.all:
            continue
        if shown >= args.rows:
            break
        rep = "" if "reproduced" not in r else ("  [object reproduces the value]" if r["reproduced"] else "  [object gives a different value]")
        print(f"  {r['verdict']:11} {r['quantity']:12} {r['where']}: {r['detail']}{rep}")
        shown += 1
    if not args.all and res["summary"].get("new topic"):
        print(f"  ({res['summary']['new topic']} formulas of unknown quantities not listed; --all shows them)")


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


def main(argv=None):
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    p = argparse.ArgumentParser(prog="python -m ckb", description="Calculation knowledge base")
    p.add_argument("--kb", default=str(ROOT / "knowledge_base"), help="knowledge base folder")
    p.add_argument("--workspace", default=str(ROOT / "workspace"), help="folder for converted sources and outputs")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("build", help="inbox -> knowledge base and web calculator")
    s.add_argument("--inbox", default=str(ROOT / "inbox"))
    s.add_argument("--app", default=str(ROOT / "app" / "index.html"))
    s.add_argument("--anonymous", action="store_true", help="leave file and sheet names out of the knowledge base")
    s.add_argument("--vision", action="store_true", help="also read formulas from PDFs with a vision model")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("convert", help="one file -> machine-readable statements")
    s.add_argument("file")
    s.add_argument("--show", type=int, default=0, metavar="N", help="print the first N statements")
    s.add_argument("--vision", action="store_true")
    s.set_defaults(fn=cmd_convert)

    sub.add_parser("list", help="objects by clause").set_defaults(fn=cmd_list)
    s = sub.add_parser("search", help="find an object")
    s.add_argument("query", nargs="+")
    s.set_defaults(fn=cmd_search)
    s = sub.add_parser("show", help="one object with its evidence")
    s.add_argument("object")
    s.add_argument("--rows", type=int, default=6)
    s.set_defaults(fn=cmd_show)

    for name, fn, text in (("run", cmd_run, "calculate in the terminal"),
                           ("report", cmd_report, "calculation sheet (HTML, PDF)"),
                           ("excel", cmd_excel, "Excel calculator with live formulas")):
        s = sub.add_parser(name, help=text)
        s.add_argument("object")
        s.add_argument("set", nargs="*", metavar="name=value", help="inputs, e.g. d=450 f_ck=30 'b_w=0.3 m'")
        s.add_argument("--check", type=float, help="design value to check against (e.g. V_Ed in kN)")
        if name == "run":
            s.add_argument("--ask", action="store_true", help="ask for every input")
        else:
            s.add_argument("-o", "--output")
        if name == "report":
            s.add_argument("--pdf", action="store_true")
            for opt in ("project", "made-by", "checked-by", "number"):
                s.add_argument(f"--{opt}", default="")
        if name == "excel":
            s.add_argument("--verify", action="store_true", help="recalculate with LibreOffice and compare")
        s.set_defaults(fn=fn)

    s = sub.add_parser("app", help="rebuild the web calculator")
    s.add_argument("-o", "--output")
    s.add_argument("--app", default=str(ROOT / "app" / "index.html"))
    s.add_argument("--fragment", action="store_true", help="page content only (for embedding)")
    s.set_defaults(fn=cmd_app)

    s = sub.add_parser("check", help="place a new source against the knowledge base")
    s.add_argument("file")
    s.add_argument("--rows", type=int, default=25)
    s.add_argument("--all", action="store_true")
    s.add_argument("--vision", action="store_true")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("tools", help="tool definitions for an AI assistant")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_tools)
    sub.add_parser("health", help="re-run every check").set_defaults(fn=cmd_health)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
