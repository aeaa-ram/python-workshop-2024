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
4. It builds the correctly-numbered folder tree, copies and sorts the files by
   their naming convention, and merges the drawings into a single PDF - in the
   right page order, skipping (and reporting) any PDF that cannot be merged
   instead of failing the whole job.

The numbering scheme (your convention)
--------------------------------------
       400              Preliminaire        (top-level stage codes - fixed)
       401              Definitive
        40101           CD-23               (stage + a 2-digit package code)
         401012         CD-23.4             (package + sub-part, 0-indexed as ONE digit: .1→0 .2→1 .3→2 .4→3)
          4010120       R00                 (one more digit per level below)
           40101200     Reports
            401012000   Original
            401012001   Translated
           40101201     Drawings
            401012010   Original
            401012011   Combined

  A package with no sub-parts skips that digit entirely - the revision sits
  straight under the package (e.g. CP-26 -> 40004 -> 400040 R00 -> ...).  A
  handful of packages (e.g. CP-35, CP-39) intentionally start as a single
  unlabelled sub-part - a folder that still just has the package's own name,
  not "<pkg>.1" yet - occupying that same digit; the script recognises and
  builds into it rather than skipping past it (see _find_implicit_subpart).

* The two stage codes (400 / 401) and the digit widths live in the CONFIG block
  below - change them there if your scheme ever differs.
* The 2-digit package code (e.g. "01" for CD-23) is NOT computed from the
  package number - there is no fixed relationship between "23" and "01".  It is
  read from the folder you already have for that package (one whose name
  contains "(CD-23)"), or typed once in the confirmation window.  After the
  first time the folder exists, so it is detected automatically.

Design notes / how the old flaws are fixed
------------------------------------------
* Wrong digit count:the depth follows the real folder depth - a package WITH a
                    sub-part gets the extra sub-part level, one WITHOUT it does
                    not - decided automatically from the source path.
* Package number:   read from the source path, not hard-coded.
* Package code:     detected from the folders you already have, or typed once
                    in the confirmation window - never guessed from the number.
* Stage:            Definitive/Preliminaire detected from the path -> 401 / 400.
* Revision label:   read from the source folder name (00_R00 -> "R00", ...).
* User directory:   nothing is hard-coded - you choose both folders.
* Re-running:       folders use exist_ok and existing files are skipped, so
                    re-running the same package never fails.
* PDF merge order:  drawings merge in ascending file-name order and each page
                    keeps its own rotation, so the combined PDF reads correctly.
* PDF merge fails:  encrypted/damaged PDFs are repaired when possible and
                    otherwise skipped and listed for you.
* Files in limbo:   anything a rule can't place is reported in a warnings list
                    and left loose at the revision root (never in its own
                    folder, so it's easy to clear out by hand), never silently
                    dropped.

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
one of them):  pikepdf (recommended) or pypdf.  Both are installed automatically
on first run.
"""

import argparse
import collections
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath


def _ensure_deps():
    """Install pikepdf automatically if it is not already present."""
    try:
        import pikepdf  # noqa: F401
        return
    except ImportError:
        pass
    try:
        print("Setting up PDF library (first time only, may take a minute)...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "pikepdf"]
        )
        print("PDF library ready.")
    except Exception:
        pass  # script still runs; drawings merge is skipped if pikepdf is missing


# ===========================================================================
#  CONFIG  -  edit this section to change the behaviour.  Nothing below here
#  normally needs to be touched.
# ===========================================================================

# How files are sorted by their name.  Each rule is (list-of-substrings, key).
# The keys map to folders built further down (see build_structure).  Matching
# is case-insensitive and the FIRST matching rule wins.
# "-PLA-"/"-BOA-" match any originator code (ODA-PLA, ADS-PLA, ...) - the
# document-TYPE code (PLA/BOA) is what decides it's a drawing, not who made it.
SORTING_RULES = [
    (["-PLA-", "-BOA-"],                          "drawings_original"),
    (["RPT", "SPC", "CER", "FIT", "MET", "MOD"],  "reports_original"),
]

# Drawing files whose name contains one of these are still copied into
# Drawings/Original (matched by SORTING_RULES above like any other drawing),
# but are left OUT of the merged Combined PDF.
DRAWINGS_MERGE_EXCLUDE = ["ADS-PLA"]

# A report whose name (without extension) ends with this is treated as the
# translated (English) version and goes into the "Translated" sub-folder.
TRANSLATED_SUFFIX = "_EN"

# The one spreadsheet worth keeping is the document list (e.g. "CNC-LST..."):
# it is kept at the revision root for reference.  Matched by keyword anywhere in
# the file name, case-insensitive.  Add other names here if yours differ.
DOCUMENT_LIST_KEYWORDS = ["CNC-LST"]

# Files with these extensions are kept as-is at the revision-folder root, so a
# zip that travels with the submission is preserved.  (The document list above
# is also kept at the root, whatever its extension.)
ROOT_EXTENSIONS = [".zip"]

# Spreadsheets / office files that are NOT the document list are not part of the
# submission, so they are skipped silently - not copied and not flagged.
IGNORE_EXTENSIONS = [".xls", ".xlsx", ".xlsm"]

# Anything the rules can't place is left loose at the revision-folder root
# (next to Reports/Drawings) rather than in its own sub-folder, so nothing is
# ever lost - and since it's plain files, not a folder, it stays easy to
# clear out even without folder-delete permissions.  A short text file
# listing what needs a look is dropped alongside them - see write_unsorted_note.
UNSORTED_NOTE_NAME = "_READ_ME_unsorted.txt"

# Drawings are merged in ascending file-name order (sheet 1, 2, 3 ...).  Set
# this to True if you ever want the old descending order back.
DRAWINGS_SORT_DESCENDING = False

# Which stage a path belongs to, recognised from a folder name in the path.
#   "...\Definitive\..."  -> CD        "...\Preliminaire\..." -> CP
# Add other spellings here if your folders ever use them.
STAGE_FROM_PATH = {
    "definit": "CD",   # matches "Definitive"
    "prelim":  "CP",   # matches "Preliminaire" / "Preliminary"
}

# --- The numbering convention (this is the only fixed part of the scheme) ---
# Each stage has a fixed top-level code; everything below is built from it.
STAGE_CODES = {
    "CP": "400",   # Preliminaire
    "CD": "401",   # Definitive
}
# Friendly names used only when the script has to CREATE a stage / package
# folder for the first time (you can rename them afterwards).
STAGE_NAMES = {"CP": "Preliminaire", "CD": "Definitive"}

# Digit widths for the two numbered levels under a stage.
PKG_SUFFIX_WIDTH = 2   # CD-23   -> a 2-digit package code, e.g. "01" (40101)
SUBPART_WIDTH = 1      # CD-23.4 -> the sub-part number as 1 digit, 0-indexed: "3" (401013)
# Every level below that (revision, Reports/Drawings, Original/Translated/
# Combined) adds exactly one digit.

# The package code (e.g. "01" for CD-23) is NEVER computed from the package
# number.  It is read from the folder you already have for that package (one
# whose name contains "(CD-23)"), or typed once in the confirmation window.
# That is what keeps the script generic for any package or numbering scheme.

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
        for marker, code in STAGE_FROM_PATH.items():
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
#  FOLDER-CODE RESOLUTION  -  work out the 2-digit package code and where to
#  put the new folders, preferring the folders you already have.
# ===========================================================================


def _lead(name):
    """The leading run of digits in a folder name, or None."""
    m = re.match(r"\s*(\d+)", name)
    return m.group(1) if m else None


def _find_implicit_subpart(package_dir, package_code):
    """Detect a sub-part 'wrapper' folder that hasn't been renamed to
    '<pkg>.N' yet - some packages (e.g. CP-35, CP-39) intentionally start as
    a single sub-part that still just carries the package's own name, ready
    to be split into ".1" / ".2" later.  It occupies the sub-part digit on
    disk (package code + one digit) but isn't itself a revision folder.

    Returns the Path of that folder if exactly one such child exists, else
    None (no sub-part level - build the revision straight under the package,
    or more than one candidate - ambiguous, leave it alone)."""
    candidates = []
    try:
        for e in os.scandir(package_dir):
            if not e.is_dir():
                continue
            code = _lead(e.name)
            if (code and code.startswith(package_code)
                    and len(code) == len(package_code) + SUBPART_WIDTH
                    and not re.search(r"(?i)\bR\d", e.name)):
                candidates.append(Path(e.path))
    except OSError:
        pass
    return candidates[0] if len(candidates) == 1 else None


def find_folder_by_regex(root, pattern, max_depth=6, include_self=False):
    """Search 'root' for the shallowest directory whose name matches 'pattern'
    and starts with a run of digits.  Return (code, Path) or (None, None).

    With include_self=True the chosen 'root' folder itself is considered too, so
    a folder the user selects directly (already partway down the tree) is found.
    """
    root = Path(root)
    if not root.exists():
        return None, None
    rx = re.compile(pattern, re.IGNORECASE)
    best = None  # (depth, code, path)
    if include_self and rx.search(root.name):
        m = re.match(r"\s*(\d+)", root.name)
        if m:
            best = (-1, m.group(1), root)  # -1 so it beats any descendant
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


def _suffix_from_code(code, stage):
    """Pull the 2-digit package code out of an existing folder's number,
    e.g. "40101" with stage CD (401) -> "01"."""
    stage_code = STAGE_CODES.get((stage or "").upper(), "")
    if stage_code and code.startswith(stage_code):
        return code[len(stage_code):len(stage_code) + PKG_SUFFIX_WIDTH]
    return code[:PKG_SUFFIX_WIDTH]


def resolve_placement(dest_root, stage, pkg, subpart):
    """Work out where to build, from whatever folder the user selected.

    The user may select the top "Document Control" folder, OR a folder that is
    already partway down the tree (its package or sub-part folder).  Either way
    we find the deepest folder that already exists and build the rest below it.
    Nothing about the numbering is computed from the package number - the
    package code is read from your folder, or you type it once.

    Returns a dict:
        pkg_suffix        - the 2-digit package code ('' if not found)
        build_dir         - the existing folder to build inside
        build_level       - "subpart" | "package" | "above_package": what
                            build_dir is, i.e. how much of the tree to create
        subpart_code      - an existing sub-part folder's number (to reuse), else None
        package_detected  - True if an existing package/sub-part folder was found
    """
    dest_root = Path(dest_root)
    stage = (stage or "CD").upper()
    stage_code = STAGE_CODES.get(stage, "")
    info = {
        "pkg_suffix": "",
        "build_dir": str(dest_root),
        "build_level": "above_package",
        "subpart_code": None,
        "package_detected": False,
    }
    if pkg is None:
        return info

    pkg_rx = rf"{stage}-?0*{pkg}(?![\d.])"
    sub_rx = rf"{stage}-?0*{pkg}\.0*{subpart}(?!\d)" if subpart else None

    # (A) An existing sub-part folder, e.g. "4010104 CD-23.4" - selected
    #     directly, or found anywhere under the chosen folder.  Build the new
    #     revision straight inside it (nothing above it is touched).
    if sub_rx:
        code, path = find_folder_by_regex(dest_root, sub_rx, include_self=True)
        if code:
            info["pkg_suffix"] = _suffix_from_code(code, stage)
            info["build_dir"] = str(path)
            info["build_level"] = "subpart"
            info["subpart_code"] = code
            info["package_detected"] = True
            return info

    # (B) An existing package folder, e.g. "40101 ... (CD-23)" - selected
    #     directly, or found below.  (?![\d.]) keeps it off the sub-part folder.
    code, path = find_folder_by_regex(dest_root, pkg_rx, include_self=True)
    if code:
        pkg_level_len = len(stage_code) + PKG_SUFFIX_WIDTH
        sub_level_len = pkg_level_len + SUBPART_WIDTH
        # A sub-part "wrapper" folder legitimately reuses the package's own
        # descriptive text (e.g. "400120 CP-35" before it becomes "CP-35.1"),
        # so it matches pkg_rx just as well as the real package folder does -
        # text alone can't tell them apart.  Its CODE can: it is always
        # exactly one digit longer than the package's.  If what matched
        # (often the folder the user selected directly) already sits at that
        # depth and isn't itself a revision folder, it IS the sub-part level
        # already - build straight into it, never re-derive from the package
        # upwards or search past it.
        if (len(code) == sub_level_len and not re.search(r"(?i)\bR\d", path.name)):
            info["pkg_suffix"] = code[len(stage_code):pkg_level_len]
            info["build_dir"] = str(path)
            info["build_level"] = "subpart"
            info["subpart_code"] = code
            info["package_detected"] = True
            return info
        info["pkg_suffix"] = _suffix_from_code(code, stage)
        info["build_dir"] = str(path)
        info["build_level"] = "package"
        info["package_detected"] = True
        # The source path gave no explicit sub-part ("23.4"), so this package
        # is normally built straight into (no sub-part level).  But some
        # packages already have an un-numbered sub-part wrapper on disk
        # (e.g. "CP-35" before it becomes "CP-35.1") - if so, build into
        # that existing folder instead of skipping past it.
        if not sub_rx:
            implicit = _find_implicit_subpart(path, code)
            if implicit:
                info["build_dir"] = str(implicit)
                info["build_level"] = "subpart"
                info["subpart_code"] = _lead(implicit.name)
        return info

    # (C) Nothing yet - create under the stage folder (e.g. "401 Definitive")
    #     if there is one, otherwise directly under the chosen folder.
    if stage_code:
        _c, stage_dir = find_folder_by_regex(
            dest_root, rf"^\s*{stage_code}(?!\d)", include_self=True)
        if stage_dir:
            info["build_dir"] = str(stage_dir)
    return info


def compute_codes(base, rev_index):
    """Derive the revision code and everything below it from a base code
    (one digit per level).  'base' is the package code (no sub-part) or the
    sub-part code (with a sub-part)."""
    rev = f"{base}{int(rev_index)}"
    reports = f"{rev}0"
    drawings = f"{rev}1"
    return {
        "base": base,
        "rev": rev,
        "reports": reports,
        "drawings": drawings,
        "rep_orig": f"{reports}0",
        "rep_trans": f"{reports}1",
        "dwg_orig": f"{drawings}0",
        "dwg_comb": f"{drawings}1",
    }


def derive_codes(stage, pkg_code, subpart, rev_index, detected_subpart_code=None):
    """Build every numeric code for one revision from the typed/detected
    package code, following the convention in the CONFIG block."""
    stage = (stage or "CD").upper()
    stage_code = STAGE_CODES.get(stage, STAGE_CODES["CD"])
    pkg_code = str(pkg_code).strip()
    if pkg_code.isdigit():
        pkg_code = pkg_code.zfill(PKG_SUFFIX_WIDTH)

    package_code = f"{stage_code}{pkg_code}"
    subpart_code = None
    if subpart or detected_subpart_code:
        # Reuse the code of an existing sub-part folder if there is one - this
        # also covers a package's "implicit" sub-part wrapper (e.g. CP-35
        # before it becomes CP-35.1), whose code isn't derivable from a
        # sub-part number at all - so the numbering on disk and in the
        # script always agree.
        subpart_code = (
            detected_subpart_code
            or f"{package_code}{(int(subpart) - 1):0{SUBPART_WIDTH}d}"
        )
    base = subpart_code if subpart_code else package_code

    codes = compute_codes(base, rev_index)
    codes["package"] = package_code
    codes["subpart"] = subpart_code
    return codes


# ===========================================================================
#  FOLDER STRUCTURE + FILE SORTING
# ===========================================================================


def build_structure(fields, codes, dry_run=False):
    """Create (unless dry-run) and return the folder map for one revision.

    Only the levels BELOW what already exists are created.  'build_level' says
    what the selected/detected folder is:
        "subpart"        - build the revision straight inside it
        "package"        - create the sub-part folder (if any) then the revision
        "above_package"  - create the package folder, sub-part folder, revision
    Existing folders are reused (never duplicated) thanks to exist_ok.
    """
    stage = (fields.get("stage") or "CD").upper()
    pkg = fields.get("pkg")
    subpart = fields.get("subpart")
    build_dir = Path(fields["placement"])
    level = fields.get("build_level", "above_package")

    # --- Package folder (existing, or created with a basic name) ----------
    if level == "above_package":
        package_dir = build_dir / f"{codes['package']} {stage}-{pkg}"
    elif level == "package":
        package_dir = build_dir
    else:  # "subpart": build_dir already IS the sub-part folder
        package_dir = build_dir.parent

    # --- Sub-part folder (only when the package has sub-parts, including an
    #     un-numbered "implicit" wrapper - see _find_implicit_subpart) -------
    if codes.get("subpart"):
        if level == "subpart":
            rev_parent = build_dir
        else:
            rev_parent = package_dir / f"{codes['subpart']} {stage}-{pkg}.{subpart}"
    else:
        rev_parent = package_dir

    # --- Revision tree ----------------------------------------------------
    rev_dir = rev_parent / f"{codes['rev']} {fields['rev_name']}"
    reports = rev_dir / f"{codes['reports']} Reports"
    drawings = rev_dir / f"{codes['drawings']} Drawings"
    folders = {
        "package": package_dir,
        "subpart": rev_parent if codes.get("subpart") else None,
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
        # files no rule could place are left loose at the revision root too -
        # no sub-folder, so they stay easy to clear out by hand.
        "unsorted": rev_dir,
    }
    if not dry_run:
        # parents=True creates the package and sub-part folders as needed.
        for key in (
            "rev", "reports", "drawings", "reports_original",
            "reports_translated", "drawings_original", "drawings_combined",
        ):
            folders[key].mkdir(parents=True, exist_ok=True)
    return folders


def classify_file(name):
    """Decide where a file goes.

    Returns (key, note):
        key  - destination folder key, "ignore" to skip silently, or None if no
               rule matched (file left loose at the revision root and flagged).
        note - None, or a short string describing an ambiguity worth a warning.

    Edit the CONFIG block at the top of the file to change any of this.
    """
    lower = name.lower()
    stem, ext = os.path.splitext(name)
    ext = ext.lower()

    # The document list (e.g. CNC-LST) is kept at the revision root, whatever
    # its extension.
    if any(kw.lower() in lower for kw in DOCUMENT_LIST_KEYWORDS):
        return "root", None

    # Drawings / reports by keyword (the FIRST matching rule wins).
    matched = [key for substrings, key in SORTING_RULES
               if any(s.lower() in lower for s in substrings)]
    if matched:
        key = matched[0]
        if key == "reports_original" and stem.lower().endswith(
            TRANSLATED_SUFFIX.lower()
        ):
            key = "reports_translated"
        # If the name matched two different categories (e.g. a drawing AND a
        # report keyword) flag it so the user can confirm where it landed.
        note = None
        families = {m.split("_", 1)[0] for m in matched}
        if len(families) > 1:
            note = (f"matched more than one category ({', '.join(matched)}); "
                    f"filed under '{key}'")
        return key, note

    # Zips travel with the submission - kept at the revision root.
    if ext in ROOT_EXTENSIONS:
        return "root", None

    # Spreadsheets that aren't the document list are not needed - skip silently.
    if ext in IGNORE_EXTENSIONS:
        return "ignore", None

    return None, None


def copy_and_sort(source, folders, dry_run=False):
    """Copy every file from the source folder into the right sub-folder.

    Returns (copied, skipped, unsorted, ambiguous, ignored):
        copied    - dict key -> [names]
        skipped   - [names] that already existed (left untouched, not overwritten)
        unsorted  - [names] no rule could place (left loose at the revision root)
        ambiguous - [(name, note)] that matched more than one category
        ignored   - [names] intentionally skipped (e.g. stray spreadsheets)
    """
    copied = collections.defaultdict(list)
    skipped, unsorted, ambiguous, ignored = [], [], [], []

    for entry in sorted(Path(source).iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir():
            continue
        key, note = classify_file(entry.name)
        if note:
            ambiguous.append((entry.name, note))
        if key == "ignore":
            ignored.append(entry.name)
            continue
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

    return copied, skipped, unsorted, ambiguous, ignored


# ===========================================================================
#  PDF MERGING  -  robust against encrypted / damaged files, keeps page order
#  and each page's own rotation.
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


def _materialise_rotation(page):
    """Copy an inherited /Rotate down onto the page so the rotation survives the
    merge.  This only propagates a rotation the source PDF already set - it never
    invents one - so it cannot turn a correct page upside down."""
    try:
        if "/Rotate" in page:
            return
        parent = page.get("/Parent")
        seen = 0
        while parent is not None and seen < 32:
            if "/Rotate" in parent:
                page.Rotate = int(parent.Rotate)
                return
            parent = parent.get("/Parent")
            seen += 1
    except Exception:  # noqa: BLE001 - rotation fix-up must never break a merge
        pass


def _merge_with_pikepdf(pdf_paths, output_path):
    """Best option: qpdf-based, repairs many 'cannot be merged' files."""
    import pikepdf

    out = pikepdf.Pdf.new()
    failed = []
    for p in pdf_paths:
        try:
            with pikepdf.open(str(p), password="") as src:
                for page in src.pages:
                    _materialise_rotation(page)
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
    """Merge every PDF in drawings_dir into output_path, except any whose name
    matches DRAWINGS_MERGE_EXCLUDE - those stay in Drawings/Original but are
    left out of the combined PDF.

    Returns (status, output_path, merged_count, failed, excluded) where
    failed is a list of (file_name, reason) for files that could not be
    merged, and excluded is a list of file names deliberately left out.
    """
    all_pdfs = sorted(
        Path(drawings_dir).glob("*.pdf"),
        key=lambda p: p.name.lower(),
        reverse=DRAWINGS_SORT_DESCENDING,
    )
    excluded = [p.name for p in all_pdfs
                if any(kw.lower() in p.name.lower() for kw in DRAWINGS_MERGE_EXCLUDE)]
    pdfs = [p for p in all_pdfs if p.name not in excluded]

    if not pdfs:
        return "no-pdfs", None, 0, [], excluded
    if dry_run:
        return "dry-run", output_path, len(pdfs), [], excluded

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
            ], excluded

    merged = len(pdfs) - len(failed)
    if merged == 0:
        # nothing got in - remove the empty output so it isn't mistaken for OK
        if output_path.exists():
            output_path.unlink()
        return "all-failed", None, 0, failed, excluded
    return "ok", output_path, merged, failed, excluded


# ===========================================================================
#  ORCHESTRATION
# ===========================================================================


def run(source, dest_root, fields, dry_run=False):
    """Do the whole job.  Returns (summary_text, warnings_list)."""
    pkg = fields.get("pkg")
    subpart = fields.get("subpart")
    stage = (fields.get("stage") or "CD").upper()

    codes = derive_codes(
        stage, fields["pkg_code"], subpart, int(fields["rev_index"]),
        fields.get("detected_subpart_code"),
    )
    folders = build_structure(fields, codes, dry_run)

    copied, skipped, unsorted, ambiguous, ignored = copy_and_sort(
        source, folders, dry_run
    )

    cdnr = f"{pkg}.{subpart}" if subpart else (str(pkg) if pkg else "")
    merged_name = f"PIO_{stage}_{cdnr}_Combined_Drawings.pdf"
    merge_status, merged_path, merged_count, merge_failed, merge_excluded = merge_drawings(
        folders["drawings_original"],
        folders["drawings_combined"] / merged_name,
        dry_run,
    )

    warnings = collect_warnings(
        fields, skipped, unsorted, ambiguous, merge_status, merge_failed
    )
    if not dry_run and unsorted:
        write_unsorted_note(folders["unsorted"], unsorted)

    summary = _summary(
        source, folders, codes, fields, copied, skipped, ignored, merge_status,
        merged_path, merged_count, merge_excluded, warnings, dry_run,
    )
    return summary, warnings


def _short(text, n=80):
    """Trim a long error message for display."""
    return text if len(text) <= n else text[:n - 3] + "..."


def collect_warnings(fields, skipped, unsorted, ambiguous, merge_status,
                     merge_failed):
    """Build one flat list of everything the user should look at by hand."""
    w = []
    if not fields.get("package_detected", True):
        w.append(
            "Package code was typed in manually (no matching folder was found "
            "in the destination) - double-check the numbering."
        )
    for name in unsorted:
        w.append(
            f"NOT SORTED (no rule matched): {name}  ->  left loose in the "
            f"revision folder, see {UNSORTED_NOTE_NAME}"
        )
    for name, note in ambiguous:
        w.append(f"CHECK PLACEMENT: {name}  ->  {note}")
    for name, reason in merge_failed:
        w.append(
            f"NOT MERGED (still in Drawings/Original): {name}  ({_short(reason)})"
        )
    if merge_status == "no-library":
        w.append(
            "Drawings were NOT merged - install a PDF library: "
            "pip install pikepdf"
        )
    elif merge_status == "all-failed":
        w.append("Drawings merge FAILED for every file - check the source PDFs.")
    if skipped:
        shown = ", ".join(skipped[:6]) + (" ..." if len(skipped) > 6 else "")
        w.append(
            f"{len(skipped)} file(s) already existed and were left as they were "
            f"(not overwritten): {shown}"
        )
    return w


def write_unsorted_note(unsorted_dir, unsorted):
    """Drop a short readme next to the loose files that still need a human."""
    try:
        Path(unsorted_dir).mkdir(parents=True, exist_ok=True)
        note = Path(unsorted_dir) / UNSORTED_NOTE_NAME
        lines = [
            "These files did not match any sorting rule, so they were left loose",
            "here (next to Reports/Drawings) for you to place by hand:",
            "",
        ] + [f"  - {n}" for n in unsorted] + [
            "",
            "To sort files like these automatically next time, add the keyword",
            "from their names to SORTING_RULES at the top of",
            "PIO_Document_Sorter.py.",
        ]
        note.write_text("\n".join(lines), encoding="utf-8")
    except Exception:  # noqa: BLE001 - a note must never crash the run
        pass


def _summary(source, folders, codes, fields, copied, skipped, ignored,
             merge_status, merged_path, merged_count, merge_excluded, warnings,
             dry_run):
    lines = []
    head = "DRY RUN - nothing was written" if dry_run else "Done"
    lines.append(f"=== PIO Document Sorter - {head} ===")
    lines.append(f"Source     : {source}")
    code_line = f"Folder code: {codes['rev']}  (package {codes['package']}"
    if codes.get("subpart"):
        code_line += f", sub-part {codes['subpart']}"
    code_line += ")"
    lines.append(code_line)
    lines.append(f"Revision   : {codes['rev']} {fields['rev_name']}")
    lines.append(f"Created in : {folders['rev']}")
    lines.append("")

    # WARNINGS first, so they are impossible to miss.
    if warnings:
        lines.append(f"###### WARNINGS ({len(warnings)}) - PLEASE REVIEW ######")
        for w in warnings:
            lines.append(f"  ! {w}")
        lines.append("#" * 44)
    else:
        lines.append("No warnings - everything was sorted and merged cleanly.")
    lines.append("")

    total = sum(len(v) for v in copied.values())
    label = "Would copy" if dry_run else "Copied"
    lines.append(f"{label} {total} file(s):")
    pretty = {
        "drawings_original": "Drawings/Original",
        "reports_original": "Reports/Original",
        "reports_translated": "Reports/Translated",
        "root": "Revision root (doc list / zips)",
        "unsorted": "Revision root, loose - needs a human (see " + UNSORTED_NOTE_NAME + ")",
    }
    for key, names in copied.items():
        lines.append(f"  - {pretty.get(key, key)}: {len(names)}")
    if skipped:
        lines.append(f"  - already existed, skipped: {len(skipped)}")
    if ignored:
        lines.append(
            f"  - not part of the submission, skipped: {len(ignored)} "
            f"(e.g. {ignored[0]})"
        )
    lines.append("")

    if merge_status == "ok":
        lines.append(f"Drawings merged: {merged_count} PDF(s) -> {merged_path.name}")
    elif merge_status == "no-pdfs":
        lines.append("Drawings merged: no PDFs found in Drawings/Original.")
    elif merge_status == "dry-run":
        lines.append(f"Drawings merged: would merge {merged_count} PDF(s).")
    elif merge_status == "no-library":
        lines.append("Drawings merged: SKIPPED (no PDF library installed).")
    elif merge_status == "all-failed":
        lines.append("Drawings merged: FAILED (see warnings above).")
    if merge_excluded:
        shown = ", ".join(merge_excluded[:6]) + (" ..." if len(merge_excluded) > 6 else "")
        lines.append(
            f"Drawings excluded from merge by rule (kept in Drawings/Original "
            f"only): {len(merge_excluded)} ({shown})"
        )
    lines.append("")
    lines.append(
        "Tip: to teach the sorter a new file type, add its keyword to "
        "SORTING_RULES at the top of PIO_Document_Sorter.py."
    )
    return "\n".join(lines)



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
    ("Package code - 2 digits after 400/401, e.g. 01", "pkg_code"),
    ("Build from inside this folder", "placement"),
]


def _gather_fields(source, dest_root):
    """Combine path parsing + code resolution into one editable dict."""
    parsed = parse_source(source)
    warnings = []
    if parsed["stage"] is None:
        parsed["stage"] = "CD"
        warnings.append(
            "Could not tell Definitive/Preliminaire from the path - assuming "
            "CD (Definitive)."
        )
    if parsed["pkg"] is None:
        warnings.append(
            "Could not find a CD-/CP- package number in the path - please enter it."
        )

    info = {
        "pkg_suffix": "", "build_dir": str(dest_root),
        "build_level": "above_package", "subpart_code": None,
        "package_detected": False,
    }
    if parsed["pkg"] is not None:
        info = resolve_placement(
            dest_root, parsed["stage"], parsed["pkg"], parsed["subpart"]
        )
        if not info["package_detected"]:
            warnings.append(
                f"No existing folder for {parsed['stage']}-{parsed['pkg']} was "
                "found in the destination. Enter its 2-digit package code below "
                "(the part after 400/401, e.g. 01). You only need to do this the "
                "first time for each package - after that it is detected."
            )

    fields = {
        "stage": parsed["stage"],
        "pkg": parsed["pkg"] if parsed["pkg"] is not None else "",
        "subpart": parsed["subpart"] if parsed["subpart"] else "",
        "rev_name": parsed["rev_name"],
        "rev_index": parsed["rev_index"],
        "pkg_code": info["pkg_suffix"],
        "placement": info["build_dir"],
        "build_level": info["build_level"],
        "package_detected": info["package_detected"],
        "detected_subpart_code": info.get("subpart_code"),
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
    fields["pkg_code"] = str(raw.get("pkg_code", "")).strip()
    fields["placement"] = str(raw.get("placement", "")).strip()
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


def show_message(summary, is_error=False, title="PIO Document Sorter - result"):
    """Show the final summary in a pop-up if possible, always print it too."""
    print("\n" + summary + "\n")
    try:
        import tkinter as tk
        from tkinter import scrolledtext

        win = tk.Tk()
        win.title(title)
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
    return p.parse_args(argv)


def main(argv=None):
    _ensure_deps()
    args = parse_args(argv if argv is not None else sys.argv[1:])

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
        # keep the internal detection keys; overlay what the user edited.
        merged = dict(fields)
        merged.update(edited)
        fields = merged

    fields = _normalise_fields(fields)
    if not fields["pkg_code"]:
        show_message(
            "No package code was given, so the numbering can't be built.\n\n"
            "Run again and either pick a destination that already contains the "
            "package folder (e.g. one named '... (CD-23)'), or type the 2-digit "
            "package code into the confirmation window.", is_error=True)
        return 1

    summary, warnings = run(source, dest, fields, dry_run=args.dry_run)

    title = "PIO Document Sorter - result"
    if warnings:
        title = f"PIO Document Sorter - finished with {len(warnings)} warning(s)"
    show_message(summary, title=title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
