# Pitfalls database

A growing catalogue of the mistakes this toolchain is designed to catch —
both the mechanical ones (caught today by `src/qa/checks.py`) and the
engineering-judgment ones (for the future AI reviewer / human review).
Each entry: what goes wrong, why, and how the toolchain helps.

This is deliberately a living document — add a row every time a real tool
surprises someone.

## A. Unit & dimensional pitfalls

| # | Pitfall | Example | Toolchain help |
|---|---|---|---|
| A1 | Hidden unit conversion baked into a magic number | `sigma = M*1e6/(A*z)` silently converts kNm→Nmm | QA `unit-conversion-smell` flags `1e6`; units are display-only today — dimensional checking (pint) is the planned fix |
| A2 | Mixing MPa and kPa / N and kN across a formula | E in MPa, load in kN, area in mm² | No auto-catch yet; keep the unit column truthful, flagged as a top bottleneck |
| A3 | Angle in degrees vs radians | `tan(theta)` with theta in degrees | `sin/cos/tan` here are radians (sympy); document the input unit |
| A4 | Second moment of area units (mm⁴) vs deflection (mm) | `delta = 5qL⁴/384EI` with L in m | Keep L, I, E in a consistent set; A2 applies |

## B. Code-application pitfalls (Eurocode)

| # | Pitfall | Example | Toolchain help |
|---|---|---|---|
| B1 | Using recommended values instead of the National Annex | crack `k_3` = 3.4 vs NA value | National-annex system: `resolve(concept, "EN-XX")` overrides only the coefficient; `params` make code coefficients explicit |
| B2 | `f_ctm` formula valid only ≤ C50/60 | using `0.30·f_ck^(2/3)` for C60 | atom `notes` record the validity limit; AI reviewer target |
| B3 | Wrong strength class basis (cylinder vs cube) | `f_ck` cube used in a cylinder formula | synonym map distinguishes `f_ck` vs `f_ck_cube` |
| B4 | Effective tension area `A_c,eff` wrong (min of three) | crack width `h_c,eff` | keep the `min(...)` explicit in the formula so it is auditable |
| B5 | Long-term vs short-term modulus confusion | using `E_cm` where `E_cm(t)` / effective modulus needed | shared atoms `E_cm`, `E_cm_t` are distinct and named |
| B6 | Partial factors omitted or double-counted | `f_yd = f_yk/γ_s` applied twice | make γ an explicit input; AI reviewer target |

## C. Structural-logic pitfalls

| # | Pitfall | Example | Toolchain help |
|---|---|---|---|
| C1 | Checking the wrong criterion | comparing `w_k` to the wrong limit | checks are explicit `w_k <= w_max`; parametric study shows the governing case |
| C2 | Only the "obvious" load case checked | 1 case instead of the envelope | `ParametricStudy` runs all cases; `critical_index` finds the governing one |
| C3 | Sign / direction errors | hogging vs sagging moment | substituted display shows the numbers going in |
| C4 | Section assumed cracked when it is not (or vice versa) | modular ratio / lever arm | assumptions belong in the sheet's Scope section |

## D. Data-management pitfalls (what the toolchain structurally prevents)

| # | Pitfall | Toolchain help |
|---|---|---|
| D1 | Same formula copy-pasted into many sheets, then edited in one | atom library = single source of truth; `apply()` reuse; fingerprint flags re-implementations (`library-bypass`) |
| D2 | Two variables meaning the same thing (`E_c` vs `E_cm`) | synonym map + `find_synonym_clashes` flags them to merge |
| D3 | Duplicate tools built independently | Gatekeeper similarity + reuse breakdown before a tool is created |
| D4 | Stale hand-typed numbers in a report | calculation IS the visualization — numbers are always recomputed |
| D5 | Losing the machine-readable data when a PDF is passed around | self-contained in-page layer, reconstructable from the PDF alone |
| D6 | No traceability of who changed what | dashboard shows source, status and last editor (from git) |

## E. Reporting pitfalls

| # | Pitfall | Toolchain help |
|---|---|---|
| E1 | Formula rewritten unrecognizably by symbolic simplification | faithful display: `sqrt(28/t)` stays `√(28/t)` |
| E2 | Report too verbose / too terse for the audience | `detailed` vs `compact` render modes; tabular summary for many cases |
| E3 | Missing reviewer/approver trail on the sheet | branded header/footer cartouche: prepared / checked / approved |

---

**How to extend:** when a tool review turns up a new class of mistake, add
a row here and, if it is mechanically detectable, a check in
`src/qa/checks.py` with the same id in its message.
