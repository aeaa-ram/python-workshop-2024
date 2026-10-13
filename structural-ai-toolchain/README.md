# Structural AI Toolchain

Converts legacy structural calculations (Mathcad Prime, Excel, Jupyter,
Python) into one version-controlled library of standardized Python tools,
checked against a central knowledge base, verified by a master reviewer,
and printed as Mathcad-style A4 reports with every formula written out.

**New here? Read the 1-page [docs/QUICKSTART.md](docs/QUICKSTART.md).**
Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · writing tools by
hand: [docs/AUTHORING_GUIDE.md](docs/AUTHORING_GUIDE.md) · doc format:
[docs/TOOL_TEMPLATE.md](docs/TOOL_TEMPLATE.md) · known traps:
[docs/PITFALLS.md](docs/PITFALLS.md) · workshop brief:
[docs/workshop/WORKSHOP_EMAIL.md](docs/workshop/WORKSHOP_EMAIL.md).

## Try it

```bash
cd structural-ai-toolchain
pip install -r requirements.txt
python main.py doctor        # what is installed / whether the AI is configured
python main.py demo          # Excel + notebook + Mathcad -> repository -> PDFs
pytest -q
```

The AI (Claude) is optional. Without `ANTHROPIC_API_KEY` (or an `ant auth
login` profile) every stage runs on its deterministic path and says so in
the audit trail; with it, the toolchain also interprets messy spreadsheets,
researches code clauses and reviews the rendered PDF visually.

## The pipeline

```
legacy file ──► parse ──► knowledge-base gate ──► rebuild in Python ──► master review ──► repository + PDF
 .mcdx .xlsx     atoms,      duplicate? atom?       CalcSheet: symbolic,   dimensions, scale,     .py  .md  manifest
 .ipynb .py      units,      revise / new / abort   substituted, result    one-to-one vs original, reports/*.pdf
                 checks                                                    AI visual — fix & loop
```

Two converters share every stage:

| Command | Use it for |
|---|---|
| `python main.py ingest <file>` | **Agentic** conversion: atomises the file, researches clauses, asks you inline (governing case, unresolved values, noise, final result, sketches), loops until converged, writes a full `JOURNAL.md` |
| `python main.py grind <file>` | **Fast** conversion for tidy sheets; questions go to `CLARIFICATIONS.md` |

Both write the same `manifest.json` (schema `manifest@2`) and run the same
master reviewer.

### What "correct" means here

- **Units are honoured.** Mathcad sheets evaluate in canonical N/mm, units
  written inside formulas count, results show in the unit Mathcad showed,
  and the substituted line carries units:
  `P_Rd,1 = 0.8·π·(19 mm)²·450 MPa/(4·1.25) = 81.66 kN`.
- **Nothing is quietly simplified.** Rounding (`ROUND`, Mathcad `round`) and
  conditionals (`IF`, Mathcad `if/otherwise`) are translated exactly.
- **The master reviewer fixes, not just flags.** A force computed in N but
  labelled kN is corrected (and the corrected step carries a visible note);
  when relabelling would leave a check comparing kN with N, the reviewer
  picks the fix that keeps the whole sheet consistent — the verdict flips
  to NOT OK if that is the truth. An AI correction is kept only if the
  deterministic re-check improves.
- **One-to-one with the original.** Excel cached values (or values the AI
  reads from a PDF print via `--original`) are compared at their printed
  precision.

```bash
python main.py review <slug> [--original original.pdf] [--fix]
```

## Reports

`python main.py render <slug> --pdf` prints a branded A4 report via
headless Chromium: Mathcad-style title block on every page (logo, project,
project no., prepared / checked / approved, rev / date, page X of Y),
narrative leads, clause references right-aligned in italic, bold results,
green OK / red NOT OK panels, selectable equations, bookmarks. Large
numbers print as `1.584·10⁶`. Branding lives in
`src/output_engine/branding.py`.

The complete calculation is baked **inside the page content** — hand
someone only the PDF and they can rebuild it:

```python
from src.output_engine import reconstruct_from_pdf
data = reconstruct_from_pdf("report.pdf")   # inputs, formulas, results, reviewer log
```

No attachment by default (`attach=True` is opt-in). `--mode compact`
prints one line per step; `src/output_engine/parametric.py` tabulates many
load cases with OK / NOT OK and flags the governing one.

## Single source of truth

Shared formulas live once in `src/library` (EN 1992-1-1 seed set, EN
1994-1-1 headed studs, mechanics). The knowledge graph fingerprints
formulas structurally (name-independent), so it recognises library math
inside an ingested sheet, carries the atom's clause into the report, and
reports what is reused vs. new. National annexes are a sub-group: same
formula, different coefficient (`resolve("crack.max_spacing", "EN-GB")`),
or a separate atom sharing the concept when the method itself differs.

```bash
python main.py atoms --tree | --search "crack width"
python main.py ask "Punching shear check"     # does it exist already?
python main.py dashboard                      # hosted / recycled / reviewed / edits
```

## Module overview

| Path | Role |
|---|---|
| `src/models` | `CalcSheet`: self-evaluating, unit-aware, faithful-display calculation model; `replay()` for reviewer fixes |
| `src/llm` | One Claude client (structured JSON, vision, refusal fallback) + scripted client for tests |
| `src/ingestion` | Parsers (mcdx, xlsx/xlsm/csv, ipynb, py), AI Grinder, agentic workflow (`agent/`), shared manifest |
| `src/knowledge_graph` | Gatekeeper duplicate detection, index, structural fingerprints, reuse analysis |
| `src/library` | Formula atoms with clauses and national-annex variants |
| `src/qa` | Master reviewer (dimensions, scale, correspondence, AI review, fix loop), lint checks |
| `src/output_engine` | Markdown / HTML / PDF / LaTeX renderers, in-page data layer, parametric tables |
| `src/dashboard`, `src/gui` | HTML dashboard; tkinter front door (investigate → create / merge) |
| `src/sharepoint_sync` | MS Graph client + webhook placeholders |
| `repository/` | The tools (`.py` + `.md` + manifest + source + reports) |
