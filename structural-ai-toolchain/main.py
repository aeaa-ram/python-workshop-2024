"""Structural AI Toolchain — CLI orchestrator.

Usage (run from the structural-ai-toolchain directory):

    python main.py demo                    # end-to-end trial run
    python main.py grind <file> [--force]  # convert a legacy file
    python main.py check <file>            # gatekeeper dry-run on a file
    python main.py ask "<title>"           # gatekeeper check for an idea
    python main.py render <slug> [--out DIR]
    python main.py index                   # rebuild knowledge-graph index
    python main.py list                    # list repository tools
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

REPO_DIR = PROJECT_ROOT / "repository"


def cmd_grind(args) -> int:
    from src.ingestion import DuplicateToolError, grind

    try:
        result = grind(args.file, REPO_DIR, force=args.force)
    except DuplicateToolError as exc:
        print(f"⛔ {exc}")
        return 1
    interp = f" (interpreter: {result.interpreter})" if result.interpreter else ""
    print(f"✔ Ground '{args.file}' -> {result.tool_dir}{interp}")
    for kind, path in result.files.items():
        print(f"  {kind:>13}: {path}")
    for warning in result.warnings:
        print(f"  ⚠️  {warning}")
    for match in result.gatekeeper_report:
        print(f"  {match}")
    if result.reuse_findings:
        print("  Atomic breakdown:")
        for finding in result.reuse_findings:
            print(f"    {finding}")
    if result.clarifications:
        print(f"  ❓ {len(result.clarifications)} clarification(s) needed "
              f"(status: needs-clarification) — see CLARIFICATIONS.md:")
        for c in result.clarifications:
            print(f"    {c}")
    from src.knowledge_graph import build_index

    build_index(REPO_DIR)
    return 0


def cmd_check(args) -> int:
    from src.gui.app import investigate

    inv = investigate(args.file, REPO_DIR)
    print("\n".join(inv.lines))
    return 2 if inv.blocked else 0


def cmd_ask(args) -> int:
    from src.knowledge_graph import check_request

    variables = [
        v.strip()
        for v in (getattr(args, "variables", "") or "").split(",")
        if v.strip()
    ]
    matches = check_request(
        args.title,
        args.description or "",
        variables=variables,
        repo_dir=REPO_DIR,
    )
    if not matches:
        print(f"✔ Nothing similar to '{args.title}' in the repository — go ahead.")
        return 0
    print(f"Found {len(matches)} related tool(s) for '{args.title}':")
    for match in matches:
        print(match)
    return 0


def cmd_render(args) -> int:
    from src.ingestion.native import load_sheet
    from src.output_engine import render_all

    tool_py = REPO_DIR / args.slug / f"{args.slug}.py"
    if not tool_py.exists():
        print(f"⛔ No tool '{args.slug}' in {REPO_DIR}")
        return 1
    sheet = load_sheet(args.slug, REPO_DIR)
    out_dir = Path(args.out) if args.out else REPO_DIR / args.slug / "reports"
    paths = render_all(
        sheet, out_dir, basename=args.slug,
        pdf=getattr(args, "pdf", False),
        mode=getattr(args, "mode", "detailed"),
    )
    print(f"✔ Rendered '{sheet.title}' ({getattr(args, 'mode', 'detailed')}):")
    for kind, path in paths.items():
        print(f"  {kind:>9}: {path}")
    return 0


def cmd_gui(_args) -> int:
    from src.gui.app import launch

    launch(REPO_DIR)
    return 0


def cmd_new(args) -> int:
    from src.ingestion.native import scaffold_tool

    tool_py = scaffold_tool(args.title, REPO_DIR)
    print(f"✔ Scaffolded native tool: {tool_py}")
    print("  Edit build_sheet(), then:")
    print(f"    python main.py register {tool_py.parent.name}")
    return 0


def cmd_register(args) -> int:
    from src.ingestion.native import register_tool
    from src.knowledge_graph import build_index

    files = register_tool(args.slug, REPO_DIR)
    build_index(REPO_DIR)
    print(f"✔ Registered '{args.slug}':")
    for kind, path in files.items():
        print(f"  {kind:>9}: {path}")
    return 0


def cmd_qa(args) -> int:
    from src.ingestion.native import load_sheet
    from src.qa import build_review_prompt, run_checks

    sheet = load_sheet(args.slug, REPO_DIR)
    findings = run_checks(sheet)
    if not findings:
        print(f"✔ '{args.slug}': no deterministic QA findings.")
    for finding in findings:
        print(finding)
    if args.prompt:
        prompt_path = REPO_DIR / args.slug / "ai_review_prompt.md"
        prompt_path.write_text(build_review_prompt(sheet), encoding="utf-8")
        print(f"\n✔ AI review prompt written to {prompt_path}")
        print("  Paste it into Claude (or wire up AnthropicReviewer) for "
              "the engineering-judgment review.")
    errors = sum(1 for f in findings if f.severity == "error")
    return 1 if errors else 0


def cmd_review(args) -> int:
    from src.ingestion.native import load_sheet
    from src.qa import review

    sheet = load_sheet(args.slug, REPO_DIR)
    render_dir = (REPO_DIR / args.slug / "reports" / "_review") \
        if args.visual else None
    rep = review(sheet, render_dir=render_dir)
    print(f"Master review of '{args.slug}' "
          f"({'AI+deterministic' if rep.ai_used else 'deterministic'}):")
    print(rep)
    if not rep.passed():
        print(f"\n⛔ {len(rep.errors())} error(s) — not ready to issue.")
    else:
        print("\n✔ No blocking issues found.")
    return 1 if not rep.passed() else 0


def cmd_atoms(args) -> int:
    from src.library import all_atoms, catalog_lines, search

    if getattr(args, "search", None):
        hits = search(args.search)
        if not hits:
            print(f"No atoms match '{args.search}'.")
            return 0
        for hit in hits:
            print(hit)
        return 0
    if getattr(args, "tree", False):
        print("\n".join(catalog_lines()))
        return 0
    for atom in sorted(all_atoms(), key=lambda a: a.atom_id):
        juris = "" if atom.jurisdiction == "EN" else f" ({atom.jurisdiction})"
        print(f"- {atom.atom_id:<26}{juris} {atom.result} = {atom.expression}")
        clause = f" [{atom.clause}]" if atom.clause else ""
        print(f"  {atom.description}{clause}")
    return 0


def cmd_dashboard(args) -> int:
    from src.dashboard import generate_dashboard

    out = Path(args.out) if getattr(args, "out", None) else None
    path = generate_dashboard(REPO_DIR, out)
    print(f"✔ Dashboard: {path}")
    print("  Open it in a browser — searchable view of hosted tools, "
          "reuse, sources, edits and the formula library.")
    return 0


def cmd_index(_args) -> int:
    from src.knowledge_graph import build_index

    index = build_index(REPO_DIR)
    print(
        f"✔ Indexed {len(index['tools'])} tool(s), "
        f"{len(index['relationships'])} relationship edge(s) "
        f"-> {REPO_DIR / '.index.json'}"
    )
    return 0


def cmd_list(_args) -> int:
    manifests = sorted(REPO_DIR.glob("*/manifest.json"))
    if not manifests:
        print("Repository is empty — run 'python main.py demo' for a trial.")
        return 0
    for manifest in manifests:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        print(
            f"- {data['tool_id']:<28} {data['title']} "
            f"[{data['source_format']}, {data['status']}]"
        )
    return 0


def cmd_demo(args) -> int:
    """End-to-end trial: fixtures -> grind -> gatekeeper -> reports."""
    from examples.make_fixtures import make_all

    print("1) Generating example legacy files (dummy Excel + notebook)...")
    fixtures = make_all(PROJECT_ROOT / "examples")
    for path in fixtures:
        print(f"   {path}")

    print("\n2) Grinding them into /repository ...")
    for path in fixtures:
        grind_args = argparse.Namespace(file=str(path), force=True)
        cmd_grind(grind_args)

    print("\n3) Gatekeeper trial — asking for a suspiciously familiar tool:")
    ask_args = argparse.Namespace(
        title="Crack width verification for RC slab to EN 1992-1-1",
        description="computes characteristic crack widths for reinforced "
        "concrete slabs",
        variables="w_k,s_r_max,phi,A_s,w_max",
    )
    cmd_ask(ask_args)

    print("\n4) Rendering branded A4 reports (md + tex + html + pdf + json):")
    for manifest in sorted(REPO_DIR.glob("*/manifest.json")):
        slug = json.loads(manifest.read_text(encoding="utf-8"))["tool_id"]
        cmd_render(argparse.Namespace(slug=slug, out=None, pdf=True,
                                      mode="detailed"))

    print("\n5) Machine-readable check — reconstructing a calc from the PDF "
          "ALONE (no attachment):")
    from src.output_engine import reconstruct_from_pdf
    slug = "crack_width_verification_rc_slab_en_1992_1_1_7_3_4"
    pdf = REPO_DIR / slug / "reports" / f"{slug}.pdf"
    if pdf.exists():
        data = reconstruct_from_pdf(pdf)
        print(f"   recovered {len(data['items'])} items; "
              f"w_k = {data['results'].get('w_k'):.4f} mm, "
              f"schema {data['schema']}")

    print("\n6) National annex — same crack-spacing formula, different k_3:")
    from src.library import resolve
    for juris in ("EN", "XX-DEMO"):
        r = resolve("crack.max_spacing", juris)
        print(f"   {juris:8} k_3 = {r.params['k_3']}  ({r.provenance[-1]})")

    print("\n7) Parametric study — one crack-width check over many load "
          "cases (tabular OK / NOT OK):")
    from src.ingestion.native import load_sheet
    from src.output_engine.parametric import ParametricStudy
    sheet = load_sheet(slug, REPO_DIR)
    cases = [{"M_qp": m} for m in (30, 45, 55, 65, 80)]
    study = ParametricStudy(sheet, cases,
                            [f"M={c['M_qp']}kNm" for c in cases])
    print(study.summary_markdown(result_vars=["sigma_s", "w_k"]))

    print("\n8) Central dashboard (hosted / recycled / sources / edits):")
    cmd_dashboard(argparse.Namespace(out=None))

    print(
        "\nDone. Open a repository/<slug>/reports/<slug>.pdf (branded A4, "
        "bookmarks, self-contained data) or repository/dashboard.html."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="structural-ai-toolchain",
        description="AI-Augmented Structural Engineering Toolchain",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("grind", help="convert a legacy file into /repository")
    p.add_argument("file")
    p.add_argument("--force", action="store_true",
                   help="override gatekeeper duplicate block")
    p.set_defaults(func=cmd_grind)

    p = sub.add_parser("check", help="gatekeeper dry-run on a file")
    p.add_argument("file")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("ask", help="gatekeeper check for a tool idea")
    p.add_argument("title")
    p.add_argument("--description", default="")
    p.add_argument(
        "--variables", default="",
        help="comma-separated symbols the tool would use, e.g. w_k,s_r_max",
    )
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("render", help="render a repository tool's reports")
    p.add_argument("slug")
    p.add_argument("--out", default=None)
    p.add_argument("--pdf", action="store_true",
                   help="also print an A4 PDF via headless Chromium")
    p.add_argument("--mode", choices=["detailed", "compact"],
                   default="detailed", help="calculation detail level")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("gui", help="launch the ingestion GUI")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("new", help="scaffold a NEW native tool (no legacy file)")
    p.add_argument("title")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("register",
                       help="generate manifest + doc for a native tool")
    p.add_argument("slug")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("qa", help="run QA checks on a tool")
    p.add_argument("slug")
    p.add_argument("--prompt", action="store_true",
                   help="also export the AI review prompt")
    p.set_defaults(func=cmd_qa)

    p = sub.add_parser("review", help="AI master reviewer: catch wrong "
                       "results (units, unresolved) before issue")
    p.add_argument("slug")
    p.add_argument("--visual", action="store_true",
                   help="also render pages for the AI visual review")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("atoms", help="browse the shared formula library")
    p.add_argument("--tree", action="store_true",
                   help="drill-down tree: jurisdiction/code/chapter/clause")
    p.add_argument("--search", default=None,
                   help="free-text search, e.g. --search 'crack width'")
    p.set_defaults(func=cmd_atoms)

    p = sub.add_parser("dashboard",
                       help="generate the human-readable HTML dashboard")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("index", help="rebuild the knowledge-graph index")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("list", help="list converted tools")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("demo", help="end-to-end trial run")
    p.set_defaults(func=cmd_demo)

    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.func(arguments))
