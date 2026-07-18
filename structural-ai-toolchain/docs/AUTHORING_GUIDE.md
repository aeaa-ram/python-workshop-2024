# Authoring Guide — creating NEW tools from scratch

This is the human workflow for building a tool directly on the toolchain
(no legacy file, no AI required). Converted and native tools end up
identical in `/repository`, so everything downstream (gatekeeper,
reports, QA) works the same.

## The golden rules

1. **Never re-type a shared formula.** If the math exists as a library
   atom (`python main.py atoms` lists them), you `sheet.apply()` it.
   The E-modulus-in-time equation exists *once* in `src/library` and
   feeds every tool that needs it. The QA checker flags violations
   (`library-bypass`).
2. **Check before you build.** `python main.py ask "<your idea>"` asks
   the Gatekeeper whether a similar tool already exists.
3. **The calculation is the visualization.** You never write display
   code — declaring the step *is* declaring its rendering.
4. **Reports are generated, never edited.** Change the `.py`, re-render.

## Step-by-step

```bash
# 1. Is it new?
python main.py ask "Punching shear check for flat slabs" \
    --variables v_Ed,v_Rd_c,d,u_1

# 2. Scaffold
python main.py new "Punching Shear Check (EN 1992-1-1 6.4)"
# -> repository/punching_shear_check_en_1992_1_1_6_4/<slug>.py
```

Edit the generated `build_sheet()`:

```python
def build_sheet() -> CalcSheet:
    sheet = CalcSheet(
        title="Punching Shear Check (EN 1992-1-1 6.4)",
        description="Punching shear verification at the first control "
                    "perimeter of a flat slab.",
        reference="EN 1992-1-1:2004 §6.4",
        author="Your Name",
    )

    sheet.section("Input Parameters")
    sheet.define("d", 260, unit="mm", description="Mean effective depth")
    sheet.define("E_s", 200000, unit="MPa", description="Steel modulus")
    sheet.define("E_cm", 33000, unit="MPa", description="Concrete modulus")

    sheet.section("Calculation")
    # Shared math -> library atom (single source of truth):
    sheet.apply("alpha_e", "ec2.general.alpha_e")
    # Atom symbols can be remapped to your sheet's names:
    # sheet.apply("E_c_eff", "ec2.concrete.E_cm_t",
    #             subs={"f_cm_t": "f_cm_28"})
    # Genuinely new logic -> calc(), with unit and description:
    sheet.calc("u_1", "2*pi*(c/2 + 2*d)", unit="mm",
               description="First control perimeter")

    sheet.section("Verification")
    sheet.check("v_Ed <= v_Rd_c", "Punching resistance without shear rebar")
    return sheet
```

API notes:

- `define(name, value, unit, description, latex=None)` — inputs.
  `latex` overrides the symbol display, e.g. `latex=r"\varepsilon_{sm}"`.
- `calc(name, expression, ...)` — expression is a plain string using
  previously defined names plus `sqrt/min/max/abs/exp/log/sin/cos/tan/pi`.
- `apply(name, atom_id, subs={...}, jurisdiction="EN")` — reuse a library
  atom; `subs` maps the atom's canonical symbols to your names;
  `jurisdiction` selects the National Annex (auto-injects its coefficients,
  e.g. `jurisdiction="EN-GB"`).
- `check("lhs <= rhs", description)` — pass/fail verdicts (render as
  OK / NOT OK, green / red).
- `section(...)` / `text(...)` — report structure and prose.

## Variable naming convention (drives the LaTeX automatically)

- `_` starts a subscript: `E_cm` → `E_{cm}`, `k_1` → `k_{1}`.
- `__` (double underscore) or a further `_` = a comma in the subscript:
  `f_c__k` → `f_{c,k}`, `sigma_Rd__max` → `σ_{Rd,max}`.
- Spell greek out: `phi` → `φ`, `epsilon_sm` → `ε_{sm}`, `rho_p__eff`
  → `ρ_{p,eff}`. Names stay valid identifiers, so the maths never breaks.
- Use one name per quantity. `E_c`/`E_cm` both mean the concrete modulus —
  QA flags the clash (`synonym-clash`) so you merge them.

## Reporting: modes, branding, parametric

- Detail level: `render <slug> --mode detailed` (Mathcad three-line) or
  `--mode compact` (`E_cm = 30464 MPa`).
- Company template: `Branding(logo_path="assets/logo.svg", ...)` and
  `ReportMeta(prepared_by=..., checked_by=..., approved_by=..., project=...)`
  passed to `render_all(..., branding=, meta=)`.
- Many load cases → one table: `ParametricStudy(sheet, cases, labels)` with
  `.summary_markdown(result_vars=[...])`; `.critical_index()` gives the
  governing case to show in full detail.

```bash
# 3. Register (manifest + standardized doc) and QA
python main.py register punching_shear_check_en_1992_1_1_6_4
python main.py qa punching_shear_check_en_1992_1_1_6_4
python main.py qa punching_shear_check_en_1992_1_1_6_4 --prompt  # AI review prompt

# 4. Render the A4 report (bookmarked PDF with embedded JSON)
python main.py render punching_shear_check_en_1992_1_1_6_4 --pdf

# 5. Commit — review happens in the merge request; status moves
#    native-unreviewed -> in-review -> approved.
```

## Promoting a formula to a library atom

When review finds that a `calc()` step is genuinely reusable (used or
usable by ≥2 tools), move it to `src/library/atoms_*.py`:

```python
register(Atom(
    atom_id="ec2.shear.v_min",
    result="v_min",
    expression="0.035*k**1.5*sqrt(f_ck)",
    clause="EN 1992-1-1:2004 §6.2.2(1)",
    description="Minimum shear resistance",
    units={"v_min": "MPa", "k": "-", "f_ck": "MPa"},
))
```

Then replace the `calc()` in your tool with `apply()`. The knowledge
graph fingerprints every atom, so future ingested legacy sheets that
contain the same structure (even with different variable names) are
recognized automatically.

## Calling atoms outside tools

```python
from src.library import custom
custom.E_cm_t(E_cm=33000, f_cm_t=30.3, f_cm=38)   # 30832.7 MPa
custom["ec2.concrete.beta_cc_t"](s_cem=0.25, t=7)  # 0.7788
```

The same registry will back the planned Excel bridge
(`=CUSTOM.E_CM_T(...)` via xlwings/PyXLL), so atoms are directly
callable from spreadsheets too.
