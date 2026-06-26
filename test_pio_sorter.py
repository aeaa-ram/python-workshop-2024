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

    # Codes follow the convention: stage 401, a 2-digit package code, a 2-digit
    # sub-part, then one digit per level below.  The package code ("01") is what
    # detection reads or the user types - it is never computed from "23".
    c = s.derive_codes("CD", "01", subpart=4, rev_index=0)
    check("subpart.package", c["package"], "40101")
    check("subpart.subpart_code", c["subpart"], "4010104")
    check("subpart.rev", c["rev"], "40101040")
    check("subpart.reports", c["reports"], "401010400")
    check("subpart.drawings", c["drawings"], "401010401")
    check("subpart.rep_orig", c["rep_orig"], "4010104000")
    check("subpart.rep_trans", c["rep_trans"], "4010104001")
    check("subpart.dwg_orig", c["dwg_orig"], "4010104010")
    check("subpart.dwg_comb", c["dwg_comb"], "4010104011")

    # A typed package code of "1" is forgiven and padded to two digits.
    check("subpart.pad", s.derive_codes("CD", "1", 4, 0)["package"], "40101")

    # --- Path parsing: a package WITHOUT a sub-part -----------------------
    p2 = s.parse_source(r"C:\X\Definitive\CD-27\00_R00")
    check("nosub.pkg", p2["pkg"], 27)
    check("nosub.subpart", p2["subpart"], None)
    # No sub-part -> the sub-part level is skipped, so the tree is one shorter.
    c2 = s.derive_codes("CD", "05", subpart=None, rev_index=0)
    check("nosub.package", c2["package"], "40105")
    check("nosub.subpart_none", c2["subpart"], None)
    check("nosub.rev", c2["rev"], "401050")
    check("nosub.reports", c2["reports"], "4010500")

    # --- Preliminaire -> stage code 400, alternate revision label ---------
    p3 = s.parse_source(r"C:\X\Preliminaire\CP-24\24.2\01_R01A")
    check("prelim.stage", p3["stage"], "CP")
    check("prelim.pkg", p3["pkg"], 24)
    check("prelim.subpart", p3["subpart"], 2)
    check("prelim.rev_name", p3["rev_name"], "R01A")
    check("prelim.rev_index", p3["rev_index"], 1)
    c3 = s.derive_codes("CP", "00", subpart=None, rev_index=0)
    check("prelim.package", c3["package"], "40000")
    check("prelim.rev", c3["rev"], "400000")

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

    # --- Package-code detection from existing folders (fully generic) ------
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "401 Definitive" / "40101 Foundations_Piers (CD-23)"
         / "4010104 CD-23.4").mkdir(parents=True)

        # Package folder found -> its 2-digit code is read out of the name.
        r = s.resolve_placement(root, "CD", 23, 4)
        check("detect.suffix", r["pkg_suffix"], "01")
        check("detect.flag", r["package_detected"], True)
        # The existing sub-part folder is found and reused.
        check("detect.subdir", str(r["subpart_dir"]).endswith("4010104 CD-23.4"), True)
        check("detect.subcode", r["subpart_code"], "4010104")

        # Same package, no sub-part asked for -> still detects the code.
        r2 = s.resolve_placement(root, "CD", 23, None)
        check("detect.nosub.suffix", r2["pkg_suffix"], "01")
        check("detect.nosub.flag", r2["package_detected"], True)

        # An unknown package -> nothing detected, user must supply the code.
        r3 = s.resolve_placement(root, "CD", 99, None)
        check("detect.none.suffix", r3["pkg_suffix"], "")
        check("detect.none.flag", r3["package_detected"], False)
        # ...and the new folder would be created under the stage folder.
        check("detect.none.parent",
              str(r3["package_parent"]).endswith("401 Definitive"), True)

    if failures:
        print("TESTS FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
