"""The pipeline: source files in, knowledge base out.

    1 retrieval and curation   find the files, drop exact duplicates, recognise a print of another source
    2 conversion               every file becomes machine-readable statements (and a Python script)
    3 decomposition            statements are mapped to the quantities of the code
    4 consolidation            each source formula is compared with the code expression (applied as
                               written, simplified, different); without a code expression the sources
                               are merged among themselves
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
from .distill.baseline import classify, reassign
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

    # ---- 4: compare with the code; merge where there is no code expression --------
    moved = reassign(by_concept, tax, observed)
    if moved:
        log(f"[4] {moved} formula(s) re-read as another quantity whose code expression they match")
    for c in tax.concepts.values():
        if c.kind != "derived":
            continue
        insts = by_concept.get(c.id, [])
        if c.formula:
            cons = classify(c, insts, tax, observed)
        elif insts:
            cons = consolidate(c.id, insts, tax, observed)
            if not cons.variants:
                continue
        else:
            continue
        out.consolidations[c.id] = cons
    name = lambda s: tax.concepts[s].text if s in tax.concepts else s.lstrip(LOCAL)   # noqa: E731
    out.benchmarks = B.run(out.consolidations, out.decs, tax, observed, name)
    for cid, cons in out.consolidations.items():
        if not cons.variants:
            continue
        rel = Counter(v.relation or ("merged" if v.merged else "not merged") for v in cons.variants)
        log(f"[4] {name(cid):14} " + ", ".join(f"{n} {k}" for k, n in rel.items()))

    # ---- 5: objects ---------------------------------------------------------
    kb = KnowledgeBase()
    label = {d.id: d.label for d in out.docs}
    formulas = {c.id: c.tree for c in tax.concepts.values() if c.formula}
    formulas.update({cid: c.unified for cid, c in out.consolidations.items() if c.unified is not None})
    for cid, cons in out.consolidations.items():
        if cons.unified is None:
            continue
        kb.objects[cid] = _object(cid, cons, out.benchmarks.get(cid, []), tax, formulas, observed,
                                  label, independent, anonymous)

    # ---- quantities (parameters) --------------------------------------------
    needed: set[str] = set()
    for o in kb.objects.values():
        needed |= set(o.params) | set(o.fixed)
        if o.check:
            needed.add(o.check)
        for chk in o.checks:
            needed |= set(X.symbols(X.parse(chk["when"])))
    for qid in sorted(needed):
        if qid in kb.objects or qid not in tax.concepts:
            continue
        c = tax.concepts[qid]
        seen = Counter(float(f"{v:.6g}") for v in observed.get(qid, []) if isinstance(v, (int, float)))
        kb.quantities[qid] = Quantity(
            id=qid, name=c.name, var=c.var, symbol=c.symbol, unit=c.unit,
            kind="coefficient" if c.kind == "coefficient" else "input", code=c.code, topic=c.topic,
            clause=c.clause, value=c.canonical_value, example=c.canonical_example, ndp=c.ndp,
            choices=[{"value": ch["value"] * c.factor, "label": ch.get("label", "")} for ch in c.choices],
            range=list(c.canonical_range) if c.canonical_range else None,
            seen=[[v, n] for v, n in seen.most_common(8)],
            background=[_background(b, tax) for b in c.background])

    # ---- 6: repository ------------------------------------------------------
    ref_name, _ = R.library()
    kb.meta = {"reference_library": ref_name, "units": "N, mm, MPa (N/mm²), rad",
               "built_from": f"{len(out.docs)} source file(s)"}
    kb.references = dict(tax.references)
    for code in tax.codes:
        topics = [{"id": tid, "title": t["title"]} for (cd, tid), t in tax.topics.items() if cd == code["code"]]
        kb.codes.append(dict(code, topics=topics, fixed=tax.fixed_for(code["code"])))
    for doc, dec in zip(out.docs, out.decs):
        s, d = doc.summary(), dec.summary()
        kb.sources.append({
            "id": doc.id, "label": doc.label, "kind": doc.kind, "converter": doc.converter,
            **({} if anonymous else {"sha256": doc.sha256[:16]}),
            "statements": s["statements"], "formulas": s["formulas"],
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
    lv = Counter(o.confidence.get("level") for o in kb.objects.values())
    log(f"[5] {len(kb.objects)} calculation objects ({lv.get('high', 0)} checked, {lv.get('medium', 0)} not yet "
        f"checked, {lv.get('low', 0)} need review), {len(kb.quantities)} parameters -> {kb_dir}")
    return out


# --------------------------------------------------------------------------
def _background(b: dict, tax: Taxonomy) -> dict:
    """A background note with its references resolved to full citations."""
    refs = []
    for r in b.get("refs", []):
        rid = max((k for k in tax.references if r == k or r.startswith(k + ":")), key=len, default="")
        refs.append({"id": rid or r, "at": r[len(rid) + 1:] if rid else "", "text": tax.references.get(rid, "")})
    return {"kind": b.get("kind", "guidance"), "text": b["text"], "refs": refs}


def _object(cid, cons, rows, tax, formulas, observed, label, independent, anonymous) -> CalcObject:
    from .distill.baseline import explain
    c = tax.concepts[cid]
    name = lambda s: tax.concepts[s].text if s in tax.concepts else s.lstrip(LOCAL)   # noqa: E731
    path = [f"{t['id']} {t['title']}" for t in tax.topic_path(c.topic, c.code)]
    deps = set(tax.dependencies(cid))
    fixed = {k: v for k, v in tax.fixed_for(c.code).items() if k in deps}
    obj = CalcObject(
        id=cid, name=c.name, formula=X.to_python(cons.unified), params=X.symbols(cons.unified),
        var=c.var, symbol=c.symbol, unit=c.unit, code=c.code or "", topic=c.topic, topic_path=path,
        clause=c.clause, eq=c.eq, basis=c.basis if cons.baseline else "sources", ndp=c.ndp, sense=c.sense,
        check=c.check, refs=[r for r in c.refs if r.get("how") != "defined here"], fixed=fixed,
        alternatives=list(c.alternatives), checks=list(c.checks),
        background=[_background(b, tax) for b in c.background])

    # ---- how the sources applied it ------------------------------------------------
    by_inst = {(b.doc, b.loc): b for b in rows if b.kind == "formula"}
    variants, practice = [], []
    n_inst = sum(len(v.instances) for v in cons.variants)
    srcs = sorted({i.doc for v in cons.variants for i in v.instances} & independent)
    for v in cons.variants:
        rel = v.relation or ("merged" if v.merged else "kept apart")
        benches = [by_inst.get((i.doc, i.loc)) for i in v.instances]
        benches = [b for b in benches if b is not None]
        first_env = next((b.inputs for b in benches if b.inputs), {})
        diffs = []
        for d in v.diffs:
            if d.kind == "alias":
                continue
            diffs.append(explain(d, tax, first_env, any(i.per_width for i in v.instances), name))
        agree = sum(b.status == "agree" for b in benches)
        dev = [b for b in benches if b.status == "deviation"]
        item = {"formula": X.to_python(v.formula, lambda s: s.lstrip(LOCAL)), "text": X.to_text(v.formula, name),
                "relation": rel, "instances": len(v.instances), "sources": [label[s] for s in v.sources],
                "merged": v.merged, "differences": diffs, "reproduced": agree, "compared": len(benches)}
        if v.reason:
            item["reason"] = v.reason
        if v.alternative:
            item["alternative"] = v.alternative.get("when", "")
        if dev:
            item["deviations"] = Counter(b.detail for b in dev).most_common(3)
        variants.append(item)
        # one practice sentence per variant
        where = f"{len(v.instances)} formula(s) in {', '.join(label[s].split(' ')[0] for s in v.sources)}"
        if rel == "as code":
            practice.append(f"{where}: as in the code.")
        elif rel == "alternative":
            practice.append(f"{where}: the permitted alternative {X.to_text(v.formula, name)} "
                            f"({v.alternative.get('when', '')}).")
        elif rel == "simplified":
            text = "; ".join(diffs) if diffs else "a special case"
            tail = f" The result differs in {len(dev)} of {len(benches)} cases: {dev[0].detail}." if dev else ""
            practice.append(f"{where}: simplified - {text}.{tail}")
        elif rel == "differs":
            practice.append(f"{where}: {X.to_text(v.formula, name)} - not the code expression; to be reviewed.")
        elif rel == "project-specific":
            practice.append(f"{where}: written with project-specific quantities ({v.reason.split(': ')[-1]}).")
        else:
            practice.append(f"{where}: {rel}.")
    # coefficient values the sources used, against the recommended value
    values_seen = {}
    for q in sorted(deps) if cons.variants else []:
        qc = tax.concepts.get(q)
        if qc is None or qc.kind != "coefficient" or not observed.get(q):
            continue
        seen = Counter(float(f"{x:.6g}") for x in observed[q] if isinstance(x, (int, float)))
        values_seen[q] = {"recommended": qc.canonical_value, "seen": [[v, n] for v, n in seen.most_common(6)]}
        other = [(v, n) for v, n in seen.items() if qc.canonical_value is None or abs(v - qc.canonical_value) > 1e-9]
        if other:
            practice.append(f"{qc.text}: the sources use " + ", ".join(
                f"{X._short(U.from_canonical(v, qc.unit))} ({n}×)" for v, n in sorted(other, key=lambda t: -t[1]))
                + (f" against the recommended {X._short(U.from_canonical(qc.canonical_value, qc.unit))}"
                   if qc.canonical_value is not None else "") + ".")
    obj.evidence = {"sources": len(srcs), "source_ids": srcs, "formula_instances": n_inst,
                    "printed_values": sum(b.kind == "printed" for b in rows),
                    "variants": variants, "practice": practice, "values_seen": values_seen}

    # ---- benchmarks, reference, confidence -------------------------------------------------
    counts = Counter(b.status for b in rows)
    obj.benchmarks = {"total": len(rows), "agree": counts.get("agree", 0), "deviation": counts.get("deviation", 0),
                      "not_comparable": counts.get("not comparable", 0), "items": []}
    for b in rows:
        it = {"source": label[b.doc], "where": _anonymise(b.loc) if anonymous else b.loc, "kind": b.kind,
              "expected": b.expected, "got": b.got, "status": b.status}
        if b.case and (not anonymous or re.fullmatch(r"(phase|case|stage|lc)\s*\d+", b.case, re.I)):
            it["case"] = b.case
        if b.detail:
            it["detail"] = b.detail
        if b.tolerance:
            it["tolerance"] = b.tolerance
        if b.per_width:
            it["per_width"] = True
        it["inputs"] = {k: v for k, v in b.inputs.items() if not k.startswith(LOCAL)}
        obj.benchmarks["items"].append(it)
    obj.reference = R.check(cid, formulas, tax)
    obj.confidence = _confidence(obj, cons, rows, tax)
    obj.version = obj.fingerprint()
    return obj


def _confidence(obj: CalcObject, cons, rows, tax) -> dict:
    """How much the object can be trusted, and why."""
    reasons = []
    ref = obj.reference.get("status")
    merged_agree = sum(1 for b in rows if b.status == "agree")
    n_src = obj.evidence.get("sources", 0)
    if cons.baseline:
        what = {"code": "the code's expression", "mechanics": "standard section analysis used with the code",
                "definition": "a definition"}.get(obj.basis, "the code baseline")
        reasons.append(f"Logic: {what} ({obj.reference_text}).")
        if ref == "agrees":
            reasons.append(f"Agrees with {obj.reference['library']} over {obj.reference['samples']} samples.")
        elif ref == "differs":
            reasons.append(f"Differs from {obj.reference['library']} in some samples.")
        else:
            reasons.append("No independent implementation available to compare with.")
        if merged_agree:
            reasons.append(f"Reproduces {merged_agree} value(s) from {n_src} independent source(s).")
        elif rows:
            reasons.append("Not reproduced by any source value yet.")
        else:
            reasons.append("Not yet seen in any source calculation.")
        if ref == "differs":
            level = "low"
        elif ref == "agrees" or merged_agree:
            level = "high"
        else:
            level = "medium"
    else:
        reasons.append("Logic distilled from the sources only: the registry has no code expression for it.")
        disagree = any(v.publishable and not v.merged for v in cons.variants)
        if disagree:
            reasons.append("The sources disagree.")
        level = "medium" if n_src >= 2 and not disagree else "low"
        reasons.append(f"Seen in {n_src} independent source(s).")
    if any(v.relation == "differs" for v in cons.variants):
        reasons.append("Some source formulas differ from the code: see how the sources applied it.")
    label = {"high": "checked", "medium": "not yet checked", "low": "review needed"}[level]
    return {"level": level, "label": label, "reasons": reasons}


def _write_report(out: Build, workspace: Path, label: dict) -> None:
    """A plain-text account of the run (for the engineer reviewing the distillation)."""
    kb = out.kb
    L = ["# Distillation report", "", "## Sources", ""]
    for s in kb.sources:
        line = f"- **{s['label']}** - {s['converter']}: {s['statements']} statements"
        if s["formulas"]:
            line += f", {s['formulas_verified']}/{s['formulas']} formulas reproduce the source value"
        if s.get("stored_results"):
            line += f", {s['stored_results']['agree']}/{s['stored_results']['compared']} results stored by Mathcad reproduced"
        if s["printed_values"]:
            line += f", {s['printed_values']} printed quantities"
        if s.get("print_of"):
            line += f" - a print of {s['print_of']} (benchmark only, not an independent source)"
        L.append(line)
        L.append(f"  - {s['recognised']} quantities recognised; {s['instances']} formulas of code quantities; "
                 f"{s['not_recognised']} calculated values not recognised")
    for s in out.skipped:
        L.append(f"- skipped: {s['file']} - {s['reason']}")
    L += ["", "## How the sources applied the code", ""]
    for o in kb.objects.values():
        ev = o.evidence
        if not ev.get("variants") and not o.benchmarks.get("total"):
            continue
        L.append(f"### {o.text} - {o.name} ({o.reference_text})")
        L.append(f"    {o.text} = {X.to_text(o.tree, kb.name)}")
        L.append(f"- confidence: **{o.confidence['label']}** - " + " ".join(o.confidence["reasons"]))
        for p in ev.get("practice", []):
            L.append(f"- {p}")
        b = o.benchmarks
        L.append(f"- benchmarks: {b['agree']} of {b['total']} source values reproduced"
                 + (f", {b['deviation']} differ" if b["deviation"] else "")
                 + (f", {b['not_comparable']} not comparable" if b["not_comparable"] else ""))
        for it in [i for i in b["items"] if i["status"] == "deviation"][:4]:
            k, unit = (1000.0, o.unit + "/m") if it.get("per_width") else (1.0, o.unit)
            L.append(f"  - {it['source']} {it['where']}: source {U.fmt(kb.to_display(o.id, it['expected']) * k)}, "
                     f"code {U.fmt(kb.to_display(o.id, it['got']) * k)} {unit} - {it.get('detail', '')}")
        L.append("")
    L += ["## Objects from the code not yet seen in any source", ""]
    L.append(", ".join(f"{o.text} ({o.reference_text})" for o in kb.objects.values()
                       if not o.evidence.get("variants") and not o.benchmarks.get("total")) or "none")
    L += ["", "## Not distilled", ""]
    for doc, dec in zip(out.docs, out.decs):
        names = Counter(s.name for s in dec.unmapped)
        if names:
            L.append(f"- {label[doc.id]}: " + ", ".join(f"{n} (x{k})" if k > 1 else n for n, k in names.most_common(25))
                     + (" ..." if len(names) > 25 else ""))
        glue = Counter(dec.producer[s.id][0].text for s in dec.glue)
        if glue:
            L.append("  - project-specific formulas for input quantities: " + ", ".join(f"{n} (x{k})" for n, k in glue.most_common()))
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "distillation_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (workspace / "instances.json").write_text(json.dumps(
        [i.to_json() for dec in out.decs for i in dec.instances], indent=1, ensure_ascii=False, default=str),
        encoding="utf-8")
