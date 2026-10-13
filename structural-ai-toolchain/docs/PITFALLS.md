# Pitfalls database

A growing catalogue of the mistakes this toolchain is designed to catch —
the mechanical ones (caught by `src/qa/checks.py` and the master reviewer
in `src/qa/master_review.py`) and the engineering-judgment ones (the AI
review pass and the human checker).
Each entry: what goes wrong, why, and how the toolchain helps.

This is deliberately a living document — add a row every time a real tool
surprises someone.

## A. Unit & dimensional pitfalls

| # | Pitfall | Example | Toolchain help |
|---|---|---|---|
| A1 | Hidden unit conversion baked into a magic number | `sigma = 45e6/W` — 45e6 is a moment in Nmm | reviewer `hidden-unit-literal`: names the dimension the number must carry; deliberate conversions on labelled inputs (`M*1e6`, `(L/1000)**2`) are recognised as correct |
| A2 | Result computed in one unit, labelled another | `P_Rd` in N shown as "81656 kN" | reviewer `unit-scale-mismatch` → **fixed** (explicit conversion or relabel, whichever keeps the sheet consistent); unit-aware Mathcad sheets convert by construction |
| A3 | A units slip that flips a verdict | `P_Ed [kN] <= P_Rd [N]` reads OK, is NOT OK | reviewer `check-verdict-units` re-evaluates both sides in N, mm |
| A4 | Formula of the wrong dimension | a stress formula declared in kN; force + length | reviewer `dimension-mismatch`, `check-dimension-mismatch` (sympy dimensional analysis) |
| A5 | Empirical code formula fed in the wrong units | `k = 1 + √(200/d)` with d in m | reviewer `empirical-formula` (noted) / `empirical-formula-units` (warned when inputs are not N, mm, MPa) |
| A6 | Unit written inside a formula ignored | Mathcad `h − 0.003 m` computed as `h − 0.003` | unit symbols carry their scale: 100 mm − 0.003 m = 97 mm |
| A7 | Angle in degrees vs radians | `tan(theta)` with theta in degrees | `sin/cos/tan` here are radians (sympy); document the input unit |

## A′. Translation pitfalls (legacy file → Python)

| # | Pitfall | Example | Toolchain help |
|---|---|---|---|
| T1 | Rounding dropped | `ROUND(L/s, 0)` → 6.67 instead of 7 studs | Excel `ROUND/ROUNDUP/ROUNDDOWN/TRUNC/INT` and Mathcad `round/trunc` translated exactly |
| T2 | Conditional dropped or turned into a check | `IF(h/d>=4, 1, 0.2(h/d+1))` | becomes `Piecewise`; only `IF(cond,1,0)` flags become checks |
| T3 | Equality condition folded at parse time | `IF(k=1, …)` always false in sympy | conditions use `Eq(…)` / `Ne(…)` |
| T4 | Lost parentheses in nested sums | `0.2·(h/d + 1)` read as `0.2·h/d + 1` | sums/differences always keep their brackets in the Mathcad translator |
| T5 | Converted value silently differs from the original | wrong cell mapped | correspondence check against cached / printed values at printed precision; AI corrections only kept if the re-check improves |

## B. Code-application pitfalls (Eurocode)

| # | Pitfall | Example | Toolchain help |
|---|---|---|---|
| B1 | Using recommended values instead of the National Annex | crack `k_3` = 3.4 vs NA value | National-annex system: `resolve(concept, "EN-XX")` overrides only the coefficient; `params` make code coefficients explicit |
| B2 | `f_ctm` formula valid only ≤ C50/60 | using `0.30·f_ck^(2/3)` for C60 | atom `notes` record the validity limit; AI research notes validity limits per step |
| B3 | Wrong strength class basis (cylinder vs cube) | `f_ck` cube used in a cylinder formula | synonym map distinguishes `f_ck` vs `f_ck_cube` |
| B4 | Effective tension area `A_c,eff` wrong (min of three) | crack width `h_c,eff` | keep the `min(...)` explicit in the formula so it is auditable |
| B5 | Long-term vs short-term modulus confusion | using `E_cm` where `E_cm(t)` / effective modulus needed | shared atoms `E_cm`, `E_cm_t` are distinct and named |
| B6 | Partial factors omitted or double-counted | `f_yd = f_yk/γ_s` applied twice | make γ an explicit input; AI review target |
| B7 | A verification the code requires is missing | bending checked, lateral-torsional buckling not | AI research lists "steps the code requires that the sheet omits" in the reflection checklist |

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
