---
# ── Machine-readable front matter (consumed by the Knowledge Graph) ──
tool_id: <slug, e.g. crack_width_ec2>          # must match folder name
title: "<Human title, e.g. Crack Width Verification (EN 1992-1-1)>"
category: <concrete|steel|timber|geotech|loading|general>
source_file: <original legacy file name>
source_format: <mcdx|xlsx|xlsm|csv|py|ipynb|native>
reference: "<design code clauses, e.g. EN 1992-1-1:2004 §7.3.4>"
status: <converted-unreviewed|in-review|approved|deprecated>
reviewed_by: <name or null>
converted: <YYYY-MM-DD>
revision: '<x.y>'
---

# <Tool Title>

| Project | Reference | Author | Revision | Date |
|---|---|---|---|---|
| … | … | … | … | … |

One-paragraph purpose statement: what the tool verifies/designs, for which
element type, under which code.

## 1. Scope & Assumptions

- Validity range of every input (e.g. `20 ≤ f_ck ≤ 90 MPa`)
- Modelling assumptions (cracked section, linear elastic, …)
- What the tool does NOT cover

## 2. Input Parameters

| Symbol | Value | Unit | Description |
|---|---|---|---|
| $b$ | … | mm | … |

## 3. Calculation

Every step is rendered by the Output Engine in the three-line Mathcad
style — symbolic, substituted, result — from the paired Python file.
**Never hand-edit numbers in this file**; regenerate it.

$$
\begin{aligned}
w_k &= s_{r,max} \cdot (\varepsilon_{sm} - \varepsilon_{cm}) \\
&= 327.1 \cdot 0.0005524 \\
&= \mathbf{0.181}\ \mathrm{mm}
\end{aligned}
$$

## 4. Verification

> ✅ **PASS** — Crack width within allowable limit
>
> $$ w_k = 0.181\ \mathrm{mm} \le w_{max} = 0.3\ \mathrm{mm} $$

## 5. Conversion Warnings

Anything The Grinder could not translate automatically, kept visible until
a reviewer resolves it.

## 6. Revision History

| Rev | Date | Author | Change |
|---|---|---|---|
| 0.1 | YYYY-MM-DD | The Grinder | Automated conversion from `<source>` |
