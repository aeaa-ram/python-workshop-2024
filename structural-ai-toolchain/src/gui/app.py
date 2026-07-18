"""Ingestion GUI — the front door of the toolchain.

Launch with ``python main.py gui``. Workflow it enforces:

1. Pick a legacy file (.xlsx/.xlsm/.csv/.ipynb/.py/.mcdx).
2. **Investigate** — the file is parsed (nothing written) and the
   Gatekeeper reports similar existing tools plus the atomic reuse
   breakdown (which formulas already exist as library atoms or in other
   tools, which are truly new).
3. Decide: *Create new tool* (blocked if a duplicate is found),
   *Force create* (override the duplicate block, kept in the report),
   or walk away and extend the existing tool instead.

The controller functions are separated from tkinter so the same logic is
unit-testable and reusable by a future web UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.ingestion.base import get_parser
from src.knowledge_graph.gatekeeper import check_submission
from src.knowledge_graph.reuse import analyze_reuse
from src.models.calculation import ParsedTool


# ------------------------------------------------------------------ #
# Controller (no tkinter — unit-testable)
# ------------------------------------------------------------------ #
@dataclass
class Investigation:
    parsed: ParsedTool
    gatekeeper: list
    reuse: list
    blocked: bool = False
    lines: list[str] = field(default_factory=list)


def investigate(file_path: str | Path, repo_dir: str | Path) -> Investigation:
    """Parse a candidate file and analyze it without writing anything."""
    parsed = get_parser(file_path).parse(Path(file_path))
    gatekeeper = check_submission(parsed, repo_dir)
    reuse = analyze_reuse(parsed, repo_dir)
    blocked = any(m.verdict == "duplicate" for m in gatekeeper)

    lines: list[str] = [f"Parsed: '{parsed.title}' ({parsed.source_format})"]
    inputs = sum(1 for v in parsed.variables if v.role == "input")
    derived = sum(1 for v in parsed.variables if v.role == "derived")
    lines.append(
        f"  {inputs} inputs, {derived} formulas, {len(parsed.checks)} checks"
    )
    for w in parsed.warnings:
        lines.append(f"  ⚠️  {w}")

    lines.append("")
    if gatekeeper:
        lines.append("Similar existing tools:")
        lines.extend(f"  {m}" for m in gatekeeper)
        if blocked:
            lines.append(
                "  ⛔ Duplicate detected — extend the existing tool, or "
                "use 'Force create' only with a good reason."
            )
    else:
        lines.append("No similar tool in the repository.")

    lines.append("")
    if reuse:
        lines.append("Atomic breakdown of the formulas:")
        lines.extend(f"  {f}" for f in reuse)
        reused = sum(1 for f in reuse if f.status != "new")
        lines.append(
            f"  -> {reused}/{len(reuse)} formulas already exist "
            "(they should be sheet.apply()'d from the library, "
            "not re-implemented)."
        )
    return Investigation(parsed, gatekeeper, reuse, blocked, lines)


def create_tool(
    file_path: str | Path, repo_dir: str | Path, force: bool = False
) -> list[str]:
    """Grind the file into the repository; returns log lines."""
    from src.ingestion import grind
    from src.knowledge_graph import build_index

    result = grind(file_path, repo_dir, force=force)
    build_index(repo_dir)
    lines = [f"✔ Created tool '{result.slug}'"]
    lines += [f"  {kind}: {path}" for kind, path in result.files.items()]
    lines.append(
        "  Next: python main.py render "
        f"{result.slug} --pdf   (A4 report with embedded JSON)"
    )
    return lines


# ------------------------------------------------------------------ #
# Tkinter shell
# ------------------------------------------------------------------ #
def launch(repo_dir: str | Path = "repository") -> None:  # pragma: no cover
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    root = tk.Tk()
    root.title("Structural AI Toolchain — Ingestion")
    root.geometry("860x560")

    state: dict = {"file": None, "investigation": None}

    top = tk.Frame(root, padx=10, pady=8)
    top.pack(fill="x")
    file_var = tk.StringVar()
    tk.Entry(top, textvariable=file_var).pack(
        side="left", fill="x", expand=True, padx=(0, 6)
    )

    log = scrolledtext.ScrolledText(
        root, wrap="word", font=("Consolas", 10), state="disabled"
    )
    log.pack(fill="both", expand=True, padx=10, pady=(0, 6))

    def write(lines: list[str]) -> None:
        log.configure(state="normal")
        log.insert("end", "\n".join(lines) + "\n\n")
        log.see("end")
        log.configure(state="disabled")

    def pick() -> None:
        path = filedialog.askopenfilename(
            title="Select legacy calculation file",
            filetypes=[
                ("All supported", "*.xlsx *.xlsm *.csv *.ipynb *.py *.mcdx"),
                ("All files", "*.*"),
            ],
        )
        if path:
            file_var.set(path)

    def run_investigation() -> None:
        path = file_var.get().strip()
        if not path:
            messagebox.showwarning("No file", "Pick a file first.")
            return
        try:
            inv = investigate(path, repo_dir)
        except Exception as exc:  # surface parser errors to the user
            write([f"⛔ Investigation failed: {exc}"])
            return
        state.update(file=path, investigation=inv)
        write(inv.lines)
        create_btn.configure(
            state="disabled" if inv.blocked else "normal"
        )
        force_btn.configure(state="normal" if inv.blocked else "disabled")

    def run_create(force: bool) -> None:
        inv = state.get("investigation")
        if inv is None:
            messagebox.showwarning("Not investigated",
                                   "Run 'Investigate' first.")
            return
        if force and not messagebox.askyesno(
            "Force create",
            "The Gatekeeper flagged this as a duplicate.\n"
            "Create it anyway?",
        ):
            return
        try:
            write(create_tool(state["file"], repo_dir, force=force))
        except Exception as exc:
            write([f"⛔ Create failed: {exc}"])

    tk.Button(top, text="Browse…", command=pick).pack(side="left")
    tk.Button(top, text="Investigate", command=run_investigation).pack(
        side="left", padx=6
    )

    bottom = tk.Frame(root, padx=10, pady=6)
    bottom.pack(fill="x")
    create_btn = tk.Button(
        bottom, text="Create new tool", state="disabled",
        command=lambda: run_create(False),
    )
    create_btn.pack(side="left")
    force_btn = tk.Button(
        bottom, text="Force create (override duplicate)", state="disabled",
        command=lambda: run_create(True),
    )
    force_btn.pack(side="left", padx=6)
    tk.Button(bottom, text="Close", command=root.destroy).pack(side="right")

    write([
        "Structural AI Toolchain — ingestion front door.",
        "1) Browse to a legacy file   2) Investigate   3) Create / Force.",
    ])
    root.mainloop()
