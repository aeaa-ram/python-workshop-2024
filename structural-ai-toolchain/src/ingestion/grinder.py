"""The Grinder — ingestion & conversion pipeline.

parse -> gatekeeper duplicate check -> master review (fix to convergence)
      -> standardize -> write to /repository

Every ground tool lands as a folder:

    repository/<slug>/
        <slug>.py        executable CalcSheet builder (the tool itself)
        <slug>.md        standardized Markdown doc with live values
        manifest.json    metadata consumed by the knowledge graph
        source/<file>    original legacy file, kept for provenance
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from src.ingestion.base import get_parser
from src.models.calculation import Clarification, ParsedTool
from src.output_engine import render_markdown


class DuplicateToolError(Exception):
    pass


@dataclass
class GrindResult:
    slug: str
    tool_dir: Path
    files: dict[str, str]
    warnings: list[str] = field(default_factory=list)
    gatekeeper_report: list = field(default_factory=list)
    reuse_findings: list = field(default_factory=list)
    clarifications: list = field(default_factory=list)
    interpreter: str = ""
    review_findings: list = field(default_factory=list)
    review: object = None


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "unnamed_tool"


def grind(
    source_path: str | Path,
    repo_dir: str | Path = "repository",
    force: bool = False,
    skip_gatekeeper: bool = False,
    client=None,
) -> GrindResult:
    """Convert one legacy file into a standardized repository tool.

    Raises DuplicateToolError when the gatekeeper flags a near-duplicate,
    unless ``force=True`` (the report is still attached to the result so
    reviewers can see what it collided with). ``client`` (an LLM client)
    adds the AI review to the master-review loop; without it the loop is
    deterministic.
    """
    source_path = Path(source_path)
    repo_dir = Path(repo_dir)
    parsed = get_parser(source_path).parse(source_path)

    report = []
    if not skip_gatekeeper:
        # Imported lazily: the knowledge graph indexes repository content
        # that the grinder itself produces.
        from src.knowledge_graph.gatekeeper import check_submission

        report = check_submission(parsed, repo_dir)
        duplicates = [m for m in report if m.verdict == "duplicate"]
        if duplicates and not force:
            names = ", ".join(m.slug for m in duplicates)
            raise DuplicateToolError(
                f"Gatekeeper: '{parsed.title}' looks like a duplicate of "
                f"existing tool(s): {names}. Re-run with force=True/--force "
                "to override, or extend the existing tool instead."
            )

    # Atomic reuse analysis: which formulas already exist as library
    # atoms or in other tools (single-source-of-truth enforcement).
    from src.knowledge_graph.reuse import analyze_reuse

    reuse_findings = analyze_reuse(parsed, repo_dir,
                                   exclude_slug=slugify(parsed.title))
    _annotate_from_atoms(parsed, reuse_findings)

    # Master reviewer: catch "looks right but wrong" results (units
    # slips, dimension errors, values that no longer match the source),
    # FIX what can be proven, and hand the rest to a human.
    review = _review_and_fix(parsed, client)
    review_findings = review.findings
    asked = {c.location for c in parsed.clarifications}
    for f in review.errors():
        if f.location not in asked:
            parsed.clarifications.append(Clarification(
                location=f.location, issue=f.code,
                question=f.message, context=f.suggested_fix))

    slug = slugify(parsed.title)
    tool_dir = repo_dir / slug
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "source").mkdir(exist_ok=True)
    shutil.copy(source_path, tool_dir / "source" / source_path.name)

    files = {
        "python": str(_write_python(parsed, tool_dir, slug)),
        "markdown": str(_write_markdown(parsed, tool_dir, slug)),
        "manifest": str(
            _write_manifest(parsed, tool_dir, slug, reuse_findings,
                            report, review)
        ),
    }
    if parsed.clarifications:
        files["clarifications"] = str(
            _write_clarifications(parsed, tool_dir, slug)
        )
    return GrindResult(
        slug=slug,
        tool_dir=tool_dir,
        files=files,
        warnings=parsed.warnings,
        gatekeeper_report=report,
        reuse_findings=reuse_findings,
        clarifications=parsed.clarifications,
        interpreter=parsed.interpreter,
        review_findings=review_findings,
        review=review,
    )


def _annotate_from_atoms(parsed: ParsedTool, findings: list) -> None:
    """A formula that IS a library atom inherits the atom's clause (shown
    in the report margin) and, if it had none, its description."""
    from src.library import get_atom

    by_name = {v.name: v for v in parsed.variables}
    for f in findings:
        if f.status != "matches_atom" or f.name not in by_name:
            continue
        atom = get_atom(f.match_id)
        var = by_name[f.name]
        var.atom_id = atom.atom_id
        var.reference = var.reference or atom.clause
        if not var.description:
            var.description = atom.description


def _review_and_fix(parsed: ParsedTool, client=None):
    """Run the master reviewer to convergence on the parsed tool and write
    every verified correction back into its variables (so the generated
    .py, the docs and the manifest all carry the corrected calculation)."""
    from src.qa.master_review import review_to_convergence

    original = {
        v.name: {"value": float(v.value), "unit": v.unit, "shown": ""}
        for v in parsed.variables
        if v.role == "derived" and isinstance(v.value, (int, float))
        and not isinstance(v.value, bool) and not parsed.unit_aware}
    fixed, report = review_to_convergence(
        parsed.to_sheet(), client=client, original_values=original)
    by_name = {v.name: v for v in parsed.variables}
    for fix in report.fixes:
        var = by_name.get(fix.name)
        if var is None:
            continue
        if fix.expression and var.role == "derived":
            var.expression = fix.expression
        if fix.unit:
            var.unit = fix.unit
        if fix.value is not None and var.role == "input":
            var.value = float(fix.value)
        var.note = (f"Reviewer correction — {fix.reason} "
                    f"({fix.before} → {fix.after}).")
    parsed.review_log = list(fixed.review_log)
    return report


def _write_clarifications(parsed: ParsedTool, tool_dir: Path, slug: str) -> Path:
    """Human-in-the-loop worksheet: exactly what the parser could not deduce."""
    lines = [
        f"# Clarifications needed — {parsed.title}",
        "",
        f"The Grinder ({parsed.interpreter or 'parser'}) converted this "
        "sheet but could not confidently resolve the items below. Answer "
        "each, update the source or the generated tool, then re-grind.",
        "",
    ]
    for i, c in enumerate(parsed.clarifications, 1):
        lines.append(f"## {i}. `{c.location}` — {c.issue}")
        lines.append("")
        lines.append(c.question)
        if c.context:
            lines.append("")
            lines.append(f"> context: `{c.context}`")
        if c.options:
            lines.append("")
            lines.append("Options:")
            lines += [f"- [ ] {o}" for o in c.options]
        lines.append("")
        lines.append("**Answer:** _..._")
        lines.append("")
    path = tool_dir / "CLARIFICATIONS.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------- #
# Standardized artifact writers
# ---------------------------------------------------------------------- #
def _write_python(parsed: ParsedTool, tool_dir: Path, slug: str) -> Path:
    lines: list[str] = []
    lines.append('"""' + parsed.title)
    lines.append("")
    lines.append(f"Auto-generated by The Grinder from "
                 f"{Path(parsed.source_path).name} ({parsed.source_format}).")
    if parsed.description:
        lines.append(parsed.description)
    lines.append('"""')
    lines.append("")
    lines.append("from src.models.calculation import CalcSheet")
    lines.append("")
    lines.append("")
    lines.append("def build_sheet() -> CalcSheet:")
    lines.append("    sheet = CalcSheet(")
    lines.append(f"        title={parsed.title!r},")
    if parsed.description:
        lines.append(f"        description={parsed.description!r},")
    if parsed.reference:
        lines.append(f"        reference={parsed.reference!r},")
    lines.append(f"        tool_id={slug!r},")
    if parsed.unit_aware:
        lines.append("        unit_aware=True,")
    lines.append("    )")

    # Mirror ParsedTool.to_sheet's resilience: emit calc()/check() only for
    # expressions that actually evaluate given the available inputs, so the
    # generated tool never crashes on load. Unresolvable formulas (e.g. ones
    # that referenced a Mathcad matrix/vector we couldn't translate) are
    # emitted as an input with an [unresolved formula] note instead.
    from src.models.calculation import CalcSheet, CalcSheetError

    probe = CalcSheet(title=parsed.title, unit_aware=parsed.unit_aware)
    inputs = [v for v in parsed.variables if v.role == "input"]
    derived = [v for v in parsed.variables if v.role == "derived"]
    if inputs:
        lines.append('    sheet.section("Input Parameters")')
        for var in inputs:
            val = var.value if var.value is not None else 0.0
            lines.append(
                f"    sheet.define({var.name!r}, {val!r}, "
                f"unit={var.unit!r}, description={var.description!r}"
                f"{_note_arg(var)})"
            )
            try:
                probe.define(var.name, val, unit=var.unit)
            except CalcSheetError:
                pass
    if derived:
        lines.append('    sheet.section("Calculation")')
        for var in derived:
            ok = True
            try:
                probe.calc(var.name, var.expression, unit=var.unit)
            except CalcSheetError:
                ok = False
            if ok:
                ref = f", reference={var.reference!r}" if var.reference else ""
                atom = f".atom_id = {var.atom_id!r}" if var.atom_id else ""
                lines.append(
                    f"    sheet.calc({var.name!r}, {var.expression!r}, "
                    f"unit={var.unit!r}, description={var.description!r}"
                    f"{ref}{_note_arg(var)}){atom}"
                )
            else:
                note = (var.description + " [unresolved formula: "
                        + var.expression + "]").strip()
                fallback = var.value if var.value is not None else 0.0
                lines.append(
                    f"    sheet.define({var.name!r}, {fallback!r}, "
                    f"unit={var.unit!r}, description={note!r})"
                )
                try:
                    probe.define(var.name, fallback, unit=var.unit)
                except CalcSheetError:
                    pass
    if parsed.checks:
        emitted = []
        for chk in parsed.checks:
            try:
                probe.check(chk)
                emitted.append(chk)
            except CalcSheetError:
                pass
        if emitted:
            lines.append('    sheet.section("Verification")')
            for chk in emitted:
                lines.append(f"    sheet.check({chk!r})")
    review_log = getattr(parsed, "review_log", None)
    if review_log:
        lines.append(f"    sheet.review_log = {review_log!r}")
    lines.append("    return sheet")
    lines.append("")
    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    from src.output_engine import render_all")
    lines.append('    print(render_all(build_sheet(), "reports"))')
    lines.append("")

    path = tool_dir / f"{slug}.py"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _note_arg(var) -> str:
    return f", note={var.note!r}" if getattr(var, "note", "") else ""


def _write_markdown(parsed: ParsedTool, tool_dir: Path, slug: str) -> Path:
    """Standardized doc = template front matter + live-rendered calc."""
    sheet = parsed.to_sheet()
    front = [
        "---",
        f"tool_id: {slug}",
        f"title: {json.dumps(parsed.title)}",
        "category: uncategorized",
        f"source_file: {Path(parsed.source_path).name}",
        f"source_format: {parsed.source_format}",
        f"reference: {json.dumps(parsed.reference)}",
        f"status: {'needs-clarification' if parsed.clarifications else 'converted-unreviewed'}",
        f"interpreter: {parsed.interpreter or 'convention'}",
        "reviewed_by: null",
        f"converted: {_dt.date.today().isoformat()}",
        "revision: '0.1'",
        "---",
        "",
    ]
    body = render_markdown(sheet)
    if parsed.clarifications:
        cl_block = ["", "## ❓ Clarifications needed (human-in-the-loop)", "",
                    "The AI Grinder could not confidently resolve these — "
                    "see `CLARIFICATIONS.md`:", ""]
        cl_block += [f"- **{c.location}** ({c.issue}): {c.question}"
                     for c in parsed.clarifications]
        body += "\n".join(cl_block) + "\n"
    if parsed.warnings:
        warn_block = ["", "## Conversion Warnings", ""]
        warn_block += [f"- ⚠️ {w}" for w in parsed.warnings]
        body += "\n".join(warn_block) + "\n"
    path = tool_dir / f"{slug}.md"
    path.write_text("\n".join(front) + body, encoding="utf-8")
    return path


def _write_manifest(
    parsed: ParsedTool,
    tool_dir: Path,
    slug: str,
    reuse_findings: list | None = None,
    gatekeeper: list | None = None,
    review=None,
) -> Path:
    from src.ingestion.manifest import build_manifest, write_manifest

    sheet = parsed.to_sheet()
    sheet.review_log = list(getattr(parsed, "review_log", []) or [])
    manifest = build_manifest(
        sheet, slug=slug, source_path=parsed.source_path,
        source_format=parsed.source_format,
        interpreter=parsed.interpreter or "convention",
        status=("needs-clarification" if parsed.clarifications
                else "converted-unreviewed"),
        converter="grinder", warnings=parsed.warnings,
        clarifications=parsed.clarifications,
        reuse_findings=reuse_findings, gatekeeper=gatekeeper, review=review,
        ai=review.ai_model if review is not None else "")
    return write_manifest(tool_dir, manifest)
