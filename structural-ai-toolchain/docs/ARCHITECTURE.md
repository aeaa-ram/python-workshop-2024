# Architecture notes

How the code maps to the eight stages, the design decisions behind it, and how the concerns raised
before the workshop are handled. The picture of the stages is in
[`workshop/calculation-knowledge-architecture.html`](workshop/calculation-knowledge-architecture.html).

## Three decisions everything else rests on

**One formula tree.** Every formula, whatever file it came from, becomes the same small tree
(`ckb/expr.py`). The Python code block, the JavaScript in the web calculator, the Excel formula, the
equation in the report and the comparison between variants are all produced from that tree. There
is no second copy of the logic that could drift.

**One set of units inside.** Inside the knowledge base every number is in N, mm, MPa and radians.
Units exist only at the boundary: when a source is read and when a result is shown. This is what
makes `... * 1000 * d / 1000` in a spreadsheet and `200 mm / d` in Mathcad the same formula: once the
units are resolved, the conversion factors cancel and disappear (`expr.fold`).

**Nothing is trusted until arithmetic agrees.** A converted formula must reproduce the value the
source shows. A merged formula must contain every variant as a numerical special case. A unified
object must reproduce the source values and, where a reference exists, agree with it. A formula
transcribed by a model must reproduce the transcribed result. Each check is a number, not an opinion.

## Stage by stage

### 2 Conversion (`ckb/convert/`)

| Source | How | Check |
|---|---|---|
| Mathcad Prime `.mcdx` | `mcad2py` writes Python with `pint` units; that script goes through the Python converter. Labels are paired with equations by their position on the page; headings and clause references are kept. | Against the results Mathcad stored in the file. |
| Excel `.xlsx` | Own formula parser (Excel operator rules kept). Names from the label to the left, optional symbol cell, unit in brackets or the next cell, case from the column header, headings from the label column, clause from headings or a reference column. | Against Excel's cached value, cell by cell. |
| Python `.py`, Jupyter `.ipynb` | Python's own parser for the formulas; functions are inlined; the script is run in a separate process for the values. Unit hints in comments are read. | Tree evaluation against the run. |
| PDF | Printed quantities from character positions: subscripts are smaller and lower, results follow the last `=` on the baseline, units printed as fractions are reassembled. | Used as benchmarks. |
| Word `.docx` | Headings, text, tables and equation-editor content; a typed formula is accepted if it reproduces the printed result. | As above. |
| Scan, photo, handwriting | Vision model transcribes; `records.py` verifies. | Re-evaluation. |

Output per source: `workspace/converted/<id>.json` (statements) and `<id>.py` (the source as a script).

### 3 Decomposition (`ckb/distill/decompose.py`, `taxonomy.py`)

`Taxonomy.resolve` decides which quantity a name is: the symbol without separators, then the symbol
with a project qualifier dropped (`d_c` → `d`), then the words of the label. Ambiguous symbols are
decided by context. Two kinds of context are kept apart on purpose: *where a quantity is defined*
(its clause and heading) decides what a statement produces; *where it is used* decides its role in a
formula. The same reinforcement area is `A_s` in the bending formula and `A_sl` in the shear formula.

A match the value contradicts is rejected: a text result, a wrong dimension, or, for weak evidence,
a number far outside the usual range.

Formulas for *input* quantities (`d = h − cover − bar/2`) are project geometry and are not distilled.
Formulas of quantities the taxonomy does not know are listed in the run report.

### 4 Consolidation (`ckb/distill/consolidate.py`)

Instances with the same formula form a variant. Variants are merged by four rules, each of which
only ever generalises:

| One variant has | The other has | Unified | Recorded for the simpler variant |
|---|---|---|---|
| a number | a symbol | the symbol | "fixes γ_C = 1.5" |
| a factor | nothing | the factor | "per unit width: b_w = 1" (only for widths and dimensionless coefficients, and a missing width only if the source really works per unit width) |
| a term | nothing | the term | "no term k_1·σ_cp" |
| `max(X, bound)` | `X` | `max(X, bound)` | "omits the lower bound" |

A merge is accepted only if every variant, with its recorded differences applied, gives the same
number as the unified formula at sixty random points of the parameter range. Anything else is kept
apart as a disagreement, with the reason.

### 5 Objects, benchmarks, reference (`ckb/pipeline.py`, `ckb/distill/benchmarks.py`, `reference.py`)

- **Formula benchmarks**: the unified formula is evaluated with the numbers a source used. Where the
  source formula is a special case, the missing quantity is looked up in the same calculation run,
  so a simplification that matters for that case shows up as a difference with its reason.
- **Print benchmarks**: a printed value is recomputed through the chain of objects from the printed
  inputs and compared within the rounding of the print.
- **Reference**: the chain is evaluated from primary inputs and compared with `structuralcodes` at
  200 random points. Adapters are in `reference.py`; an object without one has no reference.
- **Status**: *consensus* (identical in two or more independent sources), *unified* (variants
  merged), *single source*, *disagreement*. A print of another source does not count as independent.

### 6 Repository (`ckb/kb/`)

An object is a short YAML file (`knowledge_base/objects/`), its benchmark list a JSON file beside it.
`KnowledgeBase.plan` resolves dependencies: asking for `V_Rd,c` pulls in `k`, `ρ_l`, `C_Rd,c`,
`v_min`, `V_Rd,c,min` and leaves the primary inputs. Any intermediate can be given instead.
`search.classify` places a new source against the objects.

### 7 Use (`ckb/use/`) and 8 Maintenance (`ckb/maintain/`)

See the README. The health check needs no source files, because each object carries its benchmarks.

## The concerns raised before the workshop

| Concern | What the MVP does |
|---|---|
| Variants for project-specific needs; a modified copy should not just look "wrong" | `python -m ckb check` classifies a fed-back file as existing, special case, extension, differs or new topic, formula by formula. In the calculator any intermediate value can be entered directly. |
| Complex calculations (several steps, checks) | Objects compose automatically; a calculation is a chain of objects with every step shown. Iterative logic, interaction diagrams and plots are not covered yet. |
| Non-coders extending a module | An object is a YAML file with a formula in plain arithmetic; a new quantity is an entry in `taxonomy.yaml`. Everything else is regenerated. An editing screen is not built. |
| Immediate fixes before an owner reviews | No approval gate: objects are published with their status. An edit without a new version is caught by the health check. |
| Small granular pieces, not tools | One object per quantity; larger calculations are resolved, not written. |
| Quality signal from use | Each run from the command line is logged (`workspace/usage.jsonl`) and counted in the health check. Ratings and comments are not built. |
| Warnings and limitations for juniors | Notes per quantity in the taxonomy; warnings for single-source, disagreement and reference differences; range warnings on inputs. They appear in every calculation. |
| Tag everything, test the logic with it; repeated logic becomes valuable | Every statement keeps its label, clause, heading, case and location; every recognised value is a benchmark. Eighty-odd repetitions of `k` are eighty-odd confirmations. |
| Deterministic source for assistants | `python -m ckb tools` gives tool definitions; `toolschema.call` returns the value with every step and clause. |
| Health checks when things change | `python -m ckb health`. |
| Two-way interaction, Excel included | Excel calculator with native formulas out; any workbook back in. |
| Objects referencing objects | That is how every chain works; circular references are refused. |
| Provenance without copying sources | The knowledge base holds formulas, numbers and locations, not files. `--anonymous` removes names. |
| Several languages | Symbols are language-independent; label words in `taxonomy.yaml` can be listed in any language. Only English is seeded. |
| Scope | One code and one material in the seed. The mechanism does not depend on it. |

## What is not built

An approval workflow and roles, version history beyond a fingerprint per object, a server or
database, SharePoint retrieval, ratings and comments, design guides generated from reports, and
national-annex branches (the taxonomy has a `branch` field; one branch is seeded).
