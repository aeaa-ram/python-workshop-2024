#!/usr/bin/env python3
"""Logic checks for PIO_Document_Sorter (kept out of the main script so that
file stays free of example numbers).

Run:  python test_pio_sorter.py
"""

import tempfile
from pathlib import Path

import PIO_Document_Sorter as s


def main():
    failures = []

    def check(label, got, want):
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    # --- Path parsing: a package WITH a sub-part --------------------------
    src = r"C:\Users\X\...\De_Conception\Definitive\CD-23\23.4\00_R00"
    p = s.parse_source(src)
    check("subpart.stage", p["stage"], "CD")
    check("subpart.pkg", p["pkg"], 23)
    check("subpart.subpart", p["subpart"], 4)
    check("subpart.rev_name", p["rev_name"], "R00")
    check("subpart.rev_index", p["rev_index"], 0)

    # Codes are derived from a base code (as detection would supply it) - the
    # script never computes the base code from the package number.
    c = s.compute_codes("40113", p["rev_index"])
    check("subpart.rev", c["rev"], "401130")
    check("subpart.reports", c["reports"], "4011300")
    check("subpart.drawings", c["drawings"], "4011301")
    check("subpart.rep_orig", c["rep_orig"], "40113000")
    check("subpart.dwg_orig", c["dwg_orig"], "40113010")
    check("subpart.dwg_comb", c["dwg_comb"], "40113011")

    # --- Path parsing: a package WITHOUT a sub-part (the "extra 0" fix) ----
    p2 = s.parse_source(r"C:\X\Definitive\CD-27\00_R00")
    check("nosub.pkg", p2["pkg"], 27)
    check("nosub.subpart", p2["subpart"], None)
    # A no-sub-part base code is one digit shorter, so its tree is shallower.
    c2 = s.compute_codes("4015", p2["rev_index"])
    check("nosub.rev", c2["rev"], "40150")
    check("nosub.reports", c2["reports"], "401500")

    # --- Preliminaire -> CP, alternate revision label ---------------------
    p3 = s.parse_source(r"C:\X\Preliminaire\CP-24\24.2\01_R01A")
    check("prelim.stage", p3["stage"], "CP")
    check("prelim.pkg", p3["pkg"], 24)
    check("prelim.subpart", p3["subpart"], 2)
    check("prelim.rev_name", p3["rev_name"], "R01A")
    check("prelim.rev_index", p3["rev_index"], 1)

    # --- File classification (key is the first item of the returned pair) --
    def key(name):
        return s.classify_file(name)[0]

    def note(name):
        return s.classify_file(name)[1]

    check("cls.rpt", key("DEJV-11000-1200-RPT-00001.pdf"), "reports_original")
    check("cls.rpt_en", key("DEJV-11000-1200-RPT-00001_EN.pdf"), "reports_translated")
    check("cls.spc", key("DEJV-SPC-9.pdf"), "reports_original")
    check("cls.pla", key("DEJV-ODA-PLA-0001.pdf"), "drawings_original")
    check("cls.boa", key("DEJV-ODA-BOA-0001.pdf"), "drawings_original")
    check("cls.xlsx", key("tracking list.xlsx"), "root")
    check("cls.unknown", key("random notes.docx"), None)
    # A name that matches both a report and a drawing keyword is flagged.
    check("cls.ambig_key", key("ODA-PLA-and-RPT-mix.pdf"), "drawings_original")
    check("cls.ambig_note", note("ODA-PLA-and-RPT-mix.pdf") is not None, True)
    check("cls.clean_note", note("DEJV-RPT-1.pdf"), None)

    # --- Base-code detection from existing folders (fully generic) ---------
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "401 Definitive" / "4011 Foundations_Piers (CD-23)"
         / "40113 CD-23.4").mkdir(parents=True)
        # exact sub-part folder is found
        r = s.resolve_base_code(root, "CD", 23, 4)
        check("detect.sub.code", r["base_code"], "40113")
        check("detect.sub.flag", r["package_detected"], True)
        # package folder found, sub-part folder absent -> package code + (sub-1)
        r2 = s.resolve_base_code(root, "CD", 23, 1)
        check("detect.firstsub.code", r2["base_code"], "40110")
        # package with no sub-part -> the package code itself
        r3 = s.resolve_base_code(root, "CD", 23, None)
        check("detect.pkg.code", r3["base_code"], "4011")
        # nothing matching -> empty code, user must supply it
        r4 = s.resolve_base_code(root, "CD", 99, None)
        check("detect.none.code", r4["base_code"], "")
        check("detect.none.flag", r4["package_detected"], False)

    if failures:
        print("TESTS FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print(f"ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
