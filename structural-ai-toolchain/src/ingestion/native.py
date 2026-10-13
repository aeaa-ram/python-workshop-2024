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


def register_tool(slug: str, repo_dir: str | Path = "repository",
                  client=None) -> dict:
    """Generate manifest.json + standardized .md for a native tool. The
    master reviewer runs (deterministically, or with ``client``) and its
    verdict lands in the manifest; native tools are NOT auto-corrected —
    the author owns the code, so findings are reported instead."""
    from src.ingestion.manifest import build_manifest, write_manifest
    from src.qa.master_review import review

    repo_dir = Path(repo_dir)
    sheet = load_sheet(slug, repo_dir)
    tool_dir = repo_dir / slug
    report = review(sheet, client=client)
    manifest = build_manifest(
        sheet, slug=slug, source_path=f"{slug}.py", source_format="native",
        interpreter="native", converter="native",
        status="native-unreviewed" if report.passed() else "needs-attention",
        revision=sheet.revision, review=report, ai=report.ai_model)
    manifest_path = write_manifest(tool_dir, manifest)

    front = [
        "---",
        f"tool_id: {slug}",
        f"title: {json.dumps(sheet.title)}",
        "category: uncategorized",
        f"source_file: {slug}.py",
        "source_format: native",
        f"reference: {json.dumps(sheet.reference)}",
        f"status: {manifest['status']}",
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
    return {"manifest": str(manifest_path), "markdown": str(md_path),
            "review": report}


def sheet_to_python(sheet: CalcSheet, tool_dir: str | Path, slug: str,
                    origin: str = "") -> str:
    """Emit a standalone tool module that rebuilds ``sheet`` exactly —
    used to write back a reviewer-corrected calculation. Figures are
    stored under ``assets/`` next to the module."""
    import base64
    import hashlib

    tool_dir = Path(tool_dir)
    lines = [f'"""{sheet.title}', "",
             origin or "Rebuilt from a reviewed calculation sheet.", '"""',
             "", "from pathlib import Path", "",
             "from src.models.calculation import CalcSheet", "", "",
             "def build_sheet() -> CalcSheet:",
             "    here = Path(__file__).resolve().parent",
             "    sheet = CalcSheet(",
             f"        title={sheet.title!r},",
             f"        description={sheet.description!r},",
             f"        reference={sheet.reference!r},",
             f"        tool_id={slug!r},",
             f"        revision={sheet.revision!r},"]
    if sheet.unit_aware:
        lines.append("        unit_aware=True,")
    lines.append("    )")

    def opt(name: str, value) -> str:
        return f", {name}={value!r}" if value else ""

    for it in sheet.items:
        latex = sheet.latex_names.get(it.name) if it.name else None
        if it.kind == "section":
            lines.append(f"    sheet.section({it.name!r}{opt('intro', it.intro)})")
        elif it.kind == "text":
            lines.append(f"    sheet.text({it.text!r})")
        elif it.kind == "image":
            data = base64.b64decode(it.image_b64)
            ext = it.image_mime.split("/")[-1].replace("jpeg", "jpg")
            fname = f"{hashlib.sha1(data).hexdigest()[:12]}.{ext}"
            (tool_dir / "assets").mkdir(parents=True, exist_ok=True)
            (tool_dir / "assets" / fname).write_bytes(data)
            lines.append(f"    sheet.image(str(here / 'assets' / {fname!r})"
                         f"{opt('caption', it.text)}, "
                         f"width_mm={it.image_width_mm!r})")
        elif it.kind == "input":
            lines.append(
                f"    sheet.define({it.name!r}, {it.value!r}, unit={it.unit!r}"
                f"{opt('description', it.description)}{opt('latex', latex)}"
                f"{opt('reference', it.reference)}{opt('note', it.note)})")
        elif it.kind == "calc":
            lines.append(
                f"    step = sheet.calc({it.name!r}, {it.expression!r}, "
                f"unit={it.unit!r}{opt('description', it.description)}"
                f"{opt('latex', latex)}{opt('reference', it.reference)}"
                f"{opt('note', it.note)})")
            if it.atom_id:
                lines.append(f"    step.atom_id = {it.atom_id!r}")
        elif it.kind == "check":
            lines.append(
                f"    sheet.check({it.expression!r}"
                f"{opt('description', it.description)}"
                f"{opt('reference', it.reference)})")
    if sheet.review_log:
        lines.append(f"    sheet.review_log = {sheet.review_log!r}")
    lines += ["    return sheet", "", "",
              'if __name__ == "__main__":',
              "    from src.output_engine import render_all",
              '    print(render_all(build_sheet(), "reports"))', ""]
    return "\n".join(lines)
