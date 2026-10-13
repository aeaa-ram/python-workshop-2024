"""The stages of the agentic ingestion workflow.

Each stage reads/updates the CaseFile and journals what it did:

  intake      — atomise the source into fragments (math, text, images)
  gatekeep    — knowledge-base gate: is this already a tool? which
                formulas are library atoms? revise / new tool / abort
  decompose   — dependency graph; find noise, repetition, orphans
  research    — code/standard identification per fragment (citations,
                atom library, LLM knowledge when configured)
  clarify     — ask the human INLINE about everything ambiguous:
                keep/discard, governing load case, missing values,
                final governing result, sketches & their placement
  reconstruct — rebuild a clean, compact, dependency-ordered tool
  verify      — recompute; compare against source values; units review
  reflect     — per-value self-review checklist, then the master reviewer
                loop (dimensions, scale, one-to-one vs the original, AI
                visual review) — verified corrections are written back
  deliver     — write the repository tool + reports + audit trail

The workflow (workflow.py) loops decompose→verify until convergence.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from src.ingestion.agent.casefile import CaseFile, Decision, Fragment
from src.ingestion.agent.interaction import Question
from src.models.calculation import CalcSheet, CalcSheetError, ParsedTool, ParsedVariable

_CLAUSE_RE = re.compile(
    r"(EN\s?\d{3,4}(?:-\d+){0,2}(?::\d{4})?)|(§\s?[\d.]+)|(Eq\.?\s?\(?[\d.]+\)?)",
    re.IGNORECASE)


# ================================================================== #
# INTAKE
# ================================================================== #
def stage_intake(case: CaseFile, ctx) -> None:
    from src.ingestion.base import get_parser

    path = Path(case.source_path)
    parsed: ParsedTool = get_parser(path).parse(path)
    case.title = parsed.title
    case.reference = parsed.reference
    case.description = parsed.description
    ctx.unit_aware = parsed.unit_aware
    ctx.parser_interpreter = parsed.interpreter or "parser"

    for v in parsed.variables:
        case.add(Fragment(
            fid=case.next_fid("F"), kind=v.role, name=v.name,
            expression=v.expression, value=v.value, unit=v.unit,
            description=v.description, source_ref=v.source_cell))
    for chk in parsed.checks:
        case.add(Fragment(fid=case.next_fid("C"), kind="check",
                          expression=chk))

    # clarifications raised by the parser become evidence / unresolved frags
    for c in parsed.clarifications:
        frag = case.frag(c.location)
        if frag is not None:
            frag.evidence.append(f"{c.issue}: {c.question}")
            if c.issue == "multi-value-input":
                frag.evidence.append(f"options: {c.options}")
        else:
            case.add(Fragment(
                fid=case.next_fid("U"), kind="derived", name=c.location,
                description=c.question, status="unresolved",
                evidence=[f"{c.issue}: {c.context}"]))
    case.log("intake", f"{len(case.fragments)} fragments from "
                       f"{path.name} via {ctx.parser_interpreter}")

    if path.suffix.lower() == ".mcdx":
        _intake_mcdx_images(case, path)


def _intake_mcdx_images(case: CaseFile, path: Path) -> None:
    """Pull embedded sketches; header-only images are flagged as likely
    logos (noise candidates). Mathcad often stores BMPs with a .png name
    (and a broken alpha channel that renders black) — converted to real
    PNG here so the report shows the drawing."""
    import base64

    try:
        with zipfile.ZipFile(path) as zf:
            header_rels = ""
            try:
                header_rels = zf.read("mathcad/_rels/header.xml.rels").decode(
                    "utf-8", "replace")
            except KeyError:
                pass
            for name in zf.namelist():
                if not name.startswith("mathcad/media/"):
                    continue
                data = zf.read(name)
                base = Path(name).name
                if data[:2] == b"BM":
                    png = _bmp_to_png(data)
                    if png is not None:
                        data = png
                        case.log("intake", f"image {base}: BMP-in-.png "
                                           "container converted to PNG")
                frag = case.add(Fragment(
                    fid=case.next_fid("I"), kind="image", name=base,
                    image_b64=base64.b64encode(data).decode("ascii"),
                    source_ref=name))
                if base in header_rels:
                    frag.evidence.append(
                        "referenced from the page header — likely a logo")
                    frag.status = "discarded"
                    case.log("intake", f"image {base}: header logo, discarded")
                else:
                    case.log("intake",
                             f"image {base} ({len(data)//1024} KB) extracted")
    except zipfile.BadZipFile:
        pass


def _bmp_to_png(data: bytes):
    """Decode an uncompressed 24/32-bit BMP and re-encode as PNG, forcing
    the alpha channel opaque (Mathcad writes alpha=0 everywhere, which
    browsers render as an all-black/blank image)."""
    import io
    import struct

    try:
        import numpy as np
        from matplotlib.image import imsave

        offset = struct.unpack_from("<I", data, 10)[0]
        width = struct.unpack_from("<i", data, 18)[0]
        height = struct.unpack_from("<i", data, 22)[0]
        bpp = struct.unpack_from("<H", data, 28)[0]
        flip = height > 0
        height = abs(height)
        if bpp not in (24, 32) or width <= 0 or height <= 0:
            return None
        bytes_pp = bpp // 8
        row_size = (width * bytes_pp + 3) & ~3   # rows pad to 4 bytes
        raw = np.frombuffer(data, dtype=np.uint8,
                            count=row_size * height, offset=offset)
        rows = raw.reshape(height, row_size)[:, : width * bytes_pp]
        img = rows.reshape(height, width, bytes_pp)
        if flip:
            img = img[::-1]
        rgb = img[:, :, 2::-1]                   # BGR(A) -> RGB, drop alpha
        buf = io.BytesIO()
        imsave(buf, rgb, format="png")
        return buf.getvalue()
    except Exception:
        return None


# ================================================================== #
# GATEKEEP — the central knowledge base decides what is new
# ================================================================== #
def stage_gatekeep(case: CaseFile, ctx) -> None:
    from src.ingestion.manifest import next_revision
    from src.knowledge_graph.gatekeeper import check_submission
    from src.knowledge_graph.indexer import ToolRecord
    from src.knowledge_graph.reuse import analyze_expressions

    repo = Path(ctx.repo_dir)
    if (repo / ctx.slug / "manifest.json").exists():
        ctx.revision = next_revision(repo / ctx.slug)
        case.log("gatekeep", f"'{ctx.slug}' already exists — this run "
                             f"becomes revision {ctx.revision}")
    record = ToolRecord(
        slug=ctx.slug, title=case.title, description=case.description,
        reference=case.reference,
        variables=[f.name for f in case.kept() if f.name],
        formulas=[f.expression for f in case.kept("derived") if f.expression],
        checks=[f.expression for f in case.kept("check")])
    matches = check_submission(record, repo)
    ctx.gatekeeper = matches
    case.gatekeeper = [{"slug": m.slug, "title": m.title, "score": m.score,
                        "verdict": m.verdict} for m in matches]

    findings = analyze_expressions(
        [(f.name, f.expression) for f in case.kept("derived") if f.expression],
        repo, exclude_slug=ctx.slug)
    ctx.reuse = findings
    case.reuse = [{"name": f.name, "status": f.status, "match": f.match_id}
                  for f in findings]
    atoms = [f for f in findings if f.status == "matches_atom"]
    shared = [f for f in findings if f.status == "matches_tool"]
    case.log("gatekeep", f"{len(matches)} similar tool(s); formulas: "
             f"{len(atoms)} library atom(s), {len(shared)} shared with other "
             f"tools, {len(findings) - len(atoms) - len(shared)} new")

    if not matches:
        return
    top = matches[0]
    options = [f"revise {top.slug}", "new tool", "abort"]
    question = Question(
        qid="gatekeeper", stage="gatekeep",
        prompt=(f"The knowledge base already holds "
                + "; ".join(f"'{m.title}' [{m.slug}] ({m.verdict}, "
                            f"{m.score:.2f})" for m in matches[:3])
                + ". Make this a new revision of the closest one, keep it "
                  "as a separate new tool, or abort?"),
        options=options,
        default=options[0] if top.verdict == "duplicate" else "new tool",
        context="duplicate detection against every stored tool",
        rationale="one source of truth: a duplicate should revise, not fork")
    answer, by = ctx.interaction.ask(question)
    case.decisions.append(Decision(
        qid=question.qid, stage=question.stage, prompt=question.prompt,
        options=options, answer=answer, answered_by=by,
        context=question.context))
    if answer.startswith("abort"):
        ctx.aborted = True
        case.log("gatekeep", "aborted by engineer — nothing will be written")
    elif answer.startswith("revise"):
        ctx.slug = top.slug
        ctx.revision = next_revision(repo / top.slug)
        case.log("gatekeep", f"will be written as revision {ctx.revision} "
                             f"of '{top.slug}'")
    else:
        case.log("gatekeep", "kept as a separate new tool")


# ================================================================== #
# DECOMPOSE
# ================================================================== #
def stage_decompose(case: CaseFile, ctx) -> None:
    from src.knowledge_graph.fingerprint import fingerprint_if_matchable

    kept = case.kept()
    used: set[str] = set()
    for f in kept:
        if f.kind in ("derived", "check"):
            used |= f.depends_on()

    # unused inputs -> noise candidates (asked about in clarify)
    ctx.noise_candidates = [
        f for f in kept
        if f.kind == "input" and f.name and f.name not in used
        and "noise?" not in f.evidence]
    for f in ctx.noise_candidates:
        f.evidence.append("noise?")

    # repetitive structure detection
    seen: dict[str, str] = {}
    for f in kept:
        if f.kind != "derived" or not f.expression:
            continue
        fp = fingerprint_if_matchable(f.expression)
        if fp is None:
            continue
        if fp in seen and not f.repetitive_of:
            f.repetitive_of = seen[fp]
            case.log("decompose",
                     f"'{f.name}' repeats the structure of '{seen[fp]}'")
        else:
            seen.setdefault(fp, f.name)

    orphans = case.dependency_errors()
    case.log("decompose", f"{len(kept)} kept | "
             f"{len(ctx.noise_candidates)} unused-input candidates | "
             f"{len(orphans)} unresolved dependencies")


# ================================================================== #
# RESEARCH
# ================================================================== #
def stage_research(case: CaseFile, ctx) -> None:
    from src.knowledge_graph.fingerprint import fingerprint_if_matchable
    from src.library import all_atoms

    atom_fp = {}
    for atom in all_atoms():
        fp = fingerprint_if_matchable(atom.expression)
        if fp:
            atom_fp[fp] = atom

    cited = matched = 0
    for f in case.kept("derived"):
        if f.clause:
            continue
        # 1) explicit citation in the fragment's own narrative
        m = _CLAUSE_RE.search(f.description or "")
        if m:
            f.clause = m.group(0)
            f.clause_confidence = "cited"
            cited += 1
            continue
        # 2) structural match against the atom library (clause provenance)
        fp = fingerprint_if_matchable(f.expression) if f.expression else None
        if fp and fp in atom_fp:
            atom = atom_fp[fp]
            f.atom_id = atom.atom_id
            f.clause = atom.clause
            f.clause_confidence = "atom"
            if not f.description:
                f.description = atom.description
            matched += 1
    # 3) document-level reference as fallback context
    if case.reference:
        for f in case.kept("derived"):
            if not f.clause:
                f.clause = case.reference
                f.clause_confidence = "doc"
    # 4) AI research (once per run, when a model is configured)
    if ctx.llm is not None and ctx.llm.available():
        if not getattr(ctx, "ai_research_done", False):
            _ai_research(case, ctx)
            ctx.ai_research_done = True
    else:
        case.log("research", "AI research unavailable — deterministic "
                             "knowledge base only (citations + atom library)")
    case.log("research", f"clauses: {cited} cited in source, "
             f"{matched} matched to library atoms")


_RESEARCH_SYSTEM = """\
You are a structural engineer researching a legacy calculation before it
is rebuilt as a standard company tool. For every step, name the design
code clause it implements (standard, clause and equation number, e.g.
"EN 1994-1-1 6.6.3.1 (6.18)"), how sure you are, and in "note" any
validity limit or pitfall that applies (one sentence, or empty). Then list
steps the code requires for this verification that the calculation does
not contain. Never invent a clause: when you do not know, say so with
confidence "low"."""


def _ai_research(case: CaseFile, ctx) -> None:
    from src.llm import LLMError, schemas

    steps = [f for f in case.kept("derived") if f.name]
    lines = [f"- {f.name} = {f.expression} [{f.unit or '-'}]"
             f"{' — ' + f.description if f.description else ''}"
             f"{' (current: ' + f.clause + ')' if f.clause else ''}"
             for f in steps]
    inputs = [f"- {f.name} = {f.value} {f.unit}".rstrip()
              for f in case.kept("input") if f.name]
    user = (f"Tool: {case.title}\nDocument reference: {case.reference or '-'}"
            f"\nPurpose: {case.description or '-'}\n\nInputs:\n"
            + "\n".join(inputs) + "\n\nSteps:\n" + "\n".join(lines)
            + "\n\nChecks:\n" + "\n".join(
                f"- {c.expression}" for c in case.kept("check")))
    try:
        data = ctx.llm.complete_json(_RESEARCH_SYSTEM, user,
                                     schema=schemas.RESEARCH, task="research")
    except LLMError as exc:
        case.log("research", f"AI research failed ({exc}); deterministic "
                             "knowledge only")
        return
    by_name = {f.name: f for f in steps}
    updated = 0
    for r in data.get("fragments", []):
        f = by_name.get(r.get("name", ""))
        if f is None:
            continue
        conf = r.get("confidence", "low")
        clause = (r.get("clause") or "").strip()
        if r.get("note"):
            f.evidence.append(f"AI note: {r['note']}")
        if not clause or conf == "low":
            continue
        if f.clause_confidence in ("", "doc"):
            f.clause, f.clause_confidence = clause, f"ai-{conf}"
            updated += 1
        elif clause not in f.clause:
            f.evidence.append(f"AI suggests {clause} ({conf}); kept "
                              f"{f.clause} [{f.clause_confidence}]")
    ctx.missing_steps = [f"{m['description']} ({m['clause']})"
                         for m in data.get("missing_steps", [])]
    if data.get("standard") and not case.reference:
        case.reference = data["standard"]
    case.log("research", f"AI research: {updated} clause(s) assigned, "
             f"{len(ctx.missing_steps)} possibly missing step(s) noted")


# ================================================================== #
# CLARIFY — inline questions, applied immediately
# ================================================================== #
def stage_clarify(case: CaseFile, ctx) -> None:
    asked_before = {d.qid for d in case.decisions}

    def ask(q: Question, apply):
        if q.qid in asked_before:
            return
        answer, by = ctx.interaction.ask(q)
        case.decisions.append(Decision(
            qid=q.qid, stage=q.stage, prompt=q.prompt, options=q.options,
            answer=answer, answered_by=by, context=q.context))
        apply(answer)
        case.log("clarify", f"{q.qid}: {answer} ({by})")

    # ---- multi-value inputs: governing case ----
    for f in case.kept("input"):
        opts_ev = [e for e in f.evidence if e.startswith("options:")]
        if opts_ev:
            options = re.findall(r"[\d.]+ ?\w*", opts_ev[0])
            ask(Question(
                qid=f"case-{f.name}", stage="clarify",
                prompt=f"'{f.name}' has several load cases/sizes — which "
                       "governs this check?",
                options=options, default=options[0] if options else "",
                context=f.description or f.name,
                rationale="first case taken unless told otherwise"),
                lambda ans, f=f: _apply_case_choice(f, ans))

    # ---- unresolved fragments: value / formula / discard / defer ----
    for f in case.unresolved():
        if not f.name:
            continue
        ask(Question(
            qid=f"resolve-{f.name}", stage="clarify",
            prompt=f"'{f.name}' could not be translated "
                   f"({(f.evidence or ['unknown'])[0][:70]}). Provide its "
                   "value (number + unit), a formula, 'discard', or 'defer'.",
            default="defer",
            context=f.description[:90],
            rationale="never fabricates or silently drops engineering "
                      "content — a human decides"),
            lambda ans, f=f: _apply_resolution(case, f, ans))

    # ---- noise: unused inputs ----
    if getattr(ctx, "noise_candidates", None):
        names = [f.name for f in ctx.noise_candidates]
        ask(Question(
            qid="noise-unused-inputs", stage="clarify",
            prompt=f"These inputs are not used by any formula: {names}. "
                   "Keep them in the report (documentation) or discard?",
            options=["keep all", "discard all"], default="keep all",
            context="unused by every kept calculation",
            rationale="often parameters of a not-yet-translated part"),
            lambda ans: _apply_noise(ctx, ans))

    # ---- presentation (asked once) ----
    if not any(d.qid == "final-result" for d in case.decisions):
        derived_names = [f.name for f in case.kept("derived") if f.name]
        suggestion = next(
            (n for n in derived_names
             if n.lower() in ("ur", "eta", "utilisation", "utilization")),
            derived_names[-1] if derived_names else "")
        ask(Question(
            qid="final-result", stage="clarify",
            prompt="Which quantity is the FINAL governing result of this "
                   "tool (shown prominently at the end)?",
            options=derived_names[-6:] if derived_names else [],
            default=suggestion, context="the tool's bottom line",
            rationale="looks like a utilisation ratio" if suggestion.lower()
            == "ur" else "last computed quantity"),
            lambda ans: setattr(case, "final_result", ans))
        if case.final_result:
            fr = case.final_result
            has_check = any(fr in c.expression
                            for c in case.kept("check"))
            if not has_check:
                ask(Question(
                    qid="acceptance-check", stage="clarify",
                    prompt=f"Add the acceptance criterion '{fr} <= 1.0' as "
                           "an explicit OK / NOT OK verification?",
                    options=["yes", "no"], default="yes",
                    context=f"final result {fr} has no pass/fail check",
                    rationale="a governing ratio should carry its criterion"),
                    lambda ans: _apply_acceptance(case, fr, ans))
        ask(Question(
            qid="layout", stage="clarify",
            prompt="Report layout: full derivations or compact results?",
            options=["detailed", "compact"], default="detailed",
            context="presentation of the calculation steps",
            rationale="detailed = Mathcad-style three-line steps"),
            lambda ans: setattr(case, "layout", ans))

    # ---- sketches / images ----
    for f in [x for x in case.fragments if x.kind == "image"]:
        if f.status == "discarded" or any(
                d.qid == f"image-{f.name}" for d in case.decisions):
            continue
        ask(Question(
            qid=f"image-{f.name}", stage="clarify",
            prompt=f"Sketch '{f.name}' found in the source — include it? "
                   "Where?",
            options=["top (after purpose)", "with inputs", "end", "discard"],
            default="top (after purpose)",
            context=f.evidence[0] if f.evidence else "embedded figure",
            rationale="detail sketches usually lead the calculation"),
            lambda ans, f=f: _apply_image(case, f, ans))
        if f.status == "kept":
            ask(Question(
                qid=f"caption-{f.name}", stage="clarify",
                prompt=f"Caption for sketch '{f.name}'?",
                default="Connection detail",
                context="figure caption under the sketch",
                rationale="from drawing content"),
                lambda ans, f=f: setattr(f, "description", ans))


def _apply_case_choice(f: Fragment, answer: str) -> None:
    m = re.search(r"[\d.]+", answer)
    if m:
        f.value = float(m.group(0))
        f.evidence.append(f"governing case: {answer}")


def _apply_resolution(case: CaseFile, f: Fragment, answer: str) -> None:
    ans = answer.strip()
    if ans.lower() in ("defer", "skip", "later", ""):
        f.status = "deferred"      # stays visible, never silently dropped
        return
    if ans.lower() in ("discard", "drop", "remove"):
        f.status = "discarded"
        return
    m = re.fullmatch(r"([-\d.eE]+)\s*([A-Za-z/^\d]*)", ans)
    if m:
        f.kind = "input"
        f.value = float(m.group(1))
        f.unit = m.group(2) or f.unit
        f.expression = ""
        f.status = "kept"
        f.evidence.append(f"value supplied by engineer: {ans}")
        return
    # otherwise treat as a formula
    f.expression = ans
    f.kind = "derived"
    f.status = "kept"
    f.evidence.append("formula supplied by engineer")


def _apply_noise(ctx, answer: str) -> None:
    if answer.startswith("discard"):
        for f in ctx.noise_candidates:
            f.status = "discarded"


def _apply_acceptance(case: CaseFile, final_result: str, answer: str) -> None:
    if answer.lower().startswith("y"):
        case.add(Fragment(
            fid=case.next_fid("C"), kind="check",
            expression=f"{final_result} <= 1.0",
            description="Governing acceptance criterion"))


def _apply_image(case: CaseFile, f: Fragment, answer: str) -> None:
    if answer == "discard":
        f.status = "discarded"
    else:
        f.status = "kept"
        f.evidence.append(f"placement: {answer}")


# ================================================================== #
# RECONSTRUCT
# ================================================================== #
def stage_reconstruct(case: CaseFile, ctx) -> None:
    """Dependency-ordered, compact rebuild into a CalcSheet build plan."""
    inputs = [f for f in case.kept("input") if f.name]
    deriveds = _topo_order(case)
    checks = case.kept("check")
    images = [f for f in case.kept() if f.kind == "image"]

    plan: list[tuple] = []
    top_imgs = [f for f in images if any("top" in e for e in f.evidence)]
    input_imgs = [f for f in images if any("inputs" in e for e in f.evidence)]
    end_imgs = [f for f in images
                if f not in top_imgs and f not in input_imgs]
    for f in top_imgs:
        plan.append(("image", f))
    plan.append(("section", "Input Parameters",
                 "Given quantities as defined in the source document."))
    for f in inputs:
        plan.append(("define", f))
    for f in input_imgs:
        plan.append(("image", f))
    plan.append(("section", "Calculation",
                 "Derived step by step; each step cites its clause."))
    for f in deriveds:
        plan.append(("calc", f))
    if checks or images:
        plan.append(("section", "Verification",
                     "Acceptance criteria for the governing results."))
        for f in checks:
            plan.append(("check", f))
        for f in end_imgs:
            plan.append(("image", f))
    ctx.plan = plan
    case.log("reconstruct",
             f"plan: {len(inputs)} inputs, {len(deriveds)} steps, "
             f"{len(checks)} checks, {len(images)} figures, "
             f"layout={case.layout}")


def _topo_order(case: CaseFile) -> list[Fragment]:
    """Stable dependency order: keep the author's sequence, moving a step
    later only when it uses a quantity derived further down."""
    deriveds = [f for f in case.kept("derived") if f.name]
    derived_names = {f.name for f in deriveds}
    placed: list[Fragment] = []
    placed_names: set[str] = set()
    pending = list(deriveds)
    while pending:
        nxt = next((f for f in pending
                    if (f.depends_on() & derived_names) <= placed_names), None)
        if nxt is None:          # cycle or missing deps: keep source order
            placed.extend(pending)
            break
        placed.append(nxt)
        placed_names.add(nxt.name)
        pending.remove(nxt)
    return placed


def build_sheet_from_plan(case: CaseFile, ctx) -> CalcSheet:
    sheet = CalcSheet(
        title=case.title, description=case.description,
        reference=case.reference, unit_aware=ctx.unit_aware,
        tool_id=ctx.slug)
    for op in ctx.plan:
        kind = op[0]
        try:
            if kind == "section":
                sheet.section(op[1], intro=op[2])
            elif kind == "image":
                f = op[1]
                sheet.image(f.image_b64, caption=f.description or f.name,
                            mime=f.image_mime)
            elif kind == "define":
                f = op[1]
                sheet.define(f.name, f.value if f.value is not None else 0.0,
                             unit=f.unit, description=f.description,
                             reference=f.clause, note=f.review_note)
            elif kind == "calc":
                f = op[1]
                step = sheet.calc(f.name, f.expression, unit=f.unit,
                                  description=f.description,
                                  reference=f.clause, note=f.review_note)
                step.atom_id = f.atom_id
            elif kind == "check":
                f = op[1]
                sheet.check(f.expression, description=f.description,
                            reference=f.clause)
        except CalcSheetError as exc:
            frag = op[1] if len(op) > 1 and isinstance(op[1], Fragment) else None
            if frag is not None and frag.kind == "derived":
                frag.status = "unresolved"
                frag.evidence.append(f"build error: {exc}")
            elif frag is not None:
                # checks self-heal once their dependencies resolve — note it
                frag.evidence.append(f"pending: {exc}")
    sheet.review_log = list(case.review_log)
    return sheet


# ================================================================== #
# VERIFY
# ================================================================== #
def stage_verify(case: CaseFile, ctx) -> dict:
    from src.qa.master_review import deterministic_review

    sheet = build_sheet_from_plan(case, ctx)
    ctx.sheet = sheet
    errors: list[str] = []
    warnings: list[str] = []

    # 1) source-value replication (unit-naive sources carry cached values)
    if not ctx.unit_aware:
        results = sheet.results()
        for f in case.kept("derived"):
            if f.review_note:
                continue    # corrected by the master reviewer, on record
            if f.name in results and isinstance(f.value, (int, float)) \
                    and f.value not in (0, None):
                rec = results[f.name]
                if abs(rec - f.value) > 1e-3 * max(abs(f.value), 1e-9):
                    errors.append(
                        f"{f.name}: recomputed {rec:.6g} != source "
                        f"{f.value:.6g} — translation suspect")
                    f.status = "unresolved"
                    f.evidence.append("value-mismatch vs source")

    # 2) master reviewer (units / non-finite)
    for finding in deterministic_review(sheet):
        (errors if finding.severity == "error" else warnings).append(
            f"{finding.code}: {finding.location} — {finding.message}")

    # 3) completeness
    errors.extend(case.dependency_errors())
    for f in case.unresolved():
        warnings.append(f"unresolved: {f.name} (awaiting engineer input)")

    case.verification = {"errors": errors, "warnings": warnings}
    case.log("verify", f"{len(errors)} error(s), {len(warnings)} warning(s); "
             f"checks {'PASS' if sheet.all_passed() else 'ATTENTION'}")
    return case.verification


# ================================================================== #
# REFLECT
# ================================================================== #
def stage_reflect(case: CaseFile, ctx) -> None:
    from src.qa.units import known

    checklist: list[str] = []
    for f in case.kept():
        if f.kind == "input" and f.name:
            unit_ok = (not f.unit) or f.unit in ("-",) or known(f.unit)
            checklist.append(
                f"{'✓' if unit_ok else '⚠'} input {f.name}: unit "
                f"'{f.unit or '—'}'{'' if unit_ok else ' UNKNOWN'}; "
                f"{'described' if f.description else '⚠ no description'}")
        elif f.kind == "derived" and f.name:
            clause_ok = bool(f.clause)
            unit_ok = (not f.unit) or f.unit in ("-",) or known(f.unit)
            checklist.append(
                f"{'✓' if clause_ok and unit_ok else '⚠'} calc {f.name}: "
                f"clause {f.clause or '⚠ MISSING'} "
                f"[{f.clause_confidence or '-'}]; unit "
                f"'{f.unit or '—'}'{'' if unit_ok else ' UNKNOWN'}")
    for step in getattr(ctx, "missing_steps", []) or []:
        checklist.append(f"⚠ AI: the code may also require — {step}")

    _master_review(case, ctx, checklist)

    if ctx.sheet is not None:
        for c in ctx.sheet.checks():
            checklist.append(
                f"{'✓' if c.passed else '✗'} check {c.expression}: "
                f"{'OK' if c.passed else 'NOT OK'}")
    case.reflection = checklist
    flags = sum(1 for c in checklist if c[:1] in ("⚠", "✗", "⛔"))
    case.log("reflect", f"{len(checklist)} items reviewed, {flags} flagged")


def _source_values(case: CaseFile, ctx) -> dict:
    """What the ORIGINAL shows: cached values of a unit-naive source
    (Excel) plus anything read from a print of the original."""
    out: dict = {}
    if not ctx.unit_aware:
        for f in case.kept("derived"):
            if f.name and isinstance(f.value, (int, float)) \
                    and not isinstance(f.value, bool):
                out[f.name] = {"value": float(f.value), "unit": f.unit,
                               "shown": ""}
    out.update(getattr(ctx, "original_values", {}) or {})
    return out


def _master_review(case: CaseFile, ctx, checklist: list) -> None:
    """Run the reviewer to convergence; write verified fixes back into the
    fragments so the generated tool, the report and the audit agree."""
    import tempfile

    from src.ingestion.manifest import review_summary
    from src.llm import describe
    from src.qa.master_review import review_to_convergence

    if ctx.sheet is None:
        return
    client = ctx.llm if (ctx.llm is not None and ctx.llm.available()) else None
    original = _source_values(case, ctx)
    with tempfile.TemporaryDirectory() as tmp:
        render_dir = Path(tmp) if (client is not None and ctx.render_pdf) \
            else None
        fixed, report = review_to_convergence(
            ctx.sheet, render_dir=render_dir, client=client,
            original_values=original,
            original_document=getattr(ctx, "original_document", None))
    ctx.review_report = report
    for fix in report.fixes:
        f = case.frag(fix.name)
        if f is None:
            continue
        if fix.expression and f.kind == "derived":
            f.expression = fix.expression
        if fix.unit:
            f.unit = fix.unit
        if fix.value is not None and f.kind == "input":
            f.value = float(fix.value)
        f.review_note = (f"Reviewer correction — {fix.reason} "
                         f"({fix.before} → {fix.after}).")
        f.evidence.append(f"master reviewer: {fix}")
    case.review_log = list(fixed.review_log)
    case.review = review_summary(report)
    case.ai = describe(client)
    if report.fixes:
        stage_reconstruct(case, ctx)
        stage_verify(case, ctx)
    state = "✓" if report.passed() else "⛔"
    checklist.append(
        f"{state} master review: {len(report.errors())} error(s), "
        f"{len(report.warnings())} warning(s) after {report.iterations} "
        f"iteration(s); {len(report.fixes)} correction(s) applied; AI: "
        f"{report.ai_model or 'none'}")
    for fix in report.fixes:
        checklist.append(f"🔧 {fix}")
    for finding in report.findings:
        if finding.severity in ("error", "warning"):
            mark = "⛔" if finding.severity == "error" else "⚠"
            checklist.append(f"{mark} {finding.code}: {finding.location} — "
                             f"{finding.message}")
    case.log("reflect", f"master review: passed={report.passed()}, "
             f"{len(report.fixes)} fix(es), {report.iterations} iteration(s)")


# ================================================================== #
# DELIVER
# ================================================================== #
def stage_deliver(case: CaseFile, ctx) -> dict:
    import base64

    from src.ingestion.grinder import slugify
    from src.ingestion.manifest import build_manifest, write_manifest
    from src.output_engine import render_all

    slug = ctx.slug or slugify(case.title)
    tool_dir = Path(ctx.repo_dir) / slug
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "source").mkdir(exist_ok=True)
    src = Path(case.source_path)
    if src.exists():
        (tool_dir / "source" / src.name).write_bytes(src.read_bytes())

    # image assets on disk (the generated .py loads them relative to itself)
    assets = tool_dir / "assets"
    img_files: dict[str, str] = {}
    for f in case.kept():
        if f.kind == "image" and f.image_b64:
            assets.mkdir(exist_ok=True)
            fname = f.name or f"{f.fid}.png"
            (assets / fname).write_bytes(base64.b64decode(f.image_b64))
            img_files[f.fid] = f"assets/{fname}"

    revision = getattr(ctx, "revision", "0.1") or "0.1"
    if ctx.sheet is not None:
        ctx.sheet.revision = revision
    tool_py = tool_dir / f"{slug}.py"
    tool_py.write_text(_emit_python(case, ctx, slug, img_files, revision),
                       encoding="utf-8")

    report = getattr(ctx, "review_report", None)
    needs_input = bool(case.unresolved() or case.verification.get("errors")
                       or (report is not None and not report.passed()))
    manifest = build_manifest(
        ctx.sheet, slug=slug, source_path=case.source_path,
        source_format=case.source_format,
        interpreter=f"agentic/{ctx.parser_interpreter}",
        status="needs-clarification" if needs_input
        else "agent-converted-unreviewed",
        converter="agentic", revision=revision,
        reuse_findings=getattr(ctx, "reuse", None),
        gatekeeper=getattr(ctx, "gatekeeper", None),
        review=report, ai=case.ai,
        extra={"final_result": case.final_result,
               "verification": case.verification,
               "decisions": len(case.decisions)})
    manifest_path = write_manifest(tool_dir, manifest)

    case.save(tool_dir)
    paths = {"python": str(tool_py), "manifest": str(manifest_path),
             "journal": str(tool_dir / "JOURNAL.md")}
    if ctx.sheet is not None:
        paths.update(render_all(
            ctx.sheet, tool_dir / "reports", basename=slug,
            pdf=ctx.render_pdf, meta=ctx.meta, mode=case.layout))
    case.log("deliver", f"tool written to {tool_dir} (rev {revision})")
    return paths


def _emit_python(case: CaseFile, ctx, slug: str, img_files: dict,
                 revision: str = "0.1") -> str:
    lines = [f'"""{case.title}', "",
             f"Converted by the agentic ingestion workflow from "
             f"{Path(case.source_path).name}.",
             "Full audit trail: casefile.json / JOURNAL.md alongside.",
             '"""', "",
             "from pathlib import Path", "",
             "from src.models.calculation import CalcSheet", "", "",
             "def build_sheet() -> CalcSheet:",
             "    here = Path(__file__).resolve().parent",
             "    sheet = CalcSheet(",
             f"        title={case.title!r},",
             f"        description={case.description!r},",
             f"        reference={case.reference!r},",
             f"        tool_id={slug!r},",
             f"        revision={revision!r},"]
    if ctx.unit_aware:
        lines.append("        unit_aware=True,")
    lines.append("    )")

    def note(f) -> str:
        return f", note={f.review_note!r}" if f.review_note else ""

    for op in ctx.plan:
        kind = op[0]
        if kind == "section":
            lines.append(f"    sheet.section({op[1]!r}, intro={op[2]!r})")
        elif kind == "image":
            f = op[1]
            if f.fid in img_files:
                lines.append(
                    f"    sheet.image(str(here / {img_files[f.fid]!r}), "
                    f"caption={f.description or f.name!r})")
        elif kind == "define":
            f = op[1]
            lines.append(
                f"    sheet.define({f.name!r}, "
                f"{f.value if f.value is not None else 0.0!r}, "
                f"unit={f.unit!r}, description={f.description!r}, "
                f"reference={f.clause!r}{note(f)})")
        elif kind == "calc":
            f = op[1]
            if f.status != "kept":
                continue
            atom = f".atom_id = {f.atom_id!r}" if f.atom_id else ""
            lines.append(
                f"    sheet.calc({f.name!r}, {f.expression!r}, "
                f"unit={f.unit!r}, description={f.description!r}, "
                f"reference={f.clause!r}{note(f)}){atom}")
        elif kind == "check":
            f = op[1]
            lines.append(
                f"    sheet.check({f.expression!r}, "
                f"description={f.description!r}, reference={f.clause!r})")
    if case.review_log:
        lines.append(f"    sheet.review_log = {case.review_log!r}")
    lines += ["    return sheet", "", "",
              'if __name__ == "__main__":',
              "    from src.output_engine import render_all",
              '    print(render_all(build_sheet(), "reports"))', ""]
    return "\n".join(lines)
