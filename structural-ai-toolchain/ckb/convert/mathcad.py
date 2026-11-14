"""Mathcad Prime worksheets (.mcdx) -> machine-readable statements.

The worksheet is converted to Python by ``mcad2py`` (open source, MIT), which
keeps Mathcad's units by using ``pint``.  The Python then goes through the
ordinary Python converter.  Two things are added here:

* the descriptive text Mathcad shows next to each equation (matched by its
  position on the page) and the headings above it, and
* a check against the results Mathcad itself stored in the file, so we know
  the conversion reproduces the worksheet without opening Mathcad.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .. import units as U
from ..ir import SourceDocument, close, file_sha256
from .python_src import ConversionError, convert_source, find_clause

_REGION = re.compile(r"<region\b([^>]*)>\s*<(\w+)\b([^>]*)", re.S)
_ATTR = re.compile(r'([\w\-:]+)="([^"]*)"')
_MARK = re.compile(r'^mcdx region (\d+)(?:,\s*"(.*?)"\s*->\s*(\w+))?\s*$')
_RESULT = re.compile(r'<resultData result-id="(\d+)"[^>]*?(?:/>|>(.*?)</resultData>)', re.S)


def _geometry(worksheet_xml: str) -> dict[int, dict]:
    """Position and kind of every region, and the stored-result id of math regions."""
    out = {}
    for m in _REGION.finditer(worksheet_xml):
        attrs = dict(_ATTR.findall(m.group(1)))
        inner = dict(_ATTR.findall(m.group(3)))
        try:
            rid = int(attrs["region-id"])
        except (KeyError, ValueError):
            continue
        out[rid] = {"kind": m.group(2), "top": float(attrs.get("top", 0) or 0),
                    "left": float(attrs.get("left", 0) or 0),
                    "height": float(attrs.get("actualHeight", 0) or 16),
                    "result": int(inner["resultRef"]) if "resultRef" in inner else None}
    return out


def _stored_results(result_xml: str) -> dict[int, float | str]:
    out: dict[int, float | str] = {}
    for rid, body in _RESULT.findall(result_xml or ""):
        if not body:
            continue
        m = re.search(r"<ml:real>([^<]+)</ml:real>", body)
        if m and body.count("<ml:real>") == 1:
            try:
                out[int(rid)] = float(m.group(1))
            except ValueError:
                pass
            continue
        m = re.search(r"<ml:str[^>]*>([^<]*)</ml:str>", body)
        if m:
            out[int(rid)] = m.group(1)
    return out


def _patch(source: str) -> str:
    """Repair generated code that is not valid Python (degree sign as a unit name)."""
    return re.sub(r"\bureg\.°", "ureg.degree", source)


def convert_mathcad(path: Path) -> SourceDocument:
    path = Path(path)
    try:
        import mcad2py
    except ImportError as exc:                                   # pragma: no cover
        raise ConversionError("mcad2py is not installed (pip install mcad2py)") from exc
    try:
        source = _patch(mcad2py.convert_file(path, fmt="py", trace_source=True))
    except Exception as exc:                                     # noqa: BLE001
        raise ConversionError(f"mcad2py could not convert the worksheet: {exc}") from exc
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        worksheet = z.read("mathcad/worksheet.xml").decode("utf-8-sig", "replace")
        results = z.read("mathcad/result.xml").decode("utf-8-sig", "replace") \
            if "mathcad/result.xml" in names else ""
        core = z.read("docProps/core.xml").decode("utf-8-sig", "replace") \
            if "docProps/core.xml" in names else ""
    geo = _geometry(worksheet)
    stored = _stored_results(results)

    # --- read the region markers mcad2py leaves in the generated code -------
    regions: list[dict] = []
    for no, line in enumerate(source.splitlines(), 1):
        s = line.strip()
        m = _MARK.match(s[1:].strip()) if s.startswith("#") else None
        if m:
            regions.append({"id": int(m.group(1)), "raw": m.group(2) or "", "text": [],
                            "lines": [], "marker": no})
        elif regions:
            if s.startswith("#"):
                regions[-1]["text"].append(s[1:].strip())
            elif s:
                regions[-1]["lines"].append(no)

    # --- pair each equation with the text on the same row; other text = headings
    math = [r for r in regions if r["lines"]]
    texts = [r for r in regions if not r["lines"] and r["text"]]
    label_of: dict[int, dict] = {}
    used: set[int] = set()
    # a label starts on the same row as its equation (its top is within 20 px);
    # pairs are taken closest first, and equations sharing a row share its label
    pairs = []
    for r in math:
        g = geo.get(r["id"])
        for t in texts:
            tg = geo.get(t["id"])
            if g and tg and tg["left"] < g["left"] and abs(tg["top"] - g["top"]) <= 20:
                pairs.append((abs(tg["top"] - g["top"]), r["id"], t))
    for _, rid, t in sorted(pairs, key=lambda p: (p[0], p[1])):
        if rid in label_of:
            continue
        if t["id"] in used:
            owner = next(k for k, v in label_of.items() if v is t)
            if abs(geo[owner]["top"] - geo[rid]["top"]) > 2:
                continue
        label_of[rid] = t
        used.add(t["id"])

    info_by_line: dict[int, dict] = {}
    main, sub, sub_clause = "", "", ""
    for r in regions:
        if not r["lines"]:
            if r["id"] in used or not r["text"]:
                continue
            g = geo.get(r["id"])
            text = " ".join(r["text"])
            if len(text) > 160 or (g and g["kind"] != "text") or r["text"][0].rstrip().endswith(":"):
                continue                                         # a paragraph or a stray label
            clause = find_clause(text)
            title = re.sub(r"\s*\(Acc\. to[^)]*\)+\s*", " ", text).strip() or text
            if clause:
                sub, sub_clause = title, clause
            else:
                main, sub, sub_clause = title, "", ""
            continue
        lab = label_of.get(r["id"])
        label_text = " ".join(lab["text"]) if lab else ""
        clause = find_clause(label_text) or sub_clause
        label = re.sub(r"\s*\(Acc\. to[^)]*\)+\s*", " ", label_text).strip().rstrip(":").strip()
        case = ""
        m = re.search(r"\bphase\s*(\d+)", main, re.I)
        if m:
            case = f"phase {m.group(1)}"
        info = {"name": r["raw"], "label": label, "clause": clause,
                "section": [h for h in (main, sub) if h], "case": case, "group": main,
                "loc": f"region {r['id']}"}
        for ln in r["lines"]:
            info_by_line[ln] = info

    def annotate(line, _above):
        return dict(info_by_line.get(line, {}))

    doc = convert_source(source, path.name, "mathcad", sha256=file_sha256(path),
                         converter=f"mcad2py {mcad2py.__version__} + isolated run",
                         annotate=annotate)
    doc.meta["units"] = "embedded"
    for tag, key in (("dc:creator", "author"), ("cp:lastModifiedBy", "modified_by"),
                     ("dcterms:modified", "modified")):
        m = re.search(rf"<{tag}[^>]*>([^<]*)</{tag}>", core)
        if m:
            doc.meta[key] = m.group(1)
    header = [ln[1:].strip() for ln in source.splitlines()[:12]
              if ln.startswith("# ") and ":" in ln and "image" not in ln]
    if header:
        doc.meta["header"] = header

    # --- compare with the results Mathcad stored in the file ----------------
    checked = agree = 0
    for st in doc.statements:
        m = re.match(r"region (\d+)", st.loc)
        g = geo.get(int(m.group(1))) if m else None
        if not g or g["result"] is None or g["result"] not in stored:
            continue
        shown = stored[g["result"]]
        ours = st.value                       # value from running the converted code
        if isinstance(shown, float) and isinstance(ours, (int, float)):
            try:
                factor = U.parse_unit(st.unit).factor if st.unit else 1.0
            except U.UnitError:
                factor = 1.0
            source_value = shown * factor
        else:
            source_value = shown
        checked += 1
        if close(ours, source_value, rel=1e-6):
            agree += 1
        else:
            doc.issues.append(f"{st.loc}: {st.name}: converted code gives {ours!r}, "
                              f"Mathcad stored {source_value!r}")
            st.note = (st.note + "; " if st.note else "") + "differs from the result stored by Mathcad"
        st.value = source_value
    doc.meta["stored_results"] = {"compared": checked, "agree": agree}
    from ..ir import recompute
    recompute(doc)
    return doc
