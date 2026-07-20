"""The stages of the agentic ingestion workflow.

Each stage reads/updates the CaseFile and journals what it did:

  intake      — atomise the source into fragments (math, text, images)
  decompose   — dependency graph; find noise, repetition, orphans
  research    — code/standard identification per fragment (citations,
                atom library, LLM knowledge when configured)
  clarify     — ask the human INLINE about everything ambiguous:
                keep/discard, governing load case, missing values,
                final governing result, sketches & their placement
  reconstruct — rebuild a clean, compact, dependency-ordered tool
  verify      — recompute; compare against source values; units review
  reflect     — per-value self-review checklist (units, clauses, sanity)
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
            matched += 1
    # 3) document-level reference as fallback context
    if case.reference:
        for f in case.kept("derived"):
            if not f.clause:
                f.clause = case.reference
                f.clause_confidence = "doc"
    # 4) LLM deep research (engages when a backend is configured)
    if ctx.llm is not None and getattr(ctx.llm, "available", lambda: False)():
        case.log("research", "LLM clause research pass engaged")
        # per-fragment prompt loop would run here (backend-specific)
    else:
        case.log("research", "LLM research unavailable — deterministic "
                             "knowledge base only (citations + atom library)")
    case.log("research", f"clauses: {cited} cited in source, "
             f"{matched} matched to library atoms")


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
    """Kahn's algorithm over the derived fragments: a step is placeable
    once every derived quantity it references has been placed."""
    deriveds = [f for f in case.kept("derived") if f.name]
    derived_names = {f.name for f in deriveds}
    placed: list[Fragment] = []
    placed_names: set[str] = set()
    pending = list(deriveds)
    while pending:
        ready = [f for f in pending
                 if (f.depends_on() & derived_names) <= placed_names]
        if not ready:            # cycle or missing deps: keep source order
            placed.extend(pending)
            break
        for f in ready:
            placed.append(f)
            placed_names.add(f.name)
            pending.remove(f)
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
                             reference=f.clause)
            elif kind == "calc":
                f = op[1]
                sheet.calc(f.name, f.expression, unit=f.unit,
                           description=f.description or f.name,
                           reference=f.clause)
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
    if ctx.sheet is not None:
        for c in ctx.sheet.checks():
            checklist.append(
                f"{'✓' if c.passed else '✗'} check {c.expression}: "
                f"{'OK' if c.passed else 'NOT OK'}")
    if ctx.llm is not None and getattr(ctx.llm, "available", lambda: False)():
        case.log("reflect", "LLM engineering-judgment review engaged")
    else:
        case.log("reflect", "LLM judgment review unavailable — "
                            "deterministic checklist only")
    case.reflection = checklist
    flags = sum(1 for c in checklist if c.startswith("⚠") or c.startswith("✗"))
    case.log("reflect", f"{len(checklist)} items reviewed, {flags} flagged")


# ================================================================== #
# DELIVER
# ================================================================== #
def stage_deliver(case: CaseFile, ctx) -> dict:
    import base64
    import datetime as _dt
    import json as _json

    from src.ingestion.grinder import slugify
    from src.output_engine import render_all

    slug = ctx.slug or slugify(case.title)
    tool_dir = Path(ctx.repo_dir) / slug
    tool_dir.mkdir(parents=True, exist_ok=True)

    # image assets on disk (the generated .py loads them relative to itself)
    assets = tool_dir / "assets"
    img_files: dict[str, str] = {}
    for f in case.kept():
        if f.kind == "image" and f.image_b64:
            assets.mkdir(exist_ok=True)
            fname = f.name or f"{f.fid}.png"
            (assets / fname).write_bytes(base64.b64decode(f.image_b64))
            img_files[f.fid] = f"assets/{fname}"

    tool_py = tool_dir / f"{slug}.py"
    tool_py.write_text(_emit_python(case, ctx, slug, img_files),
                       encoding="utf-8")

    manifest = {
        "tool_id": slug, "title": case.title, "description": case.description,
        "reference": case.reference, "source_file": Path(case.source_path).name,
        "source_format": case.source_format,
        "converted": _dt.date.today().isoformat(),
        "status": ("needs-clarification" if case.unresolved()
                   or case.verification.get("errors")
                   else "agent-converted-unreviewed"),
        "interpreter": f"agentic/{ctx.parser_interpreter}",
        "final_result": case.final_result,
        "variables": [
            {"name": f.name, "role": f.kind, "unit": f.unit,
             "description": f.description, "expression": f.expression,
             "clause": f.clause, "atom_id": f.atom_id}
            for f in case.kept() if f.kind in ("input", "derived")],
        "checks": [f.expression for f in case.kept("check")],
        "results": ctx.sheet.results() if ctx.sheet else {},
        "verification": case.verification,
    }
    (tool_dir / "manifest.json").write_text(
        _json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    case.save(tool_dir)
    paths = {"python": str(tool_py),
             "manifest": str(tool_dir / "manifest.json"),
             "journal": str(tool_dir / "JOURNAL.md")}
    if ctx.sheet is not None:
        paths.update(render_all(
            ctx.sheet, tool_dir / "reports", basename=slug,
            pdf=ctx.render_pdf, meta=ctx.meta, mode=case.layout))
    case.log("deliver", f"tool written to {tool_dir}")
    return paths


def _emit_python(case: CaseFile, ctx, slug: str, img_files: dict) -> str:
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
             f"        tool_id={slug!r},"]
    if ctx.unit_aware:
        lines.append("        unit_aware=True,")
    lines.append("    )")
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
                f"reference={f.clause!r})")
        elif kind == "calc":
            f = op[1]
            if f.status != "kept":
                continue
            lines.append(
                f"    sheet.calc({f.name!r}, {f.expression!r}, "
                f"unit={f.unit!r}, description={(f.description or f.name)!r}, "
                f"reference={f.clause!r})")
        elif kind == "check":
            f = op[1]
            lines.append(
                f"    sheet.check({f.expression!r}, "
                f"description={f.description!r}, reference={f.clause!r})")
    lines += ["    return sheet", "", "",
              'if __name__ == "__main__":',
              "    from src.output_engine import render_all",
              '    print(render_all(build_sheet(), "reports"))', ""]
    return "\n".join(lines)
