# Calculation Knowledge Base

Design-code expressions as small, checked **calculation objects**, with the design background an
engineer needs to apply them, and the evidence of how real calculation files apply them kept out
of the way until someone asks for it. Engineers use the objects without touching code: a web
calculator, Excel, Mathcad Prime, a report generator, the terminal, or an AI assistant.

It follows the eight-stage architecture in
[`docs/workshop/calculation-knowledge-architecture.html`](docs/workshop/calculation-knowledge-architecture.html).

## The idea in one paragraph

The **code comes first**. The registry in [`ckb/data/`](ckb/data) holds each code's own
expressions: f_cd = α_cc·f_ck/γ_C, not the f_ck/γ_C most spreadsheets write. It also holds
recommended values and NDPs, conditions of application (σ_cp ≤ 0.2 f_cd), and sourced design
background (scope, limitations, pitfalls). The source files (Mathcad, Excel, PDF, Python,
Jupyter, Word, scans) are then **distilled against the code**. Each formula they contain is
classified as *as code*, *alternative*, *simplified* (with every difference listed, why it was
probably made, and whether it is on the safe side in that case), *differs*, or *project-specific*.
Every value a source shows becomes a benchmark. Where an independent library implements the same
clause, the object is also compared with it. The result of that review is a confidence level per
object: ● checked, ◐ not yet checked, ○ review needed.

## What it did with three real files

A Mathcad worksheet (precast beam to EN 1992-1-1), a PDF print of it, and an Excel workbook with ten
sheets of slab shear checks:

| Step | Result |
|---|---|
| Conversion | Mathcad: 84/84 formulas re-evaluate to the worksheet's values, 80/80 results stored by Mathcad reproduced. Excel: 1,040/1,040 formulas reproduce Excel's cached values. PDF: 100 printed quantities. |
| Curation | The PDF is recognised as a print of the worksheet: a benchmark, not a second opinion. |
| Against the code | 146 objects from EN 1992-1-1, EN 1993-1-1, EN 1993-1-8 and EN 1994-1-1. Source formulas: 21 as code, 9 simplified, 1 permitted alternative, 6 different, 12 project-specific. |
| Simplifications found | f_cd: α_cc left out (recommended value 1 assumed). V_Rd,c: lower bound V_Rd,c,min not applied, which governs in 22 of 80 cases; that is on the safe side here. V_Rd,c,min: k_1·σ_cp left out where σ_cp ≠ 0 (8 cases, unsafe side). γ_C = 1.3775 used 72 times against the recommended 1.5. Punching: f_ywd,ef = 250 + 0.2·d against 250 + 0.25·d in the code. |
| Understanding | A 540× difference was traced to one spreadsheet column holding two calculations (a full-width check and a per-metre strip); the lookup now prefers the same case and section. Per-metre working became context on the objects and on the b_w input. |
| Benchmarks | 672 source values re-run: 623 reproduced, 38 differ (each with its reason), 11 not comparable. |
| Independent reference | 21 objects agree with [`structuralcodes`](https://github.com/fib-international/structuralcodes) over 200 random samples each. |
| Confidence | 31 checked, 115 not yet checked (the wider code seed, not yet seen in a source), 0 need review. |

[`knowledge_base/`](knowledge_base) and [`app/index.html`](app/index.html) are that run, built with
`--anonymous` (no file or sheet names). The project files are not in this repository.

## Quick start

```bash
pip install -r requirements.txt
python -m ckb build                    # inbox/ -> knowledge base, code blocks, web calculator

open app/index.html                    # web calculator: one file, no server
python -m ckb search concrete shear    # find objects by words, symbol (V_Rd,c) or clause (6.2.2)
python -m ckb show V_Rd_c              # formula, conditions, design background
python -m ckb status V_Rd_c            # the evidence: sources, simplifications, benchmarks, reference
python -m ckb run V_Rd_c d=450 b_w=300 A_sl=942 --check 60
python -m ckb excel V_Rd_c             # Excel calculator, named ranges, live formulas
python -m ckb mathcad V_Rd_c           # Mathcad Prime worksheet
python -m ckb report V_Rd_c d=450 --pdf --docx   # PDF with bookmarks, Word with native equations
python -m ckb report-template V_Rd_c -o form.xlsx  # a report set up in an Excel form instead of YAML
python -m ckb verify workspace/excel/V_Rd_c.xlsx
python -m ckb questions                # differences between sources and code that nothing explained
```

`python -m ckb --help` lists every command. Tests: `python -m pytest` (52 tests; four of them need
real project files in `inbox/` and are skipped without them).

## Using an object

| Way | What you get |
|---|---|
| **Web calculator** `app/index.html` | Code tree with a confidence dot per object, and word search. Per object: **Calculate** (inputs with recommended values and NDP marks, the equation, substituted values and bold result, utilisation and conditions; cases to compare members; a report template from those cases), **Design background** (scope, limitations, pitfalls and guidance with sources; where the object is shared with other codes; a dependency map), **Chart** (the result against any input, with hover), **Code**, **Status** (the evidence). Decimals and units in Settings. |
| **Excel** `ckb excel` | Native formulas on named ranges (`=MIN(A_sl/(b_w*d),0.02)`), or plain cell references with `--refs cells` (`=MIN(C8/(C9*C7),0.02)`); no macros. Inputs are changed in the workbook. |
| **Mathcad Prime** `ckb mathcad` | A worksheet with real math regions, units where the empirical formulas need them (`200 mm/d`), `if` regions for conditions. |
| **Report** `ckb report` | See below. |
| **Terminal** `ckb run` | Asks for each input, or takes them on the command line. |
| **Python** `knowledge_base/python/ckb_objects` | One function per object, plus a `*_chain` function from the primary inputs. Design logic only. |
| **AI assistant** `ckb tools` | Tool definitions, so an assistant calls the objects instead of doing the arithmetic itself. |

Number style is the same everywhere: 2 decimals by default, small values keep 3 significant
digits, display units per quantity (`--decimals 3 --unit V_Rd_c=kN`, or a `style.yaml`). The
calculation always runs in N, mm, MPa.

## Reports

A report is a YAML template that you set up once and run for any number of cases:

```bash
python -m ckb report-template V_Rd_c -o shear.yaml     # a commented starting point
python -m ckb report --template shear.yaml --pdf
python -m ckb report --template shear.yaml --cases strips.xlsx --pdf    # same layout, other cases
python -m ckb report --template shear.yaml --from-excel workspace/excel/V_Rd_c.xlsx
```

```yaml
title: Shear resistance of slab strips
style: {decimals: 2, units: {V_Rd_c: kN}}
defaults: {f_ck: 35, b_w: 1000}
cases:                                    # or  cases: {file: strips.xlsx}  (header: case, d [mm], ...)
  - {case: Strip A, d: 273, A_sl: 1340, V_Ed: 150}
  - {case: Strip B, d: 259, A_sl: 754, V_Ed: 140}
blocks:
  - heading: Governing strip
  - calc: V_Rd_c                          # one case written out
    case: governing                       # governing | first | a case name
    show: [equation, substituted, result] # drop items to shorten it
    steps: all                            # all | result | [k, rho_l]
    remarks: {d: "from the reinforcement drawing"}
  - table: V_Rd_c                         # every case in one table
    columns: [case, d, A_sl, V_Rd_c, V_Ed, utilisation, verdict]
    sort: utilisation desc
  - chart: V_Rd_c                         # a parameter study
    x: d
    range: [150, 600]
    series: [V_Rd_c, V_Rd_c_min]
  - text: Any note.
  - pagebreak: true
```

The output is a static A4 page: bold inline results, utilisation as a number with OK / NOT OK, no
sliders and no history. `--pdf` prints it with headless Edge, Chrome or Chromium and adds bookmarks
for the title, the headings and every calculation. `--docx` writes the same report as a Word
document with native, editable Word equations and heading styles (navigation pane; *Save as PDF*
with bookmarks). Every equation is printed from the object's formula tree: `expr.to_mathml` for
HTML/PDF ([`ckb/use/report.py`](ckb/use/report.py)), `expr.to_omml` for Word
([`ckb/use/report_docx.py`](ckb/use/report_docx.py)), `expr.to_latex` for LaTeX. The footer lists
`ckb <object> <version>` for every object used.

Nobody has to edit YAML: `report-template V_Rd_c -o form.xlsx` writes the same template as an Excel
form (title block, blocks with drop-down choices, cases, remarks), and the web calculator has a
report builder that fills the template from your cases and choices.

## How do I know it is the same logic?

Every output (code block, Excel, Mathcad, report) is printed from one formula tree and carries the
object's **version**: a fingerprint of formula, unit, fixed values and conditions. `python -m ckb
verify <file>` reads a file back and checks it:

- **Excel**: the formulas are unchanged, and LibreOffice recalculates every step to the knowledge
  base's numbers.
- **Mathcad**: the worksheet is read back and re-run, step by step.
- **Code block**: the function is run at several points.
- **Report**: every version in the footer is still current.

`python -m ckb health` re-runs every stored benchmark and catches any edit made without a new
version.

## When a source and the code disagree

A difference is investigated before it is reported. The investigation tries, by recalculating:

1. An input read from another calculation in the same file.
2. Two results that differ by a width (per metre against full width).
3. One input off by a power of ten (a unit).
4. One input with another value.

Whatever it explains is recorded with the explanation, and general lessons become context on the
object. Per-metre working, for example, shows on the b_w input. What nothing explains becomes a
question for an engineer:

```bash
python -m ckb questions                                  # everything that was tried, and what would make it agree
python -m ckb answer Q1a2b3c4 --verdict explained --text "load per metre of walkway" --lesson "..."
```

The answer is applied in the next build, and a lesson becomes design background of the object.
`python -m ckb build --ask-model` also asks a language model for its reading first; its answer is
attached as a proposal and never accepted on its own.

## Several codes, no duplicates

When a later code writes an expression that is already stored, it is linked, not copied.
EN 1994-1-1 f_cd = f_ck/γ_C is the EN 1992-1-1 object with α_cc fixed to 1 *for EN 1994-1-1*.
EN 1994-1-1 f_sd = f_yk/γ_S is the same expression as f_yd, so it becomes one object with two names.
The same expression with other inputs is an *instance*:

- Punching uses k with the mean effective depth (`of: k, bind: {d: d_eff_p}`).
- A composite column uses the steel buckling curve χ with its own slenderness.

The expression is taken from the original, never typed twice. `python -m ckb codes` shows the links.
Adding a code means adding one YAML file to `ckb/data/codes/`.

## Where the web calculator lives

`app/index.html` is one static file. It holds the objects, their JavaScript functions (printed
from the same trees), and the evidence. It works offline, from SharePoint, Azure Static Web Apps
or any internal web server. The copy shared in the workshop channel is hosted privately on
claude.ai. A hosted version could add what one file cannot: shared ratings and usage counts, and
an AI search agent on top of the word search.

## How it works

| Stage | What happens | Module |
|---|---|---|
| 0 Code baseline | Each code's expressions, recommended values, NDPs, conditions and design background; codes linked so nothing is stored twice. | `ckb/data/`, `ckb/distill/taxonomy.py` |
| 1 Retrieval and curation | Files found; duplicates dropped; prints of another source recognised. | `ckb/pipeline.py` |
| 2 Conversion | Every file becomes *statements* (name, formula, value, unit, label, clause, location); every formula re-evaluated against the source. | `ckb/convert/` |
| 3 Decomposition | Statements matched to code quantities by symbol, label and context; formulas rewritten in N, mm, MPa. | `ckb/distill/decompose.py` |
| 4 Against the code | Each source formula classified against the code expression, with the reason for each simplification and its effect. Quantities the codes do not define are merged among the sources instead. | `ckb/distill/baseline.py`, `consolidate.py` |
| 5 Objects | Design logic (`objects/*.yaml`) and evidence (`evidence/*.json`) kept apart; benchmarks, reference check, confidence. | `ckb/pipeline.py`, `ckb/distill/benchmarks.py`, `reference.py` |
| 6 Repository and search | Generated Python, word search, classification of new files (`ckb check`). | `ckb/kb/` |
| 7 Use | Web calculator, Excel, Mathcad, reports, terminal, tools, verify. | `ckb/use/` |
| 8 Maintenance | Health check without the source files. | `ckb/maintain/health.py` |

More detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Limits

- The registry covers the main clauses of EN 1992-1-1, EN 1993-1-1, EN 1993-1-8 and EN 1994-1-1.
  The EC3/EC4 objects and most of the added EC2 ones were written from the codes and have not been
  seen in a source or compared with an independent library: they are marked *not yet checked*.
  Interaction factors (EN 1993-1-1 6.3.3), M_cr, class 4 sections and second order analysis are
  not in it.
- The Word report is checked by reading it back with pandoc; it has not been opened in Word here.
- Straight-line calculations only: no iteration, interaction diagrams, tables or lookups.
- The Mathcad export is checked by reading it back and re-running it; it has not been opened in
  Mathcad Prime in this environment.
- A language model is used only to *read* (scans, `--vision` for PDF formulas), and what it reads
  must reproduce the printed result. That path is tested with a scripted model, not the live API.
- Python sources are run in a separate process to get their values. Only ingest files you would run.
- No approval workflow, ratings or shared usage statistics in the single-file version.

## Layout

```
ckb/data/            code registry: common.yaml (code-independent quantities, references), codes/*.yaml
ckb/                 expr, units, notation, ir, convert, distill, kb, use, maintain, cli
knowledge_base/      objects/ (design logic, YAML), evidence/ (JSON), python/ (generated), index.json
app/index.html       web calculator
inbox/, workspace/   your files and working output (not committed)
tests/               synthetic fixtures for every file type
docs/                architecture notes and the workshop material
```

Open-source building blocks: [`mcad2py`](https://pypi.org/project/mcad2py/) (Mathcad Prime to Python,
MIT) and [`structuralcodes`](https://github.com/fib-international/structuralcodes) (independent
reference, Apache-2.0).
