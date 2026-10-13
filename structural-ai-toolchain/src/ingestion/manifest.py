"""One manifest format for every converted tool.

Both converters (the fast Grinder and the agentic workflow) write the same
``manifest.json``, built from the FINAL calculation sheet — after the
master reviewer's corrections — so the knowledge graph, the dashboard and
reuse analysis read one consistent record of what the tool computes.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

MANIFEST_SCHEMA = "structural-ai-toolchain/manifest@2"


def build_manifest(
    sheet,
    *,
    slug: str,
    source_path: str | Path,
    source_format: str,
    interpreter: str,
    status: str,
    converter: str,
    revision: str = "0.1",
    warnings: list | None = None,
    clarifications: list | None = None,
    reuse_findings: list | None = None,
    gatekeeper: list | None = None,
    review=None,
    ai: str = "",
    extra: dict | None = None,
) -> dict:
    from src.knowledge_graph.fingerprint import try_fingerprint

    variables = []
    for item in sheet.items:
        if item.kind not in ("input", "calc"):
            continue
        variables.append({
            "name": item.name,
            "role": "input" if item.kind == "input" else "derived",
            "unit": item.unit,
            "description": item.description,
            "expression": item.expression,
            "clause": item.reference,
            "atom_id": item.atom_id,
            "fingerprint": (try_fingerprint(item.expression)
                            if item.expression else None),
        })
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "tool_id": slug,
        "title": sheet.title,
        "description": sheet.description,
        "reference": sheet.reference,
        "revision": revision,
        "source_file": Path(source_path).name,
        "source_format": source_format,
        "converted": _dt.date.today().isoformat(),
        "converter": converter,
        "interpreter": interpreter,
        "ai": ai or "none (deterministic path)",
        "status": status,
        "unit_aware": bool(getattr(sheet, "unit_aware", False)),
        "variables": variables,
        "checks": [c.expression for c in sheet.checks()],
        "checks_passed": sheet.all_passed() if sheet.checks() else None,
        "results": sheet.results(),
        "warnings": list(warnings or []),
        "clarifications": [
            {"location": c.location, "issue": c.issue, "question": c.question}
            for c in (clarifications or [])
        ],
        "formula_analysis": [
            {"name": f.name, "status": f.status, "match": f.match_id}
            for f in (reuse_findings or [])
        ],
        "gatekeeper": [
            {"slug": m.slug, "title": m.title, "score": round(m.score, 3),
             "verdict": m.verdict}
            for m in (gatekeeper or [])
        ],
        "review": review_summary(review) if review is not None else None,
        "review_log": list(getattr(sheet, "review_log", []) or []),
    }
    if extra:
        manifest.update(extra)
    return manifest


def review_summary(report) -> dict:
    return {
        "passed": report.passed(),
        "converged": report.converged,
        "iterations": report.iterations,
        "ai": report.ai_model,
        "verdict": report.verdict,
        "fixes": [f.as_log() for f in report.fixes],
        "findings": [str(f) for f in report.findings
                     if f.severity in ("error", "warning")],
    }


def write_manifest(tool_dir: str | Path, manifest: dict) -> Path:
    path = Path(tool_dir) / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str),
                    encoding="utf-8")
    return path


def next_revision(tool_dir: str | Path) -> str:
    """Revision for a re-conversion of an existing tool (0.1 -> 0.2)."""
    path = Path(tool_dir) / "manifest.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8")).get(
            "revision", "0.1")
        major, minor = (int(x) for x in str(current).split(".")[:2])
        return f"{major}.{minor + 1}"
    except (OSError, ValueError, json.JSONDecodeError):
        return "0.1"
