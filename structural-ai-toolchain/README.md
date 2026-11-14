# Calculation Knowledge Base

Turns existing structural calculations (Mathcad, Excel, PDF, Python, Jupyter, Word, scans) into
small, checked **calculation objects**, sorted by the clause structure of the design code, and
lets an engineer use them without touching code.

It follows the eight-stage architecture in
[`docs/workshop/calculation-knowledge-architecture.html`](docs/workshop/calculation-knowledge-architecture.html).
This is a working MVP of that architecture: it runs end to end, on real files.

## What it did with three real files

A Mathcad worksheet (precast beam to EN 1992-1-1), a PDF print of the same worksheet, and an Excel
workbook with ten sheets of slab shear checks went through the whole chain in about five seconds:

| Step | Result |
|---|---|
| Conversion | Mathcad: 84 of 84 formulas re-evaluate to the worksheet's value, and 80 of 80 results Mathcad stored in the file are reproduced. Excel: 1,040 of 1,040 formulas re-evaluate to Excel's cached value. PDF: 100 printed quantities read with name, value, unit, label and clause. |
| Curation | The PDF was recognised as a print of the Mathcad sheet: it is used as a benchmark, not counted as a second opinion. |
| Decomposition | 654 formulas recognised as quantities of the code and rewritten in consistent units with the code's symbols. |
| Consolidation | 24 calculation objects: 5 confirmed by both independent sources, 14 seen in one source only, 5 where the sources disagree. `V_Rd,c` came out as EN 1992-1-1 expressions (6.2.a) and (6.2.b), merged from three variants that were each a special case. |
| Benchmarks | 656 source values re-run against the objects: 613 reproduced, 32 differ (the findings below), 11 could not be compared. |
| Reference | 15 objects agree with the open-source library `structuralcodes` over 200 random samples each; one differs and says so. |
| Findings | In 24 cases the workbook's `V_Rd,c` is below the code minimum `V_Rd,c,min`, which the sheet calculates but does not apply. In 8 cases its `V_Rd,c,min` leaves out `k_1·σ_cp` although `σ_cp` is not zero. The lever arm is `0.9·d` in one source and `d − λx/2` in the other: reported as a disagreement, not merged. |

The knowledge base in [`knowledge_base/`](knowledge_base) and the web calculator in
[`app/index.html`](app/index.html) are that run, with anonymised source labels. The project files
themselves are not in this repository (see [Project data](#project-data)).

## Quick start

```bash
pip install -r requirements.txt

# 1. put source files in inbox/  (they stay on your machine)
# 2. build the knowledge base and the web calculator
python -m ckb build

# 3. use it
open app/index.html              # web calculator: no server, just the file
python -m ckb list               # what is in the knowledge base
python -m ckb run V_Rd_c         # asks for the inputs in the terminal
python -m ckb excel V_Rd_c       # Excel calculator with live formulas
python -m ckb report V_Rd_c --pdf
```

`python -m ckb --help` lists every command. Tests: `python -m pytest` (37 tests; the four that need
real project files are skipped when the inbox is empty).

## Using an object without code

| Way | What you get |
|---|---|
| **Web calculator** `app/index.html` | Pick a quantity from the clause tree, type the inputs, read a self-documenting calculation that updates as you type: equation, numbers substituted, result, clause. Load a real case from the sources. Enter any intermediate value directly instead of calculating it. Evidence and the generated code are one click away. |
| **Excel** `python -m ckb excel V_Rd_c` | A workbook where every step is a native Excel formula (no macros, no add-in). Checked against LibreOffice in the tests. |
| **Back from Excel** `python -m ckb check file.xlsx` | Any workbook, including an edited calculator, is read as a source and placed against the knowledge base: *existing*, *special case*, *extension*, *differs* or *new topic*. |
| **Terminal** `python -m ckb run V_Rd_c` | Asks for each input with its unit and a starting value from a real case; prints the calculation. `d=450 "b_w=0.3 m"` on the command line skips the questions. |
| **Report** `python -m ckb report V_Rd_c --pdf` | Calculation sheet with title block, every step, utilisation, notes and limitations, and the basis of each object. |
| **Python** `knowledge_base/python/ckb_objects` | One readable function per object, plus a `*_chain` function from the primary inputs. Generated, never hand-edited. |
| **AI assistant** `python -m ckb tools` | Tool definitions so an assistant calls the benchmarked objects instead of doing arithmetic from memory. |

All of these are printed from the same formula tree, so they cannot disagree with each other.

## How it works

| Stage | What happens | Module |
|---|---|---|
| 1 Retrieval and curation | Files found; exact duplicates dropped; a print of another source recognised; unsupported files flagged with the reason. | `ckb/pipeline.py` |
| 2 Conversion | Every file becomes a list of *statements*: name, formula, value, unit, the text and clause printed next to it, and where it sits. Every formula is re-evaluated and compared with what the source shows. | `ckb/convert/` |
| 3 Decomposition | Each statement is matched to a quantity of the code by symbol, label and context. Its formula is rewritten in N, mm, MPa with the code's symbols. | `ckb/distill/decompose.py` |
| 4 Consolidation | Variants of one quantity are merged by generalisation. A merge is accepted only if every variant is numerically a special case of the result. What cannot be merged is a disagreement and is kept apart. | `ckb/distill/consolidate.py` |
| 5 Object generation | One small object per quantity, with variants, benchmarks, reference check, warnings and real example cases. | `ckb/pipeline.py`, `ckb/kb/` |
| 6 Repository and search | YAML object files, generated Python, search, and classification of new sources. | `ckb/kb/` |
| 7 Self-documenting calculations | Web calculator, Excel, report, terminal, tools. | `ckb/use/` |
| 8 Maintenance | Health check: every stored benchmark re-run, generated code compared, reference re-checked, unversioned edits caught. | `ckb/maintain/health.py` |

More detail, and how each workshop concern is handled: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### The taxonomy seed holds no formulas

[`ckb/data/taxonomy.yaml`](ckb/data/taxonomy.yaml) lists the quantities EN 1992-1-1 defines (symbol,
clause, usual unit) and how engineers spell them. The logic is distilled from the sources. Adding a
topic means adding entries there; no code changes.

### What needs a language model

Nothing in the chain above. A model is used only where something has to be *read*: a scan,
handwriting, or the formulas of a PDF print (`--vision`). What it returns is treated as a proposal:
a transcribed formula is accepted only if it reproduces the transcribed result. Set
`ANTHROPIC_API_KEY` to enable it. That path is covered by tests with a scripted model; it has not
been run against the live API in this environment.

## Limits of this MVP

- One code (EN 1992-1-1) and about sixty quantities in the seed. Other topics appear as "not recognised".
- Only straight-line calculations are distilled: no loops, iteration, tables or lookups (`VLOOKUP` and
  similar are reported per cell, not converted).
- Units a source does not state are taken as the quantity's usual unit and noted on the instance.
- A PDF print gives values, not formulas, without the vision path.
- Consensus groups what engineers do; it does not prove it right. Trust comes from the benchmarks,
  the independent reference where one exists, and an engineer's review. There is no approval
  workflow here: every object is published with its status and warnings visible.
- Python sources are executed (in a separate process) to obtain their values. Run ingestion on files
  you would be willing to run.

## Project data

Source files go in `inbox/` and working output in `workspace/`; both are ignored by git. The
committed knowledge base was built with `python -m ckb build --anonymous`, which keeps file names,
sheet names and case descriptions out of it. Without that flag the knowledge base carries full file
names and locations, which is what you want for traceability inside a company.

## Layout

```
ckb/                 the package (expr, units, notation, ir, convert, distill, kb, use, maintain, cli)
ckb/data/            taxonomy seed
knowledge_base/      distilled objects (YAML), benchmarks (JSON), generated Python
app/index.html       web calculator
inbox/               your source files (not committed)
workspace/           converted sources, reports, Excel calculators (not committed)
tests/               synthetic fixtures for every file type
docs/                architecture notes and the workshop material
```

Open-source building blocks: [`mcad2py`](https://pypi.org/project/mcad2py/) (Mathcad Prime to Python,
MIT) and [`structuralcodes`](https://github.com/fib-international/structuralcodes) (independent
reference, Apache-2.0).
