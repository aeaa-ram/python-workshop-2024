# Structural AI Toolchain — 1-page starter

> Everything runs locally. From `structural-ai-toolchain/`, once: `pip install -r requirements.txt`.

### ① Put a legacy sheet IN  →  get a tool OUT
```
python main.py gui                     # window: pick file → Investigate → Create
# or, straight from the terminal:
python main.py grind path/to/your_sheet.xlsx      # .xlsx .xlsm .csv .ipynb .py
```
Tidy sheets convert exactly; **messy sheets go through the AI Grinder** (reads scattered
tables, multi-tab, formulas) and, if unsure, **asks you questions** instead of failing.

### ② If it asks questions  →  answer them
```
repository/<your-tool>/CLARIFICATIONS.md     # e.g. "Cell H1 = 1.0 has no label — what is it?"
```
Fix the sheet (or the generated tool), then re-grind. Status shows `needs-clarification`.

### ③ See the result  →  the report
```
python main.py render <your-tool> --pdf              # detailed Mathcad-style
python main.py render <your-tool> --pdf --mode compact   # just the answers
```
→ `repository/<your-tool>/reports/<your-tool>.pdf` — branded A4, logo, OK / NOT OK, bookmarks.

### ④ Print / share  →  it's a normal PDF
Open the PDF, **Ctrl+P**. It also hides a machine-readable copy *inside itself*, so later:
```
python -c "from src.output_engine import reconstruct_from_pdf as r; print(r('file.pdf'))"
```

### ⑤ Change the inputs  →  edit one file, re-render
```
repository/<your-tool>/<your-tool>.py    # edit the numbers in build_sheet(), then render again
```
Every number in the report recomputes itself — never hand-typed.

### ⑥ Build a NEW tool from scratch (no legacy file)
```
python main.py new "Punching Shear Check (EN 1992-1-1 6.4)"   # makes a starter file
#  → edit build_sheet(),  then:
python main.py register <slug>      # make its doc + manifest
python main.py render   <slug> --pdf
```

### ⑦ Find a formula to reuse  →  don't retype code
```
python main.py atoms --search "crack width"     # search bar
python main.py atoms --tree                      # drill down: country → code → chapter → clause
python -c "from src.library import custom; print(custom.E_cm(f_cm=38))"   # call any formula
```

### ⑧ See EVERYTHING (for non-coders)  →  the dashboard
```
python main.py dashboard      # → repository/dashboard.html  (open in a browser)
```
What's hosted, what's recycled, who edited it, and the whole formula library — searchable.

---

**Where things live:**  `repository/` = your tools + reports (the source of truth) ·
`src/library/` = shared formulas (atoms) · `docs/` = the deeper guides.
**Want the full run once?** `python main.py demo`.
**Not sure a tool exists?** `python main.py ask "what you want to build"`.
