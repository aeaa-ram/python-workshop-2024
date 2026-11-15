# Architecture notes

How the code maps to the stages, the decisions behind it, and how the concerns raised before the
workshop are handled. The picture of the stages is in
[`workshop/unified-design-logic-architecture.html`](workshop/unified-design-logic-architecture.html).

## Four decisions everything else rests on

**The code is the baseline, the sources are evidence.** Most spreadsheets write f_cd = f_ck/γ_C;
the code writes α_cc·f_ck/γ_C. If the knowledge base distilled only the sources, it would keep
the simplification. So the expressions come from the codes (`ckb/data/codes/*.yaml`). The
sources then show how the code is applied in practice: which simplifications are made, how often,
whether each is on the safe side, and which values are used. An object no source has applied
yet is still published, as ◐ *not yet checked*.

**One formula tree.** Every formula becomes the same small tree (`ckb/expr.py`). The Python code
block (`to_python`), the web calculator (`to_js`), the Excel formula (`to_excel`), the Mathcad
regions (`mathcad_export.to_xml`) and the report equations (`to_mathml`) are all printed from it.
There is no second copy of the logic that could drift. Every output carries the object's version,
and `ckb verify` reads it back.

**One set of units inside.** Every number is in N, mm, MPa and radians. Units exist only at the
boundary: when a source is read and when a result is shown. That is why `... *1000*d/1000` in a
spreadsheet and `200 mm/d` in Mathcad are the same formula once read. Display units and decimals
(`ckb/use/style.py`) never touch the logic.

**Design logic and evidence are stored apart.** `knowledge_base/objects/<id>.yaml` holds the
formula, clause, unit, conditions, design background and the values a code fixes. That is all a
calculation, report, code block, workbook or worksheet ever uses.
`knowledge_base/evidence/<id>.json` holds sources, variants, benchmarks, the reference check and
the confidence. It is shown on the Status tab and by `ckb status`, never in a calculation.

## The registry (`ckb/data/`, `ckb/distill/taxonomy.py`)

`common.yaml` lists the code-independent quantities (geometry, materials, actions) with their
spellings and usual units. It also lists the references cited in the design background. Each
`codes/<code>.yaml` lists that code's chapters (titles and search keywords) and its quantities:

```yaml
- id: f_cd
  formula: alpha_cc * f_ck / gamma_C
  clause: 3.1.6(1)
  eq: (3.15)
  sense: resistance
  background:
    - kind: pitfall
      text: α_cc is a Nationally Determined Parameter. Spreadsheets often write f_ck/γ_C ...
      refs: ["EN1992-1-1:3.1.6(1)"]
```

Coefficients carry their recommended value, NDP flag and choices (k_2 = 0.5 bending, 1.0 pure
tension). Objects carry their conditions of application (`checks`), the alternatives the code
permits (z = 0.9 d), a `basis` (code, standard mechanics, definition) and hints for reading
ambiguous symbols in context.

When a later code defines a quantity, the registry compares its expression with the objects it
already has:

| The later code writes | Stored as |
|---|---|
| the same expression (EN 1994-1-1 f_sd = f_yk/γ_S) | the existing object, with the other name as an alias |
| a special case (EN 1994-1-1 f_cd = f_ck/γ_C) | the existing object, plus the values that code fixes (α_cc = 1), applied whenever that code's objects use it |
| a declared reuse (`same_as`) | the existing object |
| something else | a new object of that code |

So no expression is stored twice, and N_pl,Rd of EN 1994-1-1 uses the EN 1992-1-1 f_cd with α_cc = 1
automatically. An object can also be an *instance* of another: `of: k, bind: {d: d_eff_p}` takes the
expression of k with the punching effective depth (and records the link on k), so a correction to k
reaches punching too. The registry now holds EN 1992-1-1, EN 1993-1-1, EN 1993-1-8 and EN 1994-1-1;
objects no source has used yet are published as *not yet checked*.

## Stage by stage

### 2 Conversion (`ckb/convert/`)

| Source | How | Check |
|---|---|---|
| Mathcad Prime `.mcdx` | `mcad2py` writes Python with `pint` units, which goes through the Python converter. Labels are paired with equations by position; headings and clauses are kept. | Against the results Mathcad stored in the file. |
| Excel `.xlsx` | Own formula parser with Excel's operator rules, and defined names (named ranges). Names come from the label column, an optional symbol cell or the defined name. Units come from brackets or the next cell, cases from column headers, clauses from headings. | Against Excel's cached values, cell by cell. |
| Python, Jupyter | Python's own parser; functions inlined; the script run in a separate process for the values; unit hints in comments. | Tree evaluation against the run. |
| PDF | Printed quantities from character positions (subscripts, fractions, last `=` on the line). | Benchmarks. |
| Word | Headings, text, tables and equation-editor content. | A typed formula must reproduce the printed result. |
| Scans | A vision model transcribes; `records.py` verifies. | Re-evaluation. |

Headings that name one of several parallel calculations ("Phase 2", "Load case 3", "Span 2") become
the case of the statements under them (`notation.case_of`).

### 3 Decomposition (`ckb/distill/decompose.py`)

`Taxonomy.resolve` decides which quantity a name is: the symbol without separators, the symbol
with a project qualifier dropped, then the words of the label. Context decides ambiguous symbols:
the same reinforcement area is `A_s` in bending and `A_sl` in shear. Formulas are rewritten in N,
mm, MPa with the registry's symbols, and per-metre working (`*1000*d/1000`) is recognised as
b_w = 1.

### 4 Against the code (`ckb/distill/baseline.py`)

Every source formula of a quantity with a code expression is put in one group:

| Group | Meaning |
|---|---|
| as code | the code expression however written (checked numerically at random points) |
| alternative | an alternative the code permits |
| simplified | a special case: a recommended value typed in, a factor or term left out, a bound omitted, per unit width. Each difference is listed. |
| differs | not a special case: another method, a National Annex, another edition, or an error |
| project-specific | uses quantities the registry does not know |

Before comparing, derived quantities are expanded only where the other side writes them out, so
f_cd matches α_cc·f_ck/γ_C but η is not forced into a formula that simply has none. Symbols that
can be read two ways are tried both ways (A_s for A_sl). A formula that matches another quantity's
code expression is moved there (0.9·d in a shear sheet is the shear lever arm z_V, not the bending
z).

Before a difference is reported it is investigated (`investigate.py`): an input read from another
calculation in the file, a width between the two results (per metre against full width), a unit
factor on one input, one input with another value. Each hypothesis is tested by recalculating. An
explained difference keeps its explanation; a lesson (per-metre working, units) becomes design
background of the object. An unexplained one becomes a question for an engineer
(`workspace/questions.yaml`, `ckb answer`), whose answer is applied in the next build. Values are
looked up in the same calculation run first: same column, then same case and section, because one
spreadsheet column can hold two calculations.

For each simplification, `explain` says why it is reasonable *in that case* (σ_cp = 0 there, η = 1
for f_ck ≤ 50, the recommended α_cc = 1). `effect` says whether the source's result is on the safe
or unsafe side, from the object's sense (resistance or action effect).

Quantities without a code expression are merged among the sources by generalisation
(`consolidate.py`). A merge is accepted only if every variant is numerically a special case of the
result.

### 5 Objects, benchmarks, reference, confidence

- **Formula benchmarks**: the code expression evaluated with the numbers the source used. Values the
  source leaves out are taken from the same calculation run, so a simplification that matters in a
  case shows up there with its reason. A result off by more than a factor of 20 is an input mix-up
  (units, a full width against a strip), so it is marked not comparable rather than different.
- **Print benchmarks**: a printed value recomputed from the printed inputs, within the rounding of
  the print.
- **Reference**: the object's chain against `structuralcodes` at 200 random points (`reference.py`).
- **Confidence**: *checked* when the logic is the code's own and an independent check agrees (the
  reference library or reproduced source values); *not yet checked* when nothing has confirmed it
  yet; *review needed* when a check disagrees, or the logic rests on sources alone with one source
  or a disagreement.

### 6 Repository and search (`ckb/kb/`)

`KnowledgeBase.plan` resolves dependencies: asking for V_Rd,c pulls in k, ρ_l, C_Rd,c, v_min and
V_Rd,c,min, applies the values the object's code fixes, and leaves the primary inputs. Any
intermediate can be given instead. `checks_for` evaluates every condition in the chain, deriving
what a condition needs (f_cd for σ_cp ≤ 0.2 f_cd).

Search (`search.py`) is a word search over name, symbol, chapter titles and keywords, code title,
registry words and, with less weight, the design background. Every word must match, and a word may
be the start of a longer one. The web calculator runs the same index with the same rules.

### 7 Use (`ckb/use/`)

| Module | Output |
|---|---|
| `calc.py` | `run`: inputs in engineering units, every step, conditions, utilisation |
| `report.py` | templates over many cases; calc, table, chart, text blocks; static HTML; PDF by headless Chromium, with bookmarks |
| `report_docx.py` | the same report as Word, equations as native Office Math (`expr.to_omml`) |
| `webapp.py` | the single-file web calculator |
| `excel_bridge.py` | Excel calculator with named ranges; read back and verified with LibreOffice |
| `mathcad_export.py` | Mathcad Prime worksheet (math50 XML in an .mcdx package); verified by reading it back |
| `verify.py` | `ckb verify` for xlsx, mcdx, py, html and pdf |
| `style.py` | decimals, significant digits, display units |
| `toolschema.py` | tool definitions for an AI assistant |

### 8 Maintenance (`ckb/maintain/health.py`)

Needs no source files. It re-runs every stored benchmark, compares each generated code block and
checks it carries the current version, re-checks the reference and the dependencies, and catches a
formula edited without a new version.

## The concerns raised before the workshop

| Concern | What it does |
|---|---|
| Variants for project-specific needs; a modified copy should not look "wrong" | `ckb check` classifies a fed-back file formula by formula: as code, simplified, differs, new. In every calculator any intermediate can be entered directly. |
| Complex calculations | Objects compose; a report or calculator shows every step. Iteration, interaction diagrams and lookups are not covered. |
| Non-coders extending a module | An object is a few lines of YAML in the registry; everything else is regenerated. No editing screen yet. |
| Fixes before an owner reviews | No approval gate; confidence is visible on every object, and an edit without a new version is caught. |
| Small granular pieces | One object per quantity; larger calculations are resolved. |
| Quality signal from use | Uses from the command line are logged (`workspace/usage.jsonl`). Ratings need a hosted version. |
| Warnings and limitations for juniors | Design background per object with sources; conditions evaluated in every calculation; out-of-range inputs flagged; NDPs marked. |
| Tag everything; repeated logic becomes valuable | Every source value is a benchmark; practice (γ_C = 1.3775 72 times) is summarised per object. |
| Deterministic source for assistants | `ckb tools`; `toolschema.call` returns value, steps, conditions and version. |
| Health checks | `ckb health`. |
| Two-way with Excel | Calculator out with named ranges; any workbook back in (`ckb check`); a report from a workbook's inputs (`ckb report --from-excel`). |
| Several codes | Linked registry, no duplicated expressions. |
| Provenance without copying sources | Formulas, numbers and locations only; `--anonymous` removes names. |

## What is not built

An approval workflow and roles, version history beyond a fingerprint per object, a server, shared
ratings and usage, an AI search agent, SharePoint retrieval, and National Annex branches (an NDP is
marked, and its value can be changed per calculation, but there are no stored annex sets).
