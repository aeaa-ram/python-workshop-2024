# Clarifications needed — Simply Supported Steel Beam — quick check

The Grinder (heuristic) converted this sheet but could not confidently resolve the items below. Answer each, update the source or the generated tool, then re-grind.

## 1. `Beam!H1` — magic-number

Cell Beam!H1 = 1 has no adjacent label. What quantity is it?

> context: `1`

**Answer:** _..._

## 2. `Factors!B2` — magic-number

Cell Factors!B2 = 1 has no adjacent label. What quantity is it?

> context: `1`

**Answer:** _..._

## 3. `Beam!C9` — untranslatable-function

'Utilisation_check' at Beam!C9 uses ['IF'] which reads external/lookup data. Confirm the intended value or provide the underlying formula.

> context: `=IF(C7<=F4,1,0)`

**Answer:** _..._

## 4. `Bending_stress_sigma` — unit-scale-mismatch

'Bending_stress_sigma' is shown as 166.7 MPa but the formula evaluates to 166667 MPa (off by x1000 — a units slip).

> context: `display 166667 MPa, or reconcile the input units`

**Answer:** _..._
