"""The pipeline: source files in, knowledge base out.

    1 retrieval and curation   find the files, drop exact duplicates, recognise a print of another source
    2 conversion               every file becomes machine-readable statements (and a Python script)
    3 decomposition            statements are mapped to the quantities of the code
    4 consolidation            variants of one quantity are merged into a unified formula
    5 object generation        one small calculation object per quantity, with its evidence
    6 repository               objects, generated code blocks and the search index are written

Everything here is deterministic.  A language model is only used by the
converters that need to read an image (see ``convert/scan.py``).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import expr as X
from . import units as U
from .convert import ConversionError, convert_file, kind_of
from .distill import benchmarks as B
from .distill import reference as R
from .distill.consolidate import Consolidation, consolidate
from .distill.decompose import LOCAL, Decomposition, canonical_value, decompose
from .distill.taxonomy import Taxonomy, load as load_taxonomy
from .ir import SourceDocument, file_sha256
from .kb.objects import CalcObject, KnowledgeBase, Quantity
from .notation import symkey

KIND_LABEL = {"mathcad": "Mathcad worksheet", "excel": "Excel workbook", "pdf": "PDF print",
              "python": "Python script", "notebook": "Jupyter notebook", "word": "Word report",
              "scan": "scan"}


@dataclass
class Build:
    docs: list[SourceDocument] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    decs: list[Decomposition] = field(default_factory=list)
    consolidations: dict[str, Consolidation] = field(default_factory=dict)
    benchmarks: dict[str, list] = field(default_factory=dict)
    observed: dict = field(default_factory=dict)
    kb: KnowledgeBase | None = None
    tax: Taxonomy | None = None


# --------------------------------------------------------------------------
# stage 1 - retrieval and curation
# --------------------------------------------------------------------------
def retrieve(inbox: Path) -> tuple[list[Path], list[dict]]:
    files, skipped, seen = [], [], {}
    for p in sorted(Path(inbox).rglob("*")):
        if not p.is_file() or p.name.startswith((".", "~$")) or p.name.lower() == "readme.md":
            continue
        digest = file_sha256(p)
        if digest in seen:
            skipped.append({"file": p.name, "reason": f"identical copy of {seen[digest]}"})
            continue
        seen[digest] = p.name
        files.append(p)
    return files, skipped


def find_prints(docs: list[SourceDocument]) -> None:
    """A PDF that prints another source is not an independent source."""
    for doc in docs:
        printed = [s for s in doc.statements if s.kind == "printed" and isinstance(s.value, (int, float))]
        if len(printed) < 5 or any(s.kind == "calc" for s in doc.statements):
            continue
        for other in docs:
            if other is doc or not any(s.kind == "calc" for s in other.statements):
                continue
            table = defaultdict(list)
            for s in other.statements:
                v = s.best_value()
                if isinstance(v, (int, float)):
                    shown = U.from_canonical(v, s.unit) if (s.canonical and s.unit) else v
                    table[symkey(s.name)].append(shown)
            hits = 0
            for s in printed:
                tol = max(s.precision * 1.01, 1e-9 * abs(s.value))
                if any(abs(v - s.value) <= tol for v in table.get(symkey(s.name), [])):
                    hits += 1
            if hits >= 0.8 * len(printed):
                doc.meta["print_of"] = other.id
                break


# --------------------------------------------------------------------------
def _anonymise(text: str) -> str:
    return re.sub(r"\s*'[^']*'", "", text or "")


def build(inbox: Path, workspace: Path, kb_dir: Path, *, anonymous: bool = False, llm=None,
          vision: bool = False, log=print) -> Build:
    out = Build(tax=load_taxonomy())
    tax = out.tax
    workspace, kb_dir = Path(workspace), Path(kb_dir)

    # ---- 1 + 2: retrieve, curate, convert -----------------------------------
    files, out.skipped = retrieve(inbox)
    log(f"[1] retrieval: {len(files)} file(s) in {inbox}" + (f", {len(out.skipped)} duplicate(s) dropped" if out.skipped else ""))
    for p in files:
        if kind_of(p) is None and p.suffix.lower() not in (".xls", ".xlsb", ".doc", ".xmcd", ".mcd"):
            out.skipped.append({"file": p.name, "reason": "not a calculation format"})
            continue
        try:
            doc = convert_file(p, llm=llm, vision=vision)
        except ConversionError as exc:
            out.skipped.append({"file": p.name, "reason": str(exc)})
            log(f"    flagged and skipped: {p.name} - {exc}")
            continue
        doc.id = f"S{len(out.docs) + 1}"
        doc.label = f"{doc.id} ({KIND_LABEL.get(doc.kind, doc.kind)})" if anonymous else f"{doc.id} {doc.name}"
        out.docs.append(doc)
        s = doc.summary()
        if s["formulas"]:
            log(f"[2] {doc.label}: {s['statements']} statements, {s['formulas']} formulas, "
                f"{s['formulas_verified']} reproduce the source value" +
                (f", {s['formulas_mismatch'] + s['formulas_failed']} do not" if s["formulas_mismatch"] + s["formulas_failed"] else ""))
        else:
            log(f"[2] {doc.label}: {s['printed_values']} printed quantities")
    find_prints(out.docs)
    conv = workspace / "converted"
    conv.mkdir(parents=True, exist_ok=True)
    for doc in out.docs:
        stem = f"{doc.id}_{re.sub(r'[^A-Za-z0-9]+', '_', Path(doc.name).stem)[:40]}"
        doc.save(conv / f"{stem}.json")
        if doc.python:
            (conv / f"{stem}.py").write_text(doc.python, encoding="utf-8")

    # ---- 3: decomposition ---------------------------------------------------
    observed: dict = defaultdict(list)
    by_concept: dict = defaultdict(list)
    for doc in out.docs:
        dec = decompose(doc, tax)
        out.decs.append(dec)
        for k, v in dec.observations.items():
            observed[k] += v
        for inst in dec.instances:
            by_concept[inst.concept].append(inst)
        s = dec.summary()
        log(f"[3] {doc.label}: {s['recognised']} quantities recognised, {s['instances_with_formula']} formulas "
            f"of code quantities, {s['printed_values']} printed values, {s['not_recognised']} not recognised")
    out.observed = observed
    independent = {d.id for d in out.docs if not d.meta.get("print_of")}

    # ---- 4: consolidation ---------------------------------------------------
    for c in tax.concepts.values():
        if c.kind != "derived" or c.id not in by_concept:
            continue
        cons = consolidate(c.id, by_concept[c.id], tax, observed)
        if cons.variants:
            out.consolidations[c.id] = cons
    name = lambda s: tax.concepts[s].text if s in tax.concepts else s.lstrip(LOCAL)   # noqa: E731
    out.benchmarks = B.run(out.consolidations, out.decs, tax, observed, name)
    for cid, cons in out.consolidations.items():
        if cons.unified is not None:
            log(f"[4] {name(cid):14} {cons.status:14} {len(cons.merged)} variant(s) merged"
                + (f", {len(cons.conflicts)} not merged" if cons.conflicts else ""))

    # ---- 5: objects ---------------------------------------------------------
    kb = KnowledgeBase()
    label = {d.id: d.label for d in out.docs}
    formulas = {cid: c.unified for cid, c in out.consolidations.items() if c.unified is not None}
    typical = B.typical_values(observed)
    ref_name, _ = R.library()
    for cid, cons in out.consolidations.items():
        if cons.unified is None:
            continue
        c = tax.concepts[cid]
        merged_instances = [i for v in cons.merged for i in v.instances]
        srcs = sorted({i.doc for i in merged_instances} & independent) or sorted({i.doc for i in merged_instances})
        rows = out.benchmarks.get(cid, [])
        counts = Counter(b.status for b in rows)
        obj = CalcObject(
            id=cid, name=c.name, formula=X.to_python(cons.unified), params=X.symbols(cons.unified),
            var=c.var, symbol=c.symbol, unit=c.unit, code=tax.code, branch=tax.branch, topic=c.topic,
            topic_path=[f"{t['id']} {t['title']}" for t in tax.topic_path(c.topic)],
            clause=c.clause, eq=c.eq, check=c.check, notes=list(c.notes), neutral=dict(cons.neutral))
        # the status counts independent sources only (a print of a worksheet is not a second opinion)
        if any(v.publishable for v in cons.conflicts):
            obj.status = "disagreement"
        elif len(srcs) < 2:
            obj.status = "single source"
        else:
            obj.status = "consensus" if len(cons.merged) == 1 else "unified"
        obj.support = {"sources": len(srcs), "source_ids": srcs, "formula_instances": len(merged_instances),
                       "variants_merged": len(cons.merged),
                       "printed_values": sum(b.kind == "printed" for b in rows)}
        for v in cons.variants:
            obj.variants.append({
                "formula": X.to_python(v.formula, lambda s: s.lstrip(LOCAL)),
                "text": X.to_text(v.formula, name),
                "instances": len(v.instances),
                "sources": [label[s] for s in v.sources],
                "merged": v.merged,
                "differences": [d.describe(name) for d in v.diffs],
                **({"reason": v.reason} if v.reason else {}),
            })
        obj.benchmarks = {"total": len(rows), "agree": counts.get("agree", 0),
                          "deviation": counts.get("deviation", 0),
                          "not_comparable": counts.get("not comparable", 0), "items": []}
        for b in rows:
            item = {"source": label[b.doc], "where": _anonymise(b.loc) if anonymous else b.loc,
                    "kind": b.kind, "expected": b.expected, "got": b.got, "status": b.status}
            if b.case and (not anonymous or re.fullmatch(r"phase \d+", b.case)):
                item["case"] = b.case
            if b.detail:
                item["detail"] = b.detail
            if b.tolerance:
                item["tolerance"] = b.tolerance
            item["inputs"] = {k: v for k, v in b.inputs.items() if not k.startswith(LOCAL)}
            if b.per_width:
                item["per_width"] = True
            obj.benchmarks["items"].append(item)
        obj.reference = R.check(cid, formulas, tax)
        # ---- warnings an engineer must see before using the object ----------
        if obj.status == "single source":
            obj.warnings.append("Seen in one source only: not yet confirmed by a second, independent calculation.")
        real_conflicts = [v for v in cons.conflicts if v.publishable]
        if real_conflicts:
            obj.warnings.append(
                f"Sources disagree: {len(real_conflicts)} other formula(s) for this quantity could not be merged "
                "with the one shown. The one shown has the most support; an engineer has to decide.")
        if obj.reference.get("status") == "differs":
            obj.warnings.append(f"Differs from the independent reference ({obj.reference['library']}, "
                                f"{obj.reference['function']}) in {obj.reference['samples'] - obj.reference['agreeing_samples']} "
                                f"of {obj.reference['samples']} samples.")
        if counts.get("deviation"):
            obj.warnings.append(f"{counts['deviation']} of {len(rows)} source values are not reproduced "
                                "(see the benchmarks: a source formula that is a special case, or a disagreement).")
        obj.version = obj.fingerprint()
        kb.objects[cid] = obj

    # ---- quantities (parameters) --------------------------------------------
    needed = {p for o in kb.objects.values() for p in o.params} | {o.check for o in kb.objects.values() if o.check}
    for qid in needed:
        if qid in kb.objects or qid not in tax.concepts:
            continue
        c = tax.concepts[qid]
        kb.quantities[qid] = Quantity(
            id=qid, name=c.name, var=c.var, symbol=c.symbol, unit=c.unit, kind=c.kind, topic=c.topic,
            clause=c.clause, typical=typical.get(qid),
            range=list(c.canonical_range) if c.canonical_range else None,
            observed=len(observed.get(qid, [])))
    _examples(out, kb, tax, label, anonymous)

    # ---- 6: repository ------------------------------------------------------
    kb.meta = {"code": tax.code, "branch": tax.branch, "title": tax.title, "reference_library": ref_name,
               "units": "N, mm, MPa (N/mm²), rad"}
    kb.topics = [{"id": t["id"], "title": t["title"]} for t in tax.topics.values()]
    for doc, dec in zip(out.docs, out.decs):
        s, d = doc.summary(), dec.summary()
        kb.sources.append({
            "id": doc.id, "label": doc.label, "kind": doc.kind, "converter": doc.converter,
            "sha256": doc.sha256[:16], "statements": s["statements"], "formulas": s["formulas"],
            "formulas_verified": s["formulas_verified"], "printed_values": s["printed_values"],
            "recognised": d["recognised"], "instances": d["instances_with_formula"],
            "not_recognised": d["not_recognised"], "issues": len(doc.issues),
            **({"print_of": doc.meta["print_of"]} if doc.meta.get("print_of") else {}),
            **({"stored_results": doc.meta["stored_results"]} if doc.meta.get("stored_results") else {}),
        })
    kb.meta["skipped"] = [{"file": "(name withheld)" if anonymous else s["file"], "reason": s["reason"]}
                          for s in out.skipped]
    kb.save(kb_dir)
    from .kb.codegen import write_package
    write_package(kb, kb_dir / "python")
    out.kb = kb
    _write_report(out, workspace, label)
    log(f"[5] {len(kb.objects)} calculation objects, {len(kb.quantities)} parameters -> {kb_dir}")
    return out


# --------------------------------------------------------------------------
def _examples(out: Build, kb: KnowledgeBase, tax: Taxonomy, label: dict, anonymous: bool) -> None:
    """Real cases from the sources that the calculators can load.

    The inputs of a case are read off the source's own dependency graph: the
    statement that fed ``ρ_l`` in that source is the one that gives ``A_sl``.
    """
    ctx = {dec.doc.id: B.Context(dec, tax) for dec in out.decs}
    inst_of = {dec.doc.id: {i.stmt: i for i in dec.instances if i.kind == "formula"} for dec in out.decs}
    merged_ids = {id(i) for c in out.consolidations.values() for v in c.merged for i in v.instances}
    for cid, cons in out.consolidations.items():
        obj = kb.objects.get(cid)
        if obj is None:
            continue
        cands = [(v, i) for v in cons.merged for i in v.instances]
        cands.sort(key=lambda p: (p[1].per_width, p[1].doc, p[1].loc))
        per_doc: Counter = Counter()
        found, seen_sets = [], set()
        for v, inst in cands:
            if per_doc[inst.doc] >= 40:
                continue
            vals: dict = {}
            given: dict = {}
            ok = True

            def walk(i, depth=0):
                nonlocal ok
                for sym, a in i.args.items():
                    if sym.startswith(LOCAL) or not ok:
                        continue
                    if sym in kb.objects:
                        sub = inst_of[i.doc].get(a["stmt"])
                        if sub is not None and sub.concept == sym and id(sub) in merged_ids and depth < 12:
                            walk(sub, depth + 1)
                        elif isinstance(a["value"], (int, float)):
                            given[sym] = a["value"]      # the source gets this value some other way
                        else:
                            ok = False
                    elif isinstance(a["value"], (int, float)):
                        if sym in vals and abs(vals[sym] - a["value"]) > 1e-9 * abs(a["value"]):
                            ok = False          # one quantity, two values: not one consistent case
                        vals[sym] = a["value"]
                    else:
                        ok = False

            walk(inst)
            if not ok:
                continue
            try:
                steps, inputs = kb.plan(cid, given=tuple(given))
            except Exception:                                    # noqa: BLE001
                continue
            vals.update(given)
            neutral = {p: v for s2 in steps for p, v in kb.objects[s2].neutral.items()}
            c = ctx[inst.doc]
            st = c.by_id[inst.stmt]
            for p in inputs:
                if p in vals:
                    continue
                q = tax.concepts.get(p)
                if q is not None and q.strip and inst.per_width:
                    vals[p] = 1.0
                elif p in neutral:
                    r = c.find(p, tax.concepts[cid].topic, st, same_group_only=True)
                    vals[p] = canonical_value(r, q) if r is not None else neutral[p]
                elif q is not None and q.kind == "coefficient" and kb.quantities.get(p) and kb.quantities[p].typical is not None:
                    r = c.find(p, tax.concepts[cid].topic, st, same_group_only=True)
                    vals[p] = canonical_value(r, q) if r is not None else kb.quantities[p].typical
            if len(vals) < len(inputs) or not all(isinstance(vals.get(p), (int, float)) for p in inputs):
                continue
            vals = {p: vals[p] for p in inputs}
            expected = inst.value
            if inst.per_width:
                # show a per-metre calculation as a 1 m strip, if the logic scales with the width
                scaled = {p: (x * 1000.0 if (tax.concepts[p].strip or tax.concepts[p].dims == (0, 2, 0, 0)) else x)
                          for p, x in vals.items()}
                try:
                    r1, _ = kb.evaluate(cid, vals, given=tuple(given))
                    r2, _ = kb.evaluate(cid, scaled, given=tuple(given))
                except Exception:                                # noqa: BLE001
                    continue
                scales = isinstance(r1, float) and abs(r2 - 1000.0 * r1) <= 1e-9 * abs(r2)
                same = isinstance(r1, float) and abs(r2 - r1) <= 1e-9 * abs(r2)
                if not (scales or same):
                    continue
                vals = scaled
                if scales and isinstance(expected, (int, float)):
                    expected = expected * 1000.0
            try:
                got, _ = kb.evaluate(cid, vals, given=tuple(given))
            except Exception:                                    # noqa: BLE001
                continue
            key = tuple(round(x, 9) for x in vals.values())
            if key in seen_sets:
                continue
            seen_sets.add(key)
            per_doc[inst.doc] += 1
            where = _anonymise(inst.loc) if anonymous else inst.loc
            case = inst.case if (inst.case and (not anonymous or re.fullmatch(r"phase \d+", inst.case))) else ""
            match = isinstance(got, (int, float)) and isinstance(expected, (int, float)) \
                and abs(got - expected) <= 1e-6 * abs(expected)
            found.append({
                "label": f"{label[inst.doc]} - {where}" + (f" - {case}" if case else "")
                         + (" (1 m strip)" if inst.per_width else ""),
                "doc": inst.doc, "inputs": vals, "expected": expected, "result": got, "matches_source": match,
                **({"given": sorted(given)} if given else {}),
            })
        # a few cases per source: those the object reproduces first, then one it does not
        picked = []
        for doc_id in sorted({f["doc"] for f in found}):
            mine = [f for f in found if f["doc"] == doc_id]
            good = [f for f in mine if f["matches_source"]][:3]
            bad = [f for f in mine if not f["matches_source"]][:1]
            picked += good + bad
        for f in picked[:8]:
            f.pop("doc")
            obj.examples.append(f)


def _write_report(out: Build, workspace: Path, label: dict) -> None:
    """A plain-text account of the run (for the engineer reviewing the distillation)."""
    tax, kb = out.tax, out.kb
    name = kb.name
    L = ["# Distillation report", ""]
    L += ["## Sources", ""]
    for s in kb.sources:
        line = f"- **{s['label']}** - {s['converter']}: {s['statements']} statements"
        if s["formulas"]:
            line += f", {s['formulas_verified']}/{s['formulas']} formulas reproduce the source value"
        if s.get("stored_results"):
            line += f", {s['stored_results']['agree']}/{s['stored_results']['compared']} results stored by Mathcad reproduced"
        if s["printed_values"]:
            line += f", {s['printed_values']} printed quantities"
        if s.get("print_of"):
            line += f" - recognised as a print of {s['print_of']} (benchmark only, not an independent source)"
        L.append(line)
        L.append(f"  - {s['recognised']} quantities recognised; {s['instances']} formulas of code quantities; "
                 f"{s['not_recognised']} calculated values not recognised (project-specific or outside the taxonomy)")
    for s in out.skipped:
        L.append(f"- skipped: {s['file']} - {s['reason']}")
    L += ["", "## Calculation objects", ""]
    for o in kb.objects.values():
        L.append(f"### {o.text} - {o.name}")
        L.append(f"{o.reference_text} - {' > '.join(o.topic_path)}")
        L.append("")
        L.append(f"    {o.text} = {X.to_text(o.tree, name)}")
        L.append("")
        sup = o.support
        L.append(f"- status: **{o.status}** - {sup['formula_instances']} formula instance(s) in {sup['sources']} "
                 f"independent source(s), {sup['variants_merged']} variant(s) merged")
        for v in o.variants:
            tag = "merged" if v["merged"] else "NOT merged"
            L.append(f"  - {tag}: `{v['text']}` - {v['instances']} instance(s) in {', '.join(v['sources'])}")
            for d in v["differences"]:
                L.append(f"    - {d}")
            if v.get("reason"):
                L.append(f"    - {v['reason']}")
        b = o.benchmarks
        L.append(f"- benchmarks: {b['agree']} of {b['total']} source values reproduced"
                 + (f", {b['deviation']} deviation(s)" if b["deviation"] else "")
                 + (f", {b['not_comparable']} not comparable" if b["not_comparable"] else ""))
        shown = 0
        for it in b["items"]:
            if it["status"] == "deviation" and shown < 4:
                k, unit = (1000.0, o.unit + "/m") if it.get("per_width") else (1.0, o.unit)
                L.append(f"  - deviation at {it['source']} {it['where']}: source "
                         f"{U.fmt(kb.to_display(o.id, it['expected']) * k)}, unified "
                         f"{U.fmt(kb.to_display(o.id, it['got']) * k)} {unit} - {it.get('detail', '')}")
                shown += 1
        if o.reference:
            r = o.reference
            L.append(f"- reference: {r['status']} with {r['library']} `{r['function']}` "
                     f"({r['agreeing_samples']}/{r['samples']} samples, max. relative difference {r['max_relative_difference']})")
        for w in o.warnings:
            L.append(f"- warning: {w}")
        L.append("")
    L += ["## Not distilled", ""]
    for doc, dec in zip(out.docs, out.decs):
        names = Counter(s.name for s in dec.unmapped)
        if names:
            L.append(f"- {label[doc.id]}: " + ", ".join(f"{n} (x{k})" if k > 1 else n for n, k in names.most_common(25))
                     + (" ..." if len(names) > 25 else ""))
        glue = Counter(dec.producer[s.id][0].text for s in dec.glue)
        if glue:
            L.append(f"  - project-specific formulas for input quantities: " + ", ".join(f"{n} (x{k})" for n, k in glue.most_common()))
    proj = [c for c in out.consolidations.values() if c.unified is None]
    if proj:
        L.append("- quantities found only with project-specific formulas: " + ", ".join(name(c.concept) for c in proj))
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "distillation_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (workspace / "instances.json").write_text(json.dumps(
        [i.to_json() for dec in out.decs for i in dec.instances], indent=1, ensure_ascii=False, default=str),
        encoding="utf-8")
