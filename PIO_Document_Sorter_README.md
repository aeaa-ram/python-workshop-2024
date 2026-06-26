# PIO Document Sorter

A single Python script (`PIO_Document_Sorter.py`) that replaces the
"PIO Document Control" Power Automate Desktop flow. You point it at the
SharePoint-synced folder of files and at your local *Document Control* folder,
and it builds the correctly-numbered folder tree, sorts the files into it, and
merges the drawings into one PDF.

It is **fully generic** – there are no package numbers, codes or user names
baked into the logic. Feed it any package (CD or CP, with or without sub-parts)
and it works out the structure from the source path and from the folders you
already have.

Everything is in **one file** so it is easy to copy onto a new machine.

---

## 1. Quick start

**On Windows, the easiest way:** double-click **`Run_PIO_Sorter.bat`**.
(The first run installs the PDF library automatically.)

Or run it yourself:

```bash
python PIO_Document_Sorter.py
```

Either way, two folder-picker windows appear:

1. **Source** – the synced revision folder that holds the files,
   e.g. `…\Certification\…\Definitive\CD-23\23.4\00_R00`
2. **Destination** – your local *Document Control* folder.

Then a small **confirmation window** shows what the script read (stage, package,
sub-part, revision, folder code). Fix anything wrong and click **Run**. A
summary window – with any **warnings at the top** – tells you exactly what
happened, and a `PIO_Sorter_log_*.txt` is written next to the destination.

### Command-line use (no pop-ups)

```bash
python PIO_Document_Sorter.py --source "…\00_R00" --dest "…\Document Control"
python PIO_Document_Sorter.py --source … --dest … --dry-run   # preview only
python PIO_Document_Sorter.py --source … --dest … --yes       # skip confirm window
```

---

## 2. Make a double-click `.exe`

A Windows `.exe` can only be built **on Windows** (that is why a prebuilt one
isn't in the repo – a build made here would be a Linux binary). To make one in a
single click:

> Double-click **`Build_Windows_EXE.bat`**.

It installs PyInstaller, builds the program, and leaves it at
`dist\PIO Document Sorter.exe`. Move that `.exe` anywhere and double-click it –
no Python needed. (Under the hood it just runs
`pyinstaller --onefile --windowed --name "PIO Document Sorter" PIO_Document_Sorter.py`.)

For most people **`Run_PIO_Sorter.bat` is enough** and you can skip building the
`.exe` entirely.

---

## 3. How the folder numbering works

The scheme is: a fixed 3-digit **stage** code, then a **2-digit package** code,
then a **2-digit sub-part**, then **one more digit per level** below:

```
400              Preliminaire        <-- the two stage codes are fixed
401              Definitive
 40101           CD-23               (stage 401 + the 2-digit package code 01)
  4010104        CD-23.4             (package + the 2-digit sub-part 04)
   40101040      R00                 (one more digit per level from here down)
    401010400    Reports
     4010104000  Original
     4010104001  Translated
    401010401    Drawings
     4010104010  Original
     4010104011  Combined
```

* A package **with** a sub-part (e.g. `CD-23.4`) gets the `4010104` level, so
  `R00` is `40101040`.
* A package **without** a sub-part (e.g. `CD-40`) skips that level, so `R00`
  sits directly under the package, e.g. `401120` – one level shorter.

The depth follows the real source folder, so the digit count is always right
(this is the "extra 0" fix – no level is ever added when there is no sub-part).

The fixed parts of the scheme live in the **CONFIG block** at the top of the
script and are easy to change:

```python
STAGE_CODES = {"CP": "400", "CD": "401"}   # Preliminaire / Definitive
PKG_SUFFIX_WIDTH = 2    # CD-23   -> a 2-digit package code, e.g. "01"
SUBPART_WIDTH    = 2    # CD-23.4 -> the sub-part number as 2 digits, "04"
```

### Where the 2-digit package code comes from (nothing is guessed)

There is **no** relationship between "23" and the package code "01" – so the
script never computes it. It comes from one of two places:

1. **Preferred – read from your folders.** It searches your *Document Control*
   for the folder you already named for that package – one whose name contains
   `(CD-23)` – and reads the `01` straight out of its number `40101`. It also
   reuses an existing sub-part folder (e.g. `4010104 CD-23.4`) if you have one,
   and builds the new revision inside it.
2. **First time for a package – type it once.** If no matching folder exists
   yet, the confirmation window shows an empty **Package code** box and a
   warning. Type the two digits once (e.g. `01`); the script then creates the
   `40101 CD-23` folder (under your `401 Definitive` folder if it has one), so
   next time step 1 finds it automatically and you never type it again.

The only arithmetic it does is the convention itself (stage code + package code
+ sub-part number + one digit per level). Everything package-specific is read
from your folders or entered by you.

---

## 4. How files are sorted

| File name contains…              | Goes to                          |
|----------------------------------|----------------------------------|
| `ODA-PLA`, `ODA-BOA`             | Drawings → Original              |
| `RPT`, `SPC`, `CER`, `FIT`, `MET`| Reports → Original               |
| any of those **and** ends `_EN`  | Reports → Translated             |
| `.xlsx` / `.xls`                 | Revision-folder root             |
| anything else                    | `_To_Sort_Manually` (and warned) |

All of this lives in the **CONFIG block at the top of the script** – the lists
`SORTING_RULES`, `ROOT_EXTENSIONS`, `TRANSLATED_SUFFIX`. If a submission puts
files in `_To_Sort_Manually`, add the keyword from those file names to
`SORTING_RULES` and they'll sort next time.

Nothing is ever deleted, and unrecognised files are **copied** into a clearly
named `_To_Sort_Manually` folder (with a `_READ_ME_unsorted.txt` listing them)
so they are never lost.

---

## 5. Warnings – so nothing slips through

The original flow's biggest pain was files quietly ending up in the wrong place.
Every run now produces a **WARNINGS list at the top of the summary** (and in the
log) covering:

* files that **matched no rule** (left in `_To_Sort_Manually`);
* files whose name **matched more than one category** (filed under the first,
  but flagged so you can check);
* drawings that **couldn't be merged** (kept in Drawings/Original, listed by
  name with the reason);
* a package code that was **typed manually** rather than detected;
* files that **already existed** and were left untouched (not overwritten).

If there are no warnings the summary says so in one line, and the result window
title shows the count (e.g. *"finished with 2 warning(s)"*).

---

## 6. The drawings merge ("some files cannot be merged")

The merge no longer fails the whole job when one PDF is bad. For each drawing it
tries to add the file; if a PDF is **encrypted or damaged** it is repaired when
possible (that's what `pikepdf` is for) and otherwise **skipped and listed in
the warnings**. You still get a combined PDF of the good drawings, plus the list
of files to merge by hand.

The merged file is named `PIO_<CD|CP>_<package>_Combined_Drawings.pdf` and a
`_1`, `_2`… suffix is added rather than overwriting an existing one.

> Install **pikepdf** (`pip install pikepdf`, or just run `Run_PIO_Sorter.bat`)
> rather than only `pypdf` – it is much better at the "cannot be merged" cases.

---

## 7. Original Power Automate flaws → how they're addressed

| Flaw in the old flow                         | Fix |
|----------------------------------------------|-----|
| Extra `0` on some packages                   | digit count follows the real depth, decided automatically |
| Package number hard-coded                    | read from the source path (`CD-27`, `CP-24`, …) |
| `nr40` / package code hard-coded             | 2-digit package code detected from your existing folders, or typed once – never computed |
| `Definitive`/`Preliminaire` not handled      | detected from the path → `CD`/`CP` |
| Revision `R00` hard-coded                    | read from the source folder name (`00_R00`, `01_R01A`, …) |
| Paths point at one user's directory          | nothing hard-coded – you pick both folders |
| Paths repeated in every sub-flow             | derived once from the two folders you pick |
| Running twice overrides/fails                | folders use *exist_ok*, existing files are skipped, no shared *Temporary* folder |
| Merge fails on bad PDFs                       | bad PDFs are repaired or skipped-and-listed, not fatal |
| Files land in "not sure where" with no notice| prominent warnings list + `_To_Sort_Manually` + editable `SORTING_RULES` |
| 4 separate sub-flows to copy                 | one file |

---

## 8. Files in this folder

| File | What it is |
|------|------------|
| `PIO_Document_Sorter.py`        | the whole tool (one file) |
| `Run_PIO_Sorter.bat`            | double-click to run it (no build) |
| `Build_Windows_EXE.bat`         | double-click to build the `.exe` |
| `requirements.txt`              | the optional PDF libraries |
| `test_pio_sorter.py`            | logic checks – `python test_pio_sorter.py` |

---

## 9. Notes

* Select the **revision folder that actually contains the files** (the `00_R00`
  level). If you select a folder that only has sub-folders, the script asks you
  to pick the right one.
* Drawings merge in **ascending** file-name order (sheet 1, 2, 3 …) and each
  page keeps its own rotation, so the combined PDF reads in the right order and
  the right way up. Set `DRAWINGS_SORT_DESCENDING = True` at the top of the
  script to flip it back.
* ProjectWise is intentionally out of scope – the submission folder is built
  self-contained so you can drag-and-drop it as before.
