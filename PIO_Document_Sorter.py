#!/usr/bin/env python3
"""
PIO Document Sorter
===================

A single, readable Python replacement for the "PIO Document Control" Power
Automate Desktop flow.

What it does
------------
1. You pick the SOURCE folder - the SharePoint-synced revision folder that
   holds the files, e.g.  ...\\Definitive\\CD-23\\23.4\\00_R00
2. You pick the DESTINATION root - e.g. your local "Document Control" folder.
3. Everything else is read automatically from the source path and from the
   folders you already have:
       * Stage    -> "Definitive" = CD,   "Preliminaire" = CP
       * Package  -> CD-23 / CP-24 ...
       * Sub-part -> 23.4  (only when the package actually has sub-parts)
       * Revision -> R00 / R01 / R00A ...  (taken from the source folder name)
4. It builds the correctly-numbered folder tree (no extra "0"), copies and
   sorts the files by their naming convention, and merges the drawings into a
   single PDF - skipping (and reporting) any PDF that cannot be merged instead
   of failing the whole job.

Design notes / how the old flaws are fixed
------------------------------------------
* Extra "0":        the numbering depth follows the real folder depth, so a
                    package WITH a sub-part gets one extra digit and a package
                    WITHOUT one does not - automatically.
* Hard-coded "27":  the package number is parsed from the source path.
* Hard-coded nr40:  the base folder code is detected from the folders you
                    already have (e.g. "4011 Foundations_Piers (CD-23)"); if it
                    can't be found it is computed and you can correct it in the
                    confirmation window.
* Definitive/Prelim: detected from the path -> CD or CP prefix.
* Hard-coded "R00": the revision label and its index come from the source
                    folder name (00_R00 -> "R00", 01_R01 -> "R01", ...).
* Hard-coded user:  no user name is hard-coded anywhere - you choose both
                    folders, and the paths are derived once.
* Repeated paths:   every path is derived once from the two folders you pick.
* Overwrite on re-run: folders are created with exist_ok and existing files are
                    skipped, so re-running the same package never fails.  No
                    shared "Temporary" folder is used.
* PDF merge fails:  the merge is robust - encrypted/damaged PDFs are repaired
                    when possible and otherwise skipped and listed for you.
* 4 sub-flows:      everything is in this one file.

The job is non-destructive: it COPIES from the SharePoint source and never
deletes anything there.

Usage
-----
    # Easiest - double-click the built .exe, or run with no arguments to get
    # the folder-picker pop-ups:
    python PIO_Document_Sorter.py

    # Fully from the command line (no pop-ups):
    python PIO_Document_Sorter.py --source "<...>\\00_R00" \\
                                  --dest   "<...>\\Document Control"

    # Preview what would happen without copying anything:
    python PIO_Document_Sorter.py --source ... --dest ... --dry-run

Optional packages (the script still runs without them, but PDF merging needs
one of them):  see requirements.txt.  Build instructions for the .exe are in
PIO_Document_Sorter_README.md.
"""

import argparse
import collections
import datetime
import os
import re
import shutil
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

# ===========================================================================
#  CONFIG  -  edit this section to change the behaviour.  Nothing below here
#  normally needs to be touched.
# ===========================================================================

# How files are sorted by their name.  Each rule is (list-of-substrings, key).
# The keys map to folders built further down (see build_structure).  Matching
# is case-insensitive and the FIRST matching rule wins.
SORTING_RULES = [
    (["ODA-PLA", "ODA-BOA"],                     "drawings_original"),
    (["RPT", "SPC", "CER", "FIT", "MET"],        "reports_original"),
]

# A report whose name (without extension) ends with this is treated as the
# translated (English) version and goes into the "Translated" sub-folder.
TRANSLATED_SUFFIX = "_EN"

# Files with these extensions go straight to the revision-folder root (handy
# for tracking spreadsheets that travel with the submission).
ROOT_EXTENSIONS = [".xlsx", ".xls"]

# Anything the rules can't place is copied here, inside the revision folder, so
# nothing is ever lost and it is obvious what still needs a human.
UNSORTED_FOLDER_NAME = "_To_Sort_Manually"

# Drawings are merged in descending file-name order (matches the old flow).
DRAWINGS_SORT_DESCENDING = True

# Stage word found in the source path -> (prefix, stage digit used in codes).
#   "401 Definitive" -> digit 1,   "400 Preliminary" -> digit 0
STAGE_FROM_PATH = {
    "definit": ("CD", "1"),   # Definitive
    "prelim":  ("CP", "0"),   # Preliminaire / Preliminary  (also matches "prelimin")
}
STAGE_DIGITS = {"CD": "1", "CP": "0"}
STAGE_WORD = {"CD": "Definitive", "CP": "Preliminaire"}

# Fallback only.  CD-23 -> 4011, CD-24 -> 4012 ...  i.e. last digit = number - 22.
# This is ONLY used when the package folder can't be found in the destination;
# you can always correct the result in the confirmation window.
PACKAGE_NUMBER_OFFSET = 22

# ===========================================================================
#  PATH PARSING  -  read the stage / package / sub-part / revision from a path.
# ===========================================================================


def _pure(path_str):
    """Return a PurePath of the right flavour so we can split a Windows path
    even when this script is run on Linux/Mac for testing."""
    if "\\" in path_str or re.match(r"^[A-Za-z]:", path_str):
        return PureWindowsPath(path_str)
    return PurePosixPath(path_str)


def parse_source(source_path):
    """Read everything we can from the source folder path.

    Returns a dict with: stage ("CD"/"CP"/None), pkg (int/None),
    subpart (int/None), rev_name (str), rev_index (int).
    """
    pure = _pure(str(source_path))
    parts = pure.parts
    text = str(source_path)

    # --- Stage: look for "Definitive" / "Preliminaire" anywhere in the path ---
    stage = None
    for part in parts:
        low = part.lower()
        for marker, (code, _digit) in STAGE_FROM_PATH.items():
            if marker in low:
                stage = code
    # --- Package number from CD-XX or CP-XX ---
    pkg = None
    m = re.search(r"C[DP][-_ ]?(\d+)", text, re.IGNORECASE)
    if m:
        pkg = int(m.group(1))

    # --- Sub-part: a path element like "23.4" or "CD-23.4" ---
    subpart = None
    if pkg is not None:
        for part in parts:
            m2 = re.search(rf"(?<!\d){pkg}\.(\d+)", part)
            if m2:
                subpart = int(m2.group(1))
                break

    # --- Revision from the leaf folder name (e.g. "00_R00", "01_R01A") ---
    leaf = parts[-1] if parts else ""
    rev_index, rev_name = 0, "R00"
    m3 = re.match(r"\s*(\d+)[\s_\-]*(R[\w]*)", leaf, re.IGNORECASE)
    if m3:
        rev_index = int(m3.group(1))
        rev_name = m3.group(2).upper()
    else:
        m4 = re.search(r"(R\d+[A-Za-z]?)", leaf, re.IGNORECASE)
        if m4:
            rev_name = m4.group(1).upper()

    return {
        "stage": stage,
        "pkg": pkg,
        "subpart": subpart,
        "rev_name": rev_name,
        "rev_index": rev_index,
    }


# ===========================================================================
#  FOLDER-CODE RESOLUTION  -  work out the base numeric code and where to put
#  the new revision folder, preferring the folders you already have.
# ===========================================================================


def find_folder_by_regex(root, pattern, max_depth=6):
    """Search 'root' for the shallowest directory whose name matches 'pattern'
    and starts with a run of digits.  Return (code, Path) or (None, None)."""
    root = Path(root)
    if not root.exists():
        return None, None
    rx = re.compile(pattern, re.IGNORECASE)
    best = None  # (depth, code, path)
    for dirpath, dirnames, _files in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth >= max_depth:
            dirnames[:] = []
        for name in dirnames:
            if rx.search(name):
                code_match = re.match(r"\s*(\d+)", name)
                code = code_match.group(1) if code_match else None
                if code and (best is None or depth < best[0]):
                    best = (depth, code, Path(dirpath) / name)
    return (best[1], best[2]) if best else (None, None)


def resolve_base_code(dest_root, stage, pkg, subpart):
    """Return a dict with base_code, package_code, the folder to place the new
    revision in, and whether the package was detected from existing folders."""
    stage_digit = STAGE_DIGITS.get(stage, "1")

    # 1) Package folder, e.g. "4011 Foundations_Piers (CD-23)".
    pkg_code, pkg_path = find_folder_by_regex(
        dest_root, rf"{stage}-0*{pkg}(?![\d.])"
    )
    detected = pkg_code is not None
    if not detected:
        pkg_code = f"40{stage_digit}{pkg - PACKAGE_NUMBER_OFFSET}"

    base_code, base_path = pkg_code, pkg_path

    # 2) If there is a sub-part, prefer an existing sub-part folder, e.g.
    #    "40113 CD-23.4"; otherwise append (sub - 1) to the package code.
    if subpart:
        sub_code, sub_path = find_folder_by_regex(
            dest_root, rf"(?:{stage}-)?0*{pkg}\.0*{subpart}(?!\d)"
        )
        if sub_code:
            base_code, base_path = sub_code, sub_path
        else:
            base_code = f"{pkg_code}{subpart - 1}"
            base_path = None

    placement = base_path or pkg_path or Path(dest_root)
    return {
        "base_code": base_code,
        "package_code": pkg_code,
        "placement": str(placement),
        "package_detected": detected,
    }


def compute_codes(base_code, rev_index):
    """Derive every numeric code from the base code (one digit per level)."""
    rev = f"{base_code}{rev_index}"
    reports = f"{rev}0"
    drawings = f"{rev}1"
    return {
        "base": base_code,
        "rev": rev,
        "reports": reports,
        "drawings": drawings,
        "rep_orig": f"{reports}0",
        "rep_trans": f"{reports}1",
        "dwg_orig": f"{drawings}0",
        "dwg_comb": f"{drawings}1",
    }


# ===========================================================================
#  FOLDER STRUCTURE + FILE SORTING
# ===========================================================================


def build_structure(parent, codes, rev_name, dry_run=False):
    """Create (unless dry-run) and return the folder map for one revision."""
    parent = Path(parent)
    rev_dir = parent / f"{codes['rev']} {rev_name}"
    reports = rev_dir / f"{codes['reports']} Reports"
    drawings = rev_dir / f"{codes['drawings']} Drawings"
    folders = {
        "rev": rev_dir,
        "reports": reports,
        "drawings": drawings,
        "reports_original": reports / f"{codes['rep_orig']} Original",
        "reports_translated": reports / f"{codes['rep_trans']} Translated",
        "drawings_original": drawings / f"{codes['dwg_orig']} Original",
        "drawings_combined": drawings / f"{codes['dwg_comb']} Combined",
        # spreadsheets etc. sit at the revision root so the whole submission is
        # self-contained for the drag-and-drop into ProjectWise.
        "root": rev_dir,
        # created lazily, only if something can't be sorted.
        "unsorted": rev_dir / UNSORTED_FOLDER_NAME,
    }
    if not dry_run:
        for key in (
            "rev", "reports", "drawings", "reports_original",
            "reports_translated", "drawings_original", "drawings_combined",
        ):
            folders[key].mkdir(parents=True, exist_ok=True)
    return folders


def classify_file(name):
    """Return the destination key for a file name, or None if we can't tell.

    Edit SORTING_RULES / TRANSLATED_SUFFIX / ROOT_EXTENSIONS at the top of the
    file to change this.
    """
    lower = name.lower()
    stem, ext = os.path.splitext(name)

    if ext.lower() in ROOT_EXTENSIONS:
        return "root"

    for substrings, key in SORTING_RULES:
        if any(s.lower() in lower for s in substrings):
            if key == "reports_original" and stem.lower().endswith(
                TRANSLATED_SUFFIX.lower()
            ):
                return "reports_translated"
            return key
    return None


def copy_and_sort(source, folders, dry_run=False):
    """Copy every file from the source folder into the right sub-folder.

    Returns (copied, skipped, unsorted) where copied maps key -> [names].
    """
    copied = collections.defaultdict(list)
    skipped = []
    unsorted = []

    for entry in sorted(Path(source).iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir():
            continue
        key = classify_file(entry.name)
        dest_dir = folders[key] if key else folders["unsorted"]

        if dry_run:
            copied[key or "unsorted"].append(entry.name)
            if key is None:
                unsorted.append(entry.name)
            continue

        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / entry.name
        if target.exists():
            skipped.append(entry.name)
            continue
        shutil.copy2(entry, target)
        copied[key or "unsorted"].append(entry.name)
        if key is None:
            unsorted.append(entry.name)

    return copied, skipped, unsorted


# ===========================================================================
#  PDF MERGING  -  robust against encrypted / damaged files.
# ===========================================================================


def _add_sequential_suffix(path):
    """Return a path that does not exist yet, adding _1, _2 ... if needed."""
    if not path.exists():
        return path
    stem, suffix, i = path.stem, path.suffix, 1
    while True:
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def _merge_with_pikepdf(pdf_paths, output_path):
    """Best option: qpdf-based, repairs many 'cannot be merged' files."""
    import pikepdf

    out = pikepdf.Pdf.new()
    failed = []
    for p in pdf_paths:
        try:
            with pikepdf.open(str(p), password="") as src:
                out.pages.extend(src.pages)
        except Exception as exc:  # noqa: BLE001 - we want to keep going
            failed.append((p.name, str(exc)))
    out.save(str(output_path))
    out.close()
    return failed


def _merge_with_pypdf(pdf_paths, output_path):
    """Pure-Python fallback (pip install pypdf)."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:  # very old installs
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore

    writer = PdfWriter()
    failed = []
    for p in pdf_paths:
        try:
            reader = PdfReader(str(p))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:  # noqa: BLE001
                    pass
            for page in reader.pages:
                writer.add_page(page)
        except Exception as exc:  # noqa: BLE001
            failed.append((p.name, str(exc)))
    with open(output_path, "wb") as fh:
        writer.write(fh)
    return failed


def merge_drawings(drawings_dir, output_path, dry_run=False):
    """Merge every PDF in drawings_dir into output_path.

    Returns (status, output_path, merged_count, failed) where failed is a list
    of (file_name, reason) for files that could not be merged.
    """
    pdfs = sorted(
        Path(drawings_dir).glob("*.pdf"),
        key=lambda p: p.name.lower(),
        reverse=DRAWINGS_SORT_DESCENDING,
    )
    if not pdfs:
        return "no-pdfs", None, 0, []
    if dry_run:
        return "dry-run", output_path, len(pdfs), []

    output_path = _add_sequential_suffix(Path(output_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prefer pikepdf (handles broken/encrypted files), fall back to pypdf.
    try:
        import pikepdf  # noqa: F401
        failed = _merge_with_pikepdf(pdfs, output_path)
    except ImportError:
        try:
            failed = _merge_with_pypdf(pdfs, output_path)
        except ImportError:
            return "no-library", None, 0, [
                (p.name, "no PDF library installed") for p in pdfs
            ]

    merged = len(pdfs) - len(failed)
    if merged == 0:
        # nothing got in - remove the empty output so it isn't mistaken for OK
        if output_path.exists():
            output_path.unlink()
        return "all-failed", None, 0, failed
    return "ok", output_path, merged, failed


# ===========================================================================
#  ORCHESTRATION
# ===========================================================================


def run(source, dest_root, fields, dry_run=False):
    """Do the whole job and return a human-readable summary string."""
    pkg = fields.get("pkg")
    subpart = fields.get("subpart")
    stage = fields.get("stage") or "CD"

    codes = compute_codes(fields["base_code"], int(fields["rev_index"]))
    folders = build_structure(
        fields["placement"], codes, fields["rev_name"], dry_run
    )

    copied, skipped, unsorted = copy_and_sort(source, folders, dry_run)

    cdnr = f"{pkg}.{subpart}" if subpart else (str(pkg) if pkg else "")
    merged_name = f"PIO_{stage}_{cdnr}_Combined_Drawings.pdf"
    merge_status, merged_path, merged_count, merge_failed = merge_drawings(
        folders["drawings_original"],
        folders["drawings_combined"] / merged_name,
        dry_run,
    )

    return _summary(
        source, folders, codes, fields, copied, skipped, unsorted,
        merge_status, merged_path, merged_count, merge_failed, dry_run,
    )


def _summary(source, folders, codes, fields, copied, skipped, unsorted,
             merge_status, merged_path, merged_count, merge_failed, dry_run):
    lines = []
    head = "DRY RUN - nothing was written" if dry_run else "Done"
    lines.append(f"=== PIO Document Sorter - {head} ===")
    lines.append(f"Source      : {source}")
    lines.append(f"Revision    : {codes['rev']} {fields['rev_name']}")
    lines.append(f"Created in  : {folders['rev']}")
    if not fields.get("package_detected", True):
        lines.append(
            "  ! Package code was COMPUTED, not found in your folders - "
            "double-check the numbering."
        )
    lines.append("")

    total = sum(len(v) for v in copied.values())
    label = "Would copy" if dry_run else "Copied"
    lines.append(f"{label} {total} file(s):")
    pretty = {
        "drawings_original": "Drawings/Original",
        "reports_original": "Reports/Original",
        "reports_translated": "Reports/Translated",
        "root": "Revision root (spreadsheets)",
        "unsorted": f"{UNSORTED_FOLDER_NAME} (needs a human)",
    }
    for key, names in copied.items():
        lines.append(f"  - {pretty.get(key, key)}: {len(names)}")
    if skipped:
        lines.append(f"  - already existed, skipped: {len(skipped)}")
    lines.append("")

    # Drawings merge
    if merge_status == "ok":
        lines.append(f"Drawings merged: {merged_count} PDF(s) -> {merged_path.name}")
    elif merge_status == "no-pdfs":
        lines.append("Drawings merged: no PDFs found in Drawings/Original.")
    elif merge_status == "dry-run":
        lines.append(f"Drawings merged: would merge {merged_count} PDF(s).")
    elif merge_status == "no-library":
        lines.append(
            "Drawings merged: SKIPPED - install a PDF library "
            "(pip install pikepdf  or  pip install pypdf)."
        )
    elif merge_status == "all-failed":
        lines.append("Drawings merged: FAILED - none of the PDFs could be merged.")
    if merge_failed:
        lines.append(
            f"  ! {len(merge_failed)} drawing(s) could NOT be merged "
            "(merge the rest is fine - handle these by hand):"
        )
        for name, reason in merge_failed:
            short = reason if len(reason) < 70 else reason[:67] + "..."
            lines.append(f"      - {name}  ({short})")
    lines.append("")

    if unsorted:
        lines.append(
            f"{len(unsorted)} file(s) could not be sorted automatically and were "
            f"placed in '{UNSORTED_FOLDER_NAME}':"
        )
        for name in unsorted:
            lines.append(f"      - {name}")
        lines.append(
            "  Tip: add the keyword from these names to SORTING_RULES at the "
            "top of the script so they sort next time."
        )
    else:
        lines.append("All files were sorted automatically.")

    return "\n".join(lines)


def write_log(dest_root, summary):
    """Save the summary next to the destination so there is a record."""
    try:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = Path(dest_root) / f"PIO_Sorter_log_{stamp}.txt"
        log_path.write_text(summary, encoding="utf-8")
        return log_path
    except Exception:  # noqa: BLE001 - logging must never crash the run
        return None


# ===========================================================================
#  USER INTERFACE  -  GUI folder pickers + an editable confirmation window,
#  with a plain-text fallback when there is no display / tkinter.
# ===========================================================================

FIELD_LABELS = [
    ("Stage (CD or CP)", "stage"),
    ("Package number", "pkg"),
    ("Sub-part (blank if none)", "subpart"),
    ("Revision label", "rev_name"),
    ("Revision index (single digit)", "rev_index"),
    ("Base folder code (drives numbering)", "base_code"),
    ("Create revision folder inside", "placement"),
]


def _gather_fields(source, dest_root):
    """Combine path parsing + code resolution into one editable dict."""
    parsed = parse_source(source)
    warnings = []
    if parsed["stage"] is None:
        parsed["stage"] = "CD"
        warnings.append(
            "Could not tell Definitive/Preliminaire from the path - assuming CD."
        )
    if parsed["pkg"] is None:
        warnings.append(
            "Could not find a CD-/CP- package number in the path - please enter it."
        )

    resolved = {"base_code": "", "package_code": "", "placement": str(dest_root),
                "package_detected": False}
    if parsed["pkg"] is not None:
        resolved = resolve_base_code(
            dest_root, parsed["stage"], parsed["pkg"], parsed["subpart"]
        )
        if not resolved["package_detected"]:
            warnings.append(
                f"No existing folder for {parsed['stage']}-{parsed['pkg']} was "
                "found - the base code was computed. Check it below."
            )

    fields = {
        "stage": parsed["stage"],
        "pkg": parsed["pkg"] if parsed["pkg"] is not None else "",
        "subpart": parsed["subpart"] if parsed["subpart"] else "",
        "rev_name": parsed["rev_name"],
        "rev_index": parsed["rev_index"],
        "base_code": resolved["base_code"],
        "placement": resolved["placement"],
        "package_detected": resolved["package_detected"],
    }
    return fields, warnings


def _normalise_fields(raw):
    """Turn the (possibly user-edited) string fields into typed values."""
    fields = dict(raw)
    fields["stage"] = (raw.get("stage") or "CD").strip().upper()
    pkg = str(raw.get("pkg", "")).strip()
    fields["pkg"] = int(pkg) if pkg.isdigit() else None
    sub = str(raw.get("subpart", "")).strip()
    fields["subpart"] = int(sub) if sub.isdigit() else None
    idx = str(raw.get("rev_index", "0")).strip()
    fields["rev_index"] = int(idx) if idx.isdigit() else 0
    fields["rev_name"] = (raw.get("rev_name") or "R00").strip()
    fields["base_code"] = str(raw.get("base_code", "")).strip()
    fields["placement"] = str(raw.get("placement", "")).strip()

    # If the user supplied a package number but no base code (e.g. nothing could
    # be auto-detected), compute the base code from the fallback formula so the
    # run can still proceed instead of refusing.
    if not fields["base_code"] and fields["pkg"] is not None:
        stage_digit = STAGE_DIGITS.get(fields["stage"], "1")
        pkg_code = f"40{stage_digit}{fields['pkg'] - PACKAGE_NUMBER_OFFSET}"
        fields["base_code"] = (
            f"{pkg_code}{fields['subpart'] - 1}" if fields["subpart"] else pkg_code
        )
    return fields


def confirm_fields_gui(fields, warnings):
    """One editable window; returns the edited dict or None if cancelled."""
    import tkinter as tk

    root = tk.Tk()
    root.title("PIO Document Sorter - confirm details")
    row = 0
    if warnings:
        tk.Label(root, text="\n".join("! " + w for w in warnings), fg="#b00000",
                 justify="left", wraplength=520).grid(
            row=row, column=0, columnspan=2, padx=12, pady=(12, 4), sticky="w")
        row += 1
    tk.Label(
        root,
        text=("These values were read from the source folder and your existing\n"
              "folders. Correct anything that is wrong, then click Run."),
        justify="left",
    ).grid(row=row, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="w")
    row += 1

    entries = {}
    for label, key in FIELD_LABELS:
        tk.Label(root, text=label).grid(
            row=row, column=0, sticky="e", padx=(12, 6), pady=2)
        var = tk.StringVar(value=str(fields.get(key, "")))
        width = 64 if key == "placement" else 40
        tk.Entry(root, textvariable=var, width=width).grid(
            row=row, column=1, sticky="w", padx=(0, 12), pady=2)
        entries[key] = var
        row += 1

    state = {"ok": False}

    def on_run():
        state["ok"] = True
        root.destroy()

    def on_cancel():
        root.destroy()

    bar = tk.Frame(root)
    bar.grid(row=row, column=0, columnspan=2, pady=12)
    tk.Button(bar, text="Run", width=12, command=on_run).pack(side="left", padx=6)
    tk.Button(bar, text="Cancel", width=12, command=on_cancel).pack(side="left", padx=6)
    root.bind("<Return>", lambda _e: on_run())
    root.bind("<Escape>", lambda _e: on_cancel())
    root.mainloop()

    if not state["ok"]:
        return None
    return {key: var.get() for key, var in entries.items()}


def confirm_fields_cli(fields, warnings):
    """Plain-text confirmation used when there is no GUI."""
    for w in warnings:
        print("! " + w)
    print("\nDetected details (press Enter to keep the value shown):")
    edited = {}
    for label, key in FIELD_LABELS:
        current = str(fields.get(key, ""))
        answer = input(f"  {label} [{current}]: ").strip()
        edited[key] = answer if answer else current
    return edited


def pick_folder(title):
    """Folder picker; returns a path string or None."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        path = filedialog.askdirectory(title=title)
        root.destroy()
        return path or None
    except Exception:  # noqa: BLE001 - no display, etc.
        return None


def show_message(summary, is_error=False):
    """Show the final summary in a pop-up if possible, always print it too."""
    print("\n" + summary + "\n")
    try:
        import tkinter as tk
        from tkinter import scrolledtext

        win = tk.Tk()
        win.title("PIO Document Sorter - result")
        box = scrolledtext.ScrolledText(win, width=90, height=28, wrap="word")
        box.insert("1.0", summary)
        box.configure(state="disabled")
        box.pack(padx=10, pady=10)
        tk.Button(win, text="Close", width=12, command=win.destroy).pack(pady=(0, 10))
        win.mainloop()
    except Exception:  # noqa: BLE001
        pass


# ===========================================================================
#  ENTRY POINT
# ===========================================================================


def parse_args(argv):
    p = argparse.ArgumentParser(description="Sort a PIO submission folder.")
    p.add_argument("--source", help="SharePoint-synced revision folder (the files).")
    p.add_argument("--dest", help="Destination root, e.g. your Document Control folder.")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview only - copy/merge nothing.")
    p.add_argument("--no-gui", action="store_true",
                   help="Never open windows - use the command line only.")
    p.add_argument("--yes", action="store_true",
                   help="Skip the confirmation step (use detected values as-is).")
    p.add_argument("--self-test", action="store_true",
                   help="Run internal logic checks and exit.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if args.self_test:
        return _self_test()

    use_gui = not args.no_gui

    source = args.source or (pick_folder("Select the SOURCE folder (the files)") if use_gui else None)
    if not source:
        print("No source folder selected - nothing to do.")
        return 1
    dest = args.dest or (pick_folder("Select the DESTINATION root (Document Control)") if use_gui else None)
    if not dest:
        print("No destination folder selected - nothing to do.")
        return 1

    if not Path(source).is_dir():
        show_message(f"Source folder does not exist:\n{source}", is_error=True)
        return 1
    if not any(p.is_file() for p in Path(source).iterdir()):
        show_message(
            "The selected source folder has no files directly inside it.\n"
            "Please select the revision (R00) folder that actually contains "
            "the files.", is_error=True)
        return 1

    fields, warnings = _gather_fields(source, dest)

    if not args.yes:
        edited = (confirm_fields_gui(fields, warnings) if use_gui
                  else confirm_fields_cli(fields, warnings))
        if edited is None:
            print("Cancelled.")
            return 1
        # keep package_detected/placement from detection unless user changed them
        merged = dict(fields)
        merged.update(edited)
        fields = merged

    fields = _normalise_fields(fields)
    if fields["pkg"] is None or not fields["base_code"]:
        show_message(
            "Missing package number or base folder code - cannot continue.\n"
            "Run again and fill those in.", is_error=True)
        return 1

    summary = run(source, dest, fields, dry_run=args.dry_run)
    if not args.dry_run:
        log_path = write_log(dest, summary)
        if log_path:
            summary += f"\n\nLog saved to: {log_path}"
    show_message(summary)
    return 0


# ===========================================================================
#  SELF TEST  -  pure-logic checks so the numbering can't silently break.
# ===========================================================================


def _self_test():
    failures = []

    def check(label, got, want):
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    # Sub-part case: CD-23.4 / R00
    src = r"C:\Users\AEAA\Cima+\...\De_Conception\Definitive\CD-23\23.4\00_R00"
    p = parse_source(src)
    check("subpart.stage", p["stage"], "CD")
    check("subpart.pkg", p["pkg"], 23)
    check("subpart.subpart", p["subpart"], 4)
    check("subpart.rev_name", p["rev_name"], "R00")
    check("subpart.rev_index", p["rev_index"], 0)
    base = f"40{STAGE_DIGITS['CD']}{23 - PACKAGE_NUMBER_OFFSET}{4 - 1}"
    check("subpart.base", base, "40113")
    c = compute_codes(base, p["rev_index"])
    check("subpart.rev", c["rev"], "401130")
    check("subpart.reports", c["reports"], "4011300")
    check("subpart.drawings", c["drawings"], "4011301")
    check("subpart.rep_orig", c["rep_orig"], "40113000")
    check("subpart.dwg_orig", c["dwg_orig"], "40113010")
    check("subpart.dwg_comb", c["dwg_comb"], "40113011")

    # No-sub-part case: CD-27 / R00  -> one digit shorter (the "extra 0" fix)
    src2 = r"C:\Users\X\...\Definitive\CD-27\00_R00"
    p2 = parse_source(src2)
    check("nosub.pkg", p2["pkg"], 27)
    check("nosub.subpart", p2["subpart"], None)
    base2 = f"40{STAGE_DIGITS['CD']}{27 - PACKAGE_NUMBER_OFFSET}"
    check("nosub.base", base2, "4015")
    c2 = compute_codes(base2, p2["rev_index"])
    check("nosub.rev", c2["rev"], "40150")
    check("nosub.reports", c2["reports"], "401500")

    # Preliminaire -> CP, alternate revision label
    src3 = r"C:\X\Preliminaire\CP-24\24.2\01_R01A"
    p3 = parse_source(src3)
    check("prelim.stage", p3["stage"], "CP")
    check("prelim.pkg", p3["pkg"], 24)
    check("prelim.subpart", p3["subpart"], 2)
    check("prelim.rev_name", p3["rev_name"], "R01A")
    check("prelim.rev_index", p3["rev_index"], 1)

    # File classification
    check("cls.rpt", classify_file("DEJV-11000-1200-RPT-00001.pdf"), "reports_original")
    check("cls.rpt_en", classify_file("DEJV-11000-1200-RPT-00001_EN.pdf"), "reports_translated")
    check("cls.spc", classify_file("DEJV-SPC-9.pdf"), "reports_original")
    check("cls.pla", classify_file("DEJV-ODA-PLA-0001.pdf"), "drawings_original")
    check("cls.boa", classify_file("DEJV-ODA-BOA-0001.pdf"), "drawings_original")
    check("cls.xlsx", classify_file("tracking list.xlsx"), "root")
    check("cls.unknown", classify_file("random notes.docx"), None)

    if failures:
        print("SELF TEST FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("SELF TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
