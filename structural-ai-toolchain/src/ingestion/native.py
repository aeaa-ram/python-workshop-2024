"""Native tool authoring — creating NEW tools without grinding a legacy
file (see docs/AUTHORING_GUIDE.md for the human workflow).

``scaffold_tool`` writes a starter ``repository/<slug>/<slug>.py`` that
an engineer edits by hand; ``register_tool`` then executes the sheet and
generates the same manifest.json + standardized .md that The Grinder
produces, so native and converted tools are indistinguishable to the
knowledge graph and the output engine.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
from pathlib import Path

from src.ingestion.grinder import slugify
from src.models.calculation import CalcSheet
from src.output_engine import render_markdown

_SCAFFOLD = '''"""{title}

Native tool — authored directly against the toolchain (no legacy source).
Edit build_sheet() below, then run:

    python main.py register {slug}     # manifest + standardized doc
    python main.py render {slug} --pdf # A4 report
"""

from src.models.calculation import CalcSheet


def build_sheet() -> CalcSheet:
    sheet = CalcSheet(
        title={title!r},
        description="TODO one-paragraph purpose statement",
        reference="TODO code clauses, e.g. EN 1992-1-1:2004 §7.3.4",
        tool_id={slug!r},
    )

    sheet.section("Input Parameters")
    sheet.define("b", 1000, unit="mm", description="Section width")
    # TODO: real inputs — sheet.define(name, value, unit=..., description=...)

    sheet.section("Calculation")
    # RULE: shared formulas come from the library, never re-typed.
    # Check what exists first:  python main.py atoms
    # sheet.apply("E_cm_t", "ec2.concrete.E_cm_t")
    # sheet.calc("A", "b*h", unit="mm^2", description="Area")  # new logic only

    sheet.section("Verification")
    # sheet.check("w_k <= w_max", "Crack width within limit")

    return sheet


if __name__ == "__main__":
    from src.output_engine import render_all

    print(render_all(build_sheet(), "reports"))
'''


def scaffold_tool(title: str, repo_dir: str | Path = "repository") -> Path:
    """Create a starter native tool folder; returns the .py path."""
    slug = slugify(title)
    tool_dir = Path(repo_dir) / slug
    tool_py = tool_dir / f"{slug}.py"
    if tool_py.exists():
        raise FileExistsError(f"{tool_py} already exists")
    tool_dir.mkdir(parents=True, exist_ok=True)
    tool_py.write_text(
        _SCAFFOLD.format(title=title, slug=slug), encoding="utf-8"
    )
    return tool_py


def load_sheet(slug: str, repo_dir: str | Path = "repository") -> CalcSheet:
    """Import repository/<slug>/<slug>.py and build its sheet."""
    tool_py = Path(repo_dir) / slug / f"{slug}.py"
    if not tool_py.exists():
        raise FileNotFoundError(tool_py)
    spec = importlib.util.spec_from_file_location(slug, tool_py)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_sheet()


def register_tool(slug: str, repo_dir: str | Path = "repository") -> dict:
    """Generate manifest.json + standardized .md for a native tool."""
    from src.knowledge_graph.fingerprint import try_fingerprint

    repo_dir = Path(repo_dir)
    sheet = load_sheet(slug, repo_dir)
    tool_dir = repo_dir / slug

    variables = []
    for item in sheet.items:
        if item.kind == "input":
            variables.append(
                {
                    "name": item.name,
                    "role": "input",
                    "unit": item.unit,
                    "description": item.description,
                    "expression": "",
                    "fingerprint": None,
                }
            )
        elif item.kind == "calc":
            variables.append(
                {
                    "name": item.name,
                    "role": "derived",
                    "unit": item.unit,
                    "description": item.description,
                    "expression": item.expression,
                    "fingerprint": try_fingerprint(item.expression),
                    "atom_id": item.atom_id or None,
                }
            )

    manifest = {
        "tool_id": slug,
        "title": sheet.title,
        "description": sheet.description,
        "reference": sheet.reference,
        "source_file": f"{slug}.py",
        "source_format": "native",
        "converted": _dt.date.today().isoformat(),
        "status": "native-unreviewed",
        "variables": variables,
        "checks": [c.expression for c in sheet.checks()],
        "results": sheet.results(),
        "warnings": [],
        "formula_analysis": [],
    }
    manifest_path = tool_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    front = [
        "---",
        f"tool_id: {slug}",
        f"title: {json.dumps(sheet.title)}",
        "category: uncategorized",
        f"source_file: {slug}.py",
        "source_format: native",
        f"reference: {json.dumps(sheet.reference)}",
        "status: native-unreviewed",
        "reviewed_by: null",
        f"converted: {_dt.date.today().isoformat()}",
        f"revision: '{sheet.revision}'",
        "---",
        "",
    ]
    md_path = tool_dir / f"{slug}.md"
    md_path.write_text(
        "\n".join(front) + render_markdown(sheet), encoding="utf-8"
    )
    return {"manifest": str(manifest_path), "markdown": str(md_path)}
