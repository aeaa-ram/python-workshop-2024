# PIO Document Sorter

A single Python script (`PIO_Document_Sorter.py`) that replaces the
"PIO Document Control" Power Automate Desktop flow. You point it at the
SharePoint-synced folder of files and at your local *Document Control* folder,
and it builds the correctly-numbered folder tree, sorts the files into it, and
merges the drawings into one PDF.

Everything is in **one file** so it is easy to copy onto a new machine.

---

## 1. Quick start (no install, for testing)

```bash
python PIO_Document_Sorter.py
```

Two folder-picker windows appear:

1. **Source** – the synced revision folder that holds the files,
   e.g. `…\Certification\…\Definitive\CD-23\23.4\00_R00`
2. **Destination** – your local *Document Control* folder.

Then a small **confirmation window** shows what the script read from the path
(stage, package, sub-part, revision, folder code). Fix anything that is wrong
and click **Run**. A summary window tells you exactly what happened, and a
`PIO_Sorter_log_*.txt` is written next to the destination.

For the drawings merge you need one PDF library:

```bash
pip install pikepdf      # recommended (repairs broken/encrypted PDFs)
#  or, if pikepdf won't install on your machine:
pip install pypdf
```

The script still runs without them – it just skips the merge and tells you.

### Command-line use (no pop-ups)

```bash
python PIO_Document_Sorter.py --source "…\00_R00" --dest "…\Document Control"
python PIO_Document_Sorter.py --source … --dest … --dry-run   # preview only
python PIO_Document_Sorter.py --source … --dest … --yes       # skip confirm window
```

---

## 2. Build the double-click `.exe`

So you never need Python open:

```bash
pip install pyinstaller pikepdf
pyinstaller --onefile --windowed --name "PIO Document Sorter" PIO_Document_Sorter.py
```

The result is `dist\PIO Document Sorter.exe`. Double-click it and you get the
same two folder pickers. (`--windowed` hides the console; drop it if you want to
see the text output too.)

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

The old flow used a hard-coded `nr40`, so it added that extra digit even when
there was no sub-part. The script now **decides automatically** from the source
path, so the digit count is always right.

### Where the base code comes from

1. **Preferred:** it searches your *Document Control* folder for the package you
   already named – e.g. `4011 Foundations_Piers (CD-23)` – and reads `4011` from
   it. It also drops the new revision folder *inside* that existing folder.
2. **Fallback:** if it can't find it, it computes the code
   (`CD-23 → 4011`, `CD-24 → 4012`, …, i.e. `last digit = number − 22`), **warns
   you**, and puts the revision folder at the destination root so you can move
   it. You can always correct the code in the confirmation window.

> The fallback formula assumes packages run CD-23, CD-24, … in order. If your
> real numbering is different (it stops being a single digit above CD-31), just
> make sure the package folder is named with its code in the destination – then
> detection (option 1) is used and the formula is never needed.

---

## 4. How files are sorted

| File name contains…              | Goes to                          |
|----------------------------------|----------------------------------|
| `ODA-PLA`, `ODA-BOA`             | Drawings → Original              |
| `RPT`, `SPC`, `CER`, `FIT`, `MET`| Reports → Original               |
| any of those **and** ends `_EN`  | Reports → Translated             |
| `.xlsx` / `.xls`                 | Revision-folder root             |
| anything else                    | `_To_Sort_Manually` (and listed) |

Nothing is ever deleted, and unrecognised files are **copied** into a clearly
named `_To_Sort_Manually` folder and listed in the summary so you can handle
them – they are never lost or silently dropped.

All of this lives in the **CONFIG block at the top of the script** – the lists
`SORTING_RULES`, `ROOT_EXTENSIONS`, `TRANSLATED_SUFFIX`, etc. If a submission
puts lots of files in `_To_Sort_Manually`, add the keyword from those file names
to `SORTING_RULES` and they'll sort next time.

---

## 5. The drawings merge ("some files cannot be merged")

The merge no longer fails the whole job when one PDF is bad. For each drawing it
tries to add the file; if a PDF is **encrypted or damaged** it is repaired when
possible (that's what `pikepdf` is for) and otherwise **skipped and listed by
name** in the summary. You still get a combined PDF of the good drawings, plus a
short list of the files to merge by hand.

The merged file is named `PIO_<CD|CP>_<package>_Combined_Drawings.pdf` and a
`_1`, `_2`… suffix is added rather than overwriting an existing one.

---

## 6. Original Power Automate flaws → how they're addressed

| Flaw in the old flow                         | Fix |
|----------------------------------------------|-----|
| Extra `0` on some packages                   | digit count follows the real depth, decided automatically |
| Package number `27` hard-coded               | read from the source path (`CD-27`) |
| `nr40` (e.g. `15`) hard-coded                | detected from your existing folders, or computed + confirmable |
| `Definitive`/`Preliminaire` not handled      | detected from the path → `CD`/`CP` |
| Revision `R00` hard-coded                    | read from the source folder name (`00_R00`, `01_R01A`, …) |
| Paths point at one user's directory          | nothing hard-coded – you pick both folders |
| Paths repeated in every sub-flow             | derived once from the two folders you pick |
| Running twice overrides/fails                | folders use *exist_ok*, existing files are skipped, no shared *Temporary* folder |
| Merge fails on bad PDFs                       | bad PDFs are repaired or skipped-and-listed, not fatal |
| Lots of files land in "not sure where"       | editable `SORTING_RULES`; leftovers kept and listed, not dropped |
| 4 separate sub-flows to copy                 | one file |

---

## 7. Notes / things to check

* Select the **revision folder that actually contains the files** (the `00_R00`
  level). If you select a folder that only has sub-folders, the script asks you
  to pick the right one.
* The merge order matches the old flow (file name, descending). Change
  `DRAWINGS_SORT_DESCENDING` at the top of the script to flip it.
* ProjectWise is intentionally out of scope – the submission folder is built
  self-contained so you can drag-and-drop it as before.
