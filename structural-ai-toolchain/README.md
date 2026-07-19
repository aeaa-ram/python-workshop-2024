# Structural AI Toolchain

Foundation for an AI-augmented ecosystem that converts legacy structural
engineering files (Mathcad, Excel, Python, Jupyter) into a centralized,
version-controlled repository of standardized Python tools with
Mathcad-style, print-ready documentation.

**New here? Read the 1-page [docs/QUICKSTART.md](docs/QUICKSTART.md)**
(also as [QUICKSTART.pdf](docs/QUICKSTART.pdf)) — it navigates the whole
thing without the deep docs.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design (incl.
the **AI Grinder** for messy spreadsheets),
[docs/TOOL_TEMPLATE.md](docs/TOOL_TEMPLATE.md) for the standardized doc
format, [docs/AUTHORING_GUIDE.md](docs/AUTHORING_GUIDE.md) for writing new
tools by hand, and [docs/PITFALLS.md](docs/PITFALLS.md) for the pitfalls
database the QA layer targets.

## The AI Grinder (messy sheets)

`grind` auto-dispatches: tidy convention sheets convert exactly; **messy
real-world sheets** (scattered tables, multi-tab, named ranges, lookups)
go through an LLM pipeline that reads the workbook, names the variables,
translates the formulas, and — crucially — **recomputes everything and
checks it against the sheet's own cached values**, so nothing is silently
wrong. Anything it can't deduce (a magic number, a `VLOOKUP`, circular
logic) is written to `CLARIFICATIONS.md` as a precise question, not a
failure. Works offline via a deterministic heuristic; set
`ANTHROPIC_API_KEY` (+ `pip install anthropic`) to use Claude for the
hardest sheets. See the pipeline in `src/ingestion/{workbook_extract,
interpret,llm_client,ai_pipeline}.py`.

## Quickstart

```bash
cd structural-ai-toolchain
pip install -r requirements.txt

# End-to-end trial: builds a dummy crack-width Excel workbook and a beam
# notebook, grinds both into /repository, runs the gatekeeper + atomic
# reuse analysis, renders md/html/tex/json and bookmarked PDF reports.
python main.py demo
pytest
```

## Two ways to add a tool

**A) Grind a legacy file** (Excel/Jupyter/Python/CSV; Mathcad mocked):

```bash
python main.py gui                        # drag-in GUI: investigate -> create/merge
python main.py check examples/crack_width_ec2.xlsx   # CLI dry-run (dupes + reuse)
python main.py grind examples/crack_width_ec2.xlsx   # convert into /repository
```

**B) Author a new tool from scratch** (see the authoring guide):

```bash
python main.py atoms                      # list reusable library formulas
python main.py ask "Punching shear check" # is it a duplicate?
python main.py new  "Punching Shear Check (EN 1992-1-1 6.4)"   # scaffold
# ...edit build_sheet()...
python main.py register punching_shear_check_en_1992_1_1_6_4   # doc + manifest
python main.py qa       punching_shear_check_en_1992_1_1_6_4 --prompt   # QA (+AI prompt)
```

Then render the report (all tools, both origins, work identically):

```bash
python main.py render <slug> --pdf        # A4 PDF: bookmarks + embedded JSON
```

## Reports: branded, self-contained, AI-proof

`render --pdf` prints a **branded A4 report** via headless Chromium —
company logo, black Mathcad-style page frame, prepared/checked/approved
cartouche, OK / NOT OK verdicts, repeated header/footer. Math is
pre-rendered to inline SVG, so **no internet or LaTeX install** is needed.
Swap the company look in one place (`src/output_engine/branding.py`);
point `logo_path` at your official logo (the default is a placeholder).

Every PDF has **document bookmarks** and — baked into the **page content,
not as an attachment** — a self-contained machine-readable layer. Hand
someone only the PDF and they reconstruct the whole calculation, immune to
the attachment-stripping that loses data in modern PDF round-trips:

```python
from src.output_engine import reconstruct_from_pdf
data = reconstruct_from_pdf("report.pdf")   # inputs, formulas, results — no attachment
```

(Reconstruction uses `pdftotext` if present, else pypdf. `apt install
poppler-utils` for the most robust extraction.)

**Render modes:** `--mode detailed` (Mathcad three-line) or `--mode
compact` (`E_cm = 30464 MPa`). For many load cases, a **parametric study**
tabulates every varying input + result with OK / NOT OK and flags the
governing case — see `src/output_engine/parametric.py`.

## Single source of truth (the atom library)

Shared formulas live once in `src/library` and are reused everywhere —
the EN 1992-1-1 E-modulus-in-time chain feeds crack-width, deflection and
bending tools from the same code. Tools `sheet.apply()` an atom instead of
re-typing it; the knowledge graph **fingerprints formulas structurally**
(name-independent) so it recognizes reused math inside freshly ingested
sheets and reports an atomic breakdown of what is reused vs. genuinely new.

```python
from src.library import custom, resolve, search, catalog
custom.E_cm_t(E_cm=33000, f_cm_t=30.3, f_cm=38)   # call any formula directly
search("crack width")                             # free-text find
catalog()                                         # drill-down tree
```

**National annexes are a sub-group, not a new silo.** A coefficient that
differs by country (e.g. crack-spacing `k_3`) stays the same symbol in the
same formula — only its value changes: `resolve("crack.max_spacing",
"EN-GB")`, or `sheet.apply(..., jurisdiction="EN-GB")` which auto-injects
the annex coefficient. When the *whole method* changes, register a
separate atom sharing the same `concept` with a different `jurisdiction`.

```bash
python main.py atoms --tree              # jurisdiction → code → chapter → clause
python main.py atoms --search "crack width"
python main.py dashboard                 # human-readable: hosted/recycled/source/edits
```

## Module overview

| Path | Role |
|---|---|
| `src/models` | `CalcSheet` — self-evaluating, self-documenting, faithful-display calculation model + JSON serialization |
| `src/library` | Atomic formula library (single source of truth), `custom.*` accessor, EC2 seed atoms |
| `src/ingestion` | "The Grinder": xlsx/xlsm/csv/ipynb/py parsers, mcdx mock, pipeline, native authoring |
| `src/knowledge_graph` | Gatekeeper duplicate detection, repo index, structural fingerprint + atomic reuse analysis |
| `src/output_engine` | Markdown / print-ready HTML / LaTeX renderers, PDF bookmark + machine-readable stamp |
| `src/qa` | Deterministic QA checks + AI-review prompt export (Eurocode QA seam) |
| `src/gui` | tkinter ingestion front door (investigate → create/merge) |
| `src/sharepoint_sync` | MS Graph client + webhook placeholders |
| `repository/` | SSOT of tools (`.py` + `.md` + manifest + source + reports) |
