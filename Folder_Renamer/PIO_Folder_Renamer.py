#!/usr/bin/env python3
"""
PIO Folder Renamer  (one-time clean-up tool)
============================================

Renames an EXISTING ProjectWise folder tree so its numbers match the scheme
used by PIO_Document_Sorter.py:

    400 / 401            stage (Preliminaire / Definitive)        - unchanged
     40101              package   = stage + 2-digit package code
      4010104           sub-part  = package + 2-digit sub-part
       40101040         revision  = sub-part + 1 digit
        401010400       Reports / Drawings
         4010104000     Original / Translated / Combined

It only ever changes the **leading number** of each folder; the descriptive
part of the name (e.g. "Foundation_Piers (CD-23)", "CD-23.1", "R00", "Reports")
is kept exactly as it is.  It never touches, moves, deletes or renames files -
only folders.

How the new numbers are worked out (read from your own tree, nothing guessed)
----------------------------------------------------------------------------
* The 2-digit package code is the package's position under its stage: the
  lowest-numbered package in a stage becomes 00, the next 01, and so on.  That
  is read from the existing 4-digit codes (e.g. under Definitive 4010->00,
  4011->01, ... so CD-23 = 40101), so it matches what you already have.
* The sub-part number is read from the folder name, zero-indexed (CD-23.1 -> 00, CD-23.2 -> 01, ...).
* The revision index is read from the existing number (R00 -> 0, R01 -> 1, the
  re-issue R01A keeps its existing slot).
* Reports/Drawings and Original/Translated/Combined are read from the names.

Safety
------
* It runs as a **PREVIEW by default** - it shows and logs every planned rename
  and changes NOTHING.  You only apply after reviewing (a button in the window,
  or the --apply switch).
* Anything it cannot map confidently (odd or duplicated folders) is **flagged
  and left untouched**, listed for you to fix by hand - it never guesses.
* Renames are applied deepest-first and skip any name that already exists, so
  it can't collide or clobber.  Files are never touched.

Usage
-----
    python PIO_Folder_Renamer.py                 # pick the folder, PREVIEW only
    python PIO_Folder_Renamer.py --root "<...>\\40 ATTESTATION REVIEW"
    python PIO_Folder_Renamer.py --root "<...>" --apply   # actually rename
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Must match the CONFIG block in PIO_Document_Sorter.py.
STAGE_CODES = {"CP": "400", "CD": "401"}
PKG_SUFFIX_WIDTH = 2
SUBPART_WIDTH = 2


# ---------------------------------------------------------------------------
#  Small helpers
# ---------------------------------------------------------------------------

def _lead(name):
    """The leading run of digits in a folder name, or None."""
    m = re.match(r"\s*(\d+)", name)
    return m.group(1) if m else None


def _desc(name):
    """The descriptive part of a folder name (everything after the leading
    number), e.g. '40110 CD-23.1' -> 'CD-23.1'."""
    return re.sub(r"^\s*\d+[\s_]*", "", name).strip() or name


def _stage_of(name):
    """CP / CD / None from a stage folder's name or code."""
    low = name.lower()
    lead = _lead(name)
    if "prelim" in low or lead == STAGE_CODES.get("CP"):
        return "CP"
    if "definit" in low or lead == STAGE_CODES.get("CD"):
        return "CD"
    return None


def _min_child_code(path):
    """Lowest leading number among a folder's direct sub-folders (used to find
    the base each stage's package codes count up from)."""
    vals = []
    try:
        for e in os.scandir(path):
            if e.is_dir():
                lead = _lead(e.name)
                if lead is not None:
                    vals.append(int(lead))
    except OSError:
        pass
    return min(vals) if vals else None


def _rev_code(parent_new, parent_old, lead):
    """New revision code = parent's new code + the revision index read from the
    existing number.  Returns (code, None) or (None, reason)."""
    if not (parent_new and parent_old and lead):
        return None, "missing parent/own number"
    if not lead.startswith(parent_old):
        return None, f"revision number {lead} does not extend its parent {parent_old}"
    rest = lead[len(parent_old):]
    if rest == "":
        rev_index = 0
    elif rest.isdigit():
        rev_index = int(rest)
    else:
        return None, f"cannot read a revision index from '{rest}'"
    if rev_index > 99:
        return None, f"revision index {rev_index} looks wrong"
    return f"{parent_new}{rev_index}", None


# ---------------------------------------------------------------------------
#  Build the rename plan (top-down so each parent's new code is known first)
# ---------------------------------------------------------------------------

def build_plan(root):
    """Return (plan, flags).

    plan  - list of dicts: path, depth, old, new, role, status ('rename' /
            'same'), note.
    flags - list of (path, reason) for folders left untouched for review.
    """
    root = Path(root)
    plan = []
    flags = []

    def recurse(path, parent_role, parent_new, parent_old, stage, which, base):
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
        except OSError as exc:
            flags.append((path, f"could not read folder ({exc})"))
            return
        for entry in entries:
            if not entry.is_dir():
                continue
            p = Path(entry.path)
            name = entry.name
            lead = _lead(name)
            desc = _desc(name)
            depth = len(p.parts)

            role = new_code = note = None
            n_stage, n_which, n_base = stage, None, base

            if parent_role == "root":
                st = _stage_of(name)
                if st:
                    role, n_stage = "stage", st
                    new_code = STAGE_CODES.get(st, lead or "")
                    n_base = _min_child_code(p)
                else:
                    # a wrapper folder (e.g. the project root) - just descend.
                    recurse(p, "root", None, None, None, None, None)
                    continue

            elif parent_role == "stage":
                role = "package"
                if lead is None or base is None:
                    flags.append((p, "package folder has no usable number"))
                    continue
                suffix = int(lead) - base
                if suffix < 0 or suffix > 99:
                    flags.append((p, f"package number {lead} is outside the expected range"))
                    continue
                new_code = f"{STAGE_CODES[stage]}{suffix:0{PKG_SUFFIX_WIDTH}d}"
                m = re.search(r"(?i)(C[DP])[-\s]?\d+", name)
                if m and m.group(1).upper() != stage:
                    note = f"name says {m.group(1).upper()} but it sits under {stage}"

            elif parent_role == "package":
                ms = re.search(r"(?i)C[DP][-\s]?\d+\.(\d+)", name)
                if ms:
                    role = "subpart"
                    new_code = (f"{parent_new}{(int(ms.group(1)) - 1):0{SUBPART_WIDTH}d}"
                                if parent_new else None)
                elif re.search(r"(?i)\bR\d", name):
                    role = "revision"
                    new_code, reason = _rev_code(parent_new, parent_old, lead)
                    if not new_code:
                        flags.append((p, reason)); continue
                else:
                    flags.append((p, "inside a package but is neither a sub-part nor a revision"))
                    continue

            elif parent_role == "subpart":
                if re.search(r"(?i)\bR\d", name):
                    role = "revision"
                    new_code, reason = _rev_code(parent_new, parent_old, lead)
                    if not new_code:
                        flags.append((p, reason)); continue
                else:
                    flags.append((p, "inside a sub-part but is not a revision"))
                    continue

            elif parent_role == "revision":
                low = name.lower()
                if "report" in low:
                    role, n_which = "category", "reports"
                    new_code = f"{parent_new}0"
                elif "drawing" in low:
                    role, n_which = "category", "drawings"
                    new_code = f"{parent_new}1"
                else:
                    flags.append((p, "inside a revision but is not Reports or Drawings"))
                    continue

            elif parent_role == "category":
                low = name.lower()
                if "translat" in low:
                    digit = "1"
                elif "combin" in low:
                    digit = "1"
                elif "original" in low or "individual" in low:
                    digit = "0"
                else:
                    flags.append((p, "inside Reports/Drawings but is not Original/Translated/Combined"))
                    continue
                role = "variant"
                new_code = f"{parent_new}{digit}"
                if "individual" in low:
                    note = "non-standard name 'Individual' (the script uses 'Original')"

            else:  # under a variant - should only contain files
                flags.append((p, f"unexpected folder nested under a {parent_role} folder"))
                continue

            if not new_code:
                flags.append((p, "could not work out a new number"))
                continue

            new_name = f"{new_code} {desc}"
            plan.append({
                "path": p, "depth": depth, "old": name, "new": new_name,
                "role": role, "note": note,
                "status": "rename" if new_name != name else "same",
            })
            recurse(p, role, new_code, lead, n_stage, n_which, n_base)

    # The selected folder is normally the container of "400 ..." and "401 ...",
    # but allow picking a single stage folder directly too.
    st = _stage_of(root.name)
    if st:
        recurse(root, "stage", STAGE_CODES.get(st, _lead(root.name) or ""),
                _lead(root.name), st, None, _min_child_code(root))
    else:
        recurse(root, "root", None, None, None, None, None)
    return plan, flags


# ---------------------------------------------------------------------------
#  Apply (deepest-first, collision-safe, folders only)
# ---------------------------------------------------------------------------

def apply_plan(plan):
    """Perform the renames.  Returns (done, collisions, errors)."""
    renames = [e for e in plan if e["status"] == "rename"]
    renames.sort(key=lambda e: e["depth"], reverse=True)  # children before parents
    done, collisions, errors = 0, [], []
    for e in renames:
        old = Path(e["path"])
        new = old.with_name(e["new"])
        try:
            if new.exists() and os.path.normcase(str(new)) != os.path.normcase(str(old)):
                collisions.append((old, new))
                continue
            os.rename(old, new)
            done += 1
        except OSError as exc:
            errors.append((old, str(exc)))
    return done, collisions, errors


# ---------------------------------------------------------------------------
#  Reporting
# ---------------------------------------------------------------------------

def build_report(root, plan, flags, applied=None):
    renames = [e for e in plan if e["status"] == "rename"]
    same = [e for e in plan if e["status"] == "same"]
    notes = [e for e in plan if e.get("note")]
    lines = []
    head = "APPLIED" if applied is not None else "PREVIEW - nothing was changed"
    lines.append(f"=== PIO Folder Renamer - {head} ===")
    lines.append(f"Root: {root}")
    lines.append("")
    lines.append(f"Folders to rename : {len(renames)}")
    lines.append(f"Already correct   : {len(same)}")
    lines.append(f"Flagged (left as-is, need a human): {len(flags)}")
    if notes:
        lines.append(f"Renamed but worth a look: {len(notes)}")
    if applied is not None:
        done, collisions, errors = applied
        lines.append("")
        lines.append(f"RESULT: renamed {done}, "
                     f"skipped {len(collisions)} (name already existed), "
                     f"errors {len(errors)}")
        for old, new in collisions:
            lines.append(f"  ! SKIPPED (target exists): {old.name}  ->  {new.name}")
        for old, exc in errors:
            lines.append(f"  ! ERROR: {old}  ({exc})")
    lines.append("")

    if flags:
        lines.append(f"###### FLAGGED ({len(flags)}) - left untouched, please review ######")
        for p, reason in flags:
            lines.append(f"  ! {p}\n      {reason}")
        lines.append("#" * 60)
        lines.append("")

    if notes:
        lines.append("--- renamed, but check these ---")
        for e in notes:
            lines.append(f"  ~ {e['old']}  ->  {e['new']}\n      {e['note']}")
        lines.append("")

    lines.append(f"--- {'renames applied' if applied is not None else 'planned renames'} "
                 f"({len(renames)}) ---")
    for e in sorted(renames, key=lambda e: str(e["path"]).lower()):
        lines.append(f"  {e['old']}  ->  {e['new']}")
    return "\n".join(lines)



# ---------------------------------------------------------------------------
#  UI
# ---------------------------------------------------------------------------

def pick_folder(title):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        path = filedialog.askdirectory(title=title)
        root.destroy()
        return path or None
    except Exception:  # noqa: BLE001
        return None


def confirm_apply_gui(summary, count):
    """Show the preview; return True if the user clicks APPLY."""
    try:
        import tkinter as tk
        from tkinter import scrolledtext, messagebox
    except Exception:  # noqa: BLE001
        print(summary)
        return False

    win = tk.Tk()
    win.title("PIO Folder Renamer - PREVIEW")
    tk.Label(
        win, justify="left", fg="#b00000",
        text=("PREVIEW - nothing has been changed yet.\n"
              f"{count} folder(s) would be renamed. Review below, then choose."),
    ).pack(padx=10, pady=(10, 4), anchor="w")
    box = scrolledtext.ScrolledText(win, width=100, height=30, wrap="none")
    box.insert("1.0", summary)
    box.configure(state="disabled")
    box.pack(padx=10, pady=6)

    state = {"apply": False}

    def on_apply():
        if messagebox.askyesno(
            "Confirm",
            f"Rename {count} folder(s) now?\n\n"
            "Files are not touched. This changes folder names on disk.",
        ):
            state["apply"] = True
            win.destroy()

    bar = tk.Frame(win); bar.pack(pady=(0, 10))
    tk.Button(bar, text="Close (no changes)", width=20,
              command=win.destroy).pack(side="left", padx=6)
    tk.Button(bar, text="APPLY renames", width=20,
              command=on_apply).pack(side="left", padx=6)
    win.mainloop()
    return state["apply"]


def show_result_gui(summary):
    try:
        import tkinter as tk
        from tkinter import scrolledtext
    except Exception:  # noqa: BLE001
        print(summary)
        return
    win = tk.Tk()
    win.title("PIO Folder Renamer - done")
    box = scrolledtext.ScrolledText(win, width=100, height=30, wrap="none")
    box.insert("1.0", summary)
    box.configure(state="disabled")
    box.pack(padx=10, pady=10)
    tk.Button(win, text="Close", width=14, command=win.destroy).pack(pady=(0, 10))
    win.mainloop()


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

def parse_args(argv):
    p = argparse.ArgumentParser(description="Rename an existing PIO folder tree to the new scheme.")
    p.add_argument("--root", help="The folder that contains '400 ...' and '401 ...'.")
    p.add_argument("--apply", action="store_true",
                   help="Actually rename (default is a preview that changes nothing).")
    p.add_argument("--no-gui", action="store_true", help="Command line only.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    use_gui = not args.no_gui

    root = args.root or (pick_folder(
        "Select the folder that contains '400 ...' and '401 ...'") if use_gui else None)
    if not root:
        print("No folder selected - nothing to do.")
        return 1
    if not Path(root).is_dir():
        print(f"Not a folder: {root}")
        return 1

    plan, flags = build_plan(root)
    renames = [e for e in plan if e["status"] == "rename"]
    preview = build_report(root, plan, flags)

    if not renames and not flags:
        print(preview)
        show_result_gui(preview + "\n\nEverything already matches - nothing to do.")
        return 0

    # Decide whether to apply.
    do_apply = args.apply
    if not do_apply and use_gui:
        do_apply = confirm_apply_gui(preview, len(renames))
    elif not do_apply:
        # CLI preview only
        print(preview)
        print(f"\nPREVIEW only. Re-run with --apply to perform the {len(renames)} rename(s).")
        return 0

    if not do_apply:
        print("Closed without changes.")
        return 0

    result = apply_plan(plan)
    final = build_report(root, plan, flags, applied=result)
    print(final)
    show_result_gui(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
