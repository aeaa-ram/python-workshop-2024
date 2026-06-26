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

## 3. How the folder numbering works (and the "extra 0" fix)

Each folder's number is its parent's number **plus one digit per level**. The
depth – and therefore the number of digits – follows the real folder structure:

```
401            Definitive                     (400 = Preliminaire)
 4011          Foundations_Piers (CD-23)
  40113        CD-23.4         <-- this level ONLY exists when there are sub-parts
   401130      R00
    4011300    Reports
     40113000  Original
     40113001  Translated
    4011301    Drawings
     40113010  Original
     40113011  Combined
```

* A package **with** a sub-part (e.g. `CD-23.4`) gets the extra `40113` level,
  so `R00` is `401130` (6 digits).
* A package **without** a sub-part (e.g. `CD-27`) skips that level, so `R00` is
  `40150` (5 digits).

The old flow used a fixed `nr40`, so it added that extra digit even when there
was no sub-part. The script now **decides automatically** from the source path,
so the digit count is always right.

### Where the base code comes from (no formula, nothing hard-coded)

1. **Preferred – read from your folders.** It searches your *Document Control*
   for the folder you already named for that package – e.g. one whose name
   contains `(CD-23)`, or a sub-part folder containing `CD-23.4` – and reads the
   code from it. It also drops the new revision folder *inside* that folder.
2. **First time for a package – type it once.** If no matching folder exists
   yet, the confirmation window shows an empty **Base folder code** box and a
   warning. Type the code once; from then on the folder exists, so step 1 finds
   it automatically. (The numbers `400`/`401`, the package digit, etc. are part
   of *your* scheme – the script never guesses them.)

The only arithmetic it ever does is the convention itself: a brand-new sub-part
`.N` is the `(N-1)`-th child of its package folder. Everything else is read or
entered.

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
* a base code that was **typed manually** rather than detected;
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
| `nr40` / base code hard-coded                | detected from your existing folders, or typed once – never computed |
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
* The merge order matches the old flow (file name, descending). Change
  `DRAWINGS_SORT_DESCENDING` at the top of the script to flip it.
* ProjectWise is intentionally out of scope – the submission folder is built
  self-contained so you can drag-and-drop it as before.
