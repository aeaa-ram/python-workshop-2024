"""PDF calculations -> machine-readable statements.

A PDF is a print: the formulas are drawings, not data.  What a PDF does state
reliably is every *printed quantity* - its name, the value and the unit - and
the text and code reference next to it.  Those are read here from the
position and size of the characters (subscripts are smaller and lower,
results follow the last ``=`` on the equation's baseline).

Printed quantities are used as benchmarks: logic distilled from other sources
must reproduce the printed output from the printed input.  Recovering the
formulas themselves from a print needs a vision model (see ``scan.py``).
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import units as U
from ..ir import SourceDocument, Statement, file_sha256
from .python_src import ConversionError, find_clause

_DEF = "≔"
_BARS = "―─—‒–"
_NUM = re.compile(r"^\s*([-−]?\d+(?:[.,]\d+)?)(?:\s*[⋅·×x]\s*10\s*\^\s*([-−]?\d+))?\s*(.*)$")


def _mid(ch) -> float:
    return (ch["top"] + ch["bottom"]) / 2


def _join(chars: list[dict], gap: float = 1.6) -> str:
    """Characters in reading order as text; a gap becomes a space."""
    out, prev = [], None
    for ch in sorted(chars, key=lambda c: c["x0"]):
        if prev is not None and ch["x0"] - prev["x1"] > gap:
            out.append(" ")
        out.append(ch["text"])
        prev = ch
    return "".join(out)


def _unit_text(raw: str) -> str:
    s = raw.strip().replace("⋅", "·").replace(" · ", "·").replace("· ", "·").replace(" ·", "·")
    s = re.sub(r"\s*\^\s*", "^", s)
    s = re.sub(r"\s+", " ", s).strip(" ·")
    if not s:
        return ""
    try:
        return U.parse_unit(s.replace(" ", "")).text
    except U.UnitError:
        return ""


def _page_statements(page, page_no: int, doc: SourceDocument, section: list[str]) -> list[Statement]:
    chars = [c for c in page.chars if c["text"].strip()]
    if not chars:
        return []
    defs = sorted((c for c in chars if c["text"] == _DEF), key=lambda c: (round(c["top"]), c["x0"]))
    main = max((c["size"] for c in defs), default=10.0)
    math_fonts: set[str] = set()
    found: list[dict] = []

    for d in defs:
        ym = _mid(d)
        band = [c for c in chars if abs(_mid(c) - ym) <= 3.5 and c["size"] >= 0.85 * d["size"]]
        subs = [c for c in chars if c["size"] < 0.85 * d["size"] and 1.0 <= c["top"] - d["top"] <= 9.5]
        # ---- name: walk left from the definition sign -----------------------
        left = sorted((c for c in band + subs if c["x1"] <= d["x0"] + 0.6 and c is not d),
                      key=lambda c: -c["x1"])
        name_chars, edge = [], d["x0"]
        for c in left:
            if edge - c["x1"] > 3.2 or c["text"] in "=+-−⋅·,()⎛⎜⎝⎞⎟⎠":
                break
            name_chars.append(c)
            edge = c["x0"]
        if not name_chars:
            continue
        base = _join([c for c in name_chars if c["size"] >= 0.85 * d["size"]], gap=99).replace(" ", "")
        sub = _join([c for c in name_chars if c["size"] < 0.85 * d["size"]], gap=99).replace(" ", "")
        if not base:
            continue
        found.append({"d": d, "ym": ym, "x_name": edge, "name": f"{base}_{sub}" if sub else base,
                      "band": band})
        math_fonts.update(c["fontname"] for c in name_chars)
        math_fonts.add(d["fontname"])

    statements: list[Statement] = []
    for i, f in enumerate(found):
        d, ym = f["d"], f["ym"]
        # the equation ends where the next one on the same row starts
        limit = min((g["x_name"] for g in found if g is not f and abs(g["ym"] - ym) <= 3.5
                     and g["x_name"] > d["x1"]), default=page.width)
        # ... or at a wide gap: a separate region printed further right on the row
        edge = d["x1"]
        for c in sorted((c for c in chars if abs(_mid(c) - ym) <= 14 and d["x1"] <= c["x0"] < limit),
                        key=lambda c: c["x0"]):
            if c["x0"] - edge > 13:
                limit = c["x0"]
                break
            edge = max(edge, c["x1"])
        rhs = [c for c in f["band"] if d["x1"] - 0.5 <= c["x0"] < limit - 0.5]
        math_fonts.update(c["fontname"] for c in rhs)
        eqs = [c for c in rhs if c["text"] == "="]
        start = eqs[-1]["x1"] if eqs else d["x1"]
        tail = [c for c in rhs if c["x0"] >= start - 0.3]
        # raised small characters are exponents (mm², 10⁻³)
        raised = [c for c in chars if start <= c["x0"] < limit and c["size"] < 0.85 * d["size"]
                  and -8.0 <= c["top"] - d["top"] <= 0.5]
        parts, prev, pending = [], None, False
        seq = sorted([(c, False) for c in tail] + [(c, True) for c in raised], key=lambda p: p[0]["x0"])
        for c, up in seq:
            if prev is not None and c["x0"] - prev["x1"] > 1.6 and not up:
                parts.append(" ")
            if up and not pending:
                parts.append("^")
            pending = up
            parts.append(c["text"])
            prev = c
        text = "".join(parts).strip()
        value, unit, prec = None, "", 0.0
        m = re.match(r"^[“\"”]\s*(.*?)\s*[”\"“]$", text)
        if m and eqs:
            value = m.group(1)
        else:
            m = _NUM.match(text)
            if m and (eqs or True):
                num = m.group(1).replace("−", "-").replace(",", ".")
                rest = m.group(3)
                decimals = len(num.split(".")[1]) if "." in num else 0
                value = float(num)
                prec = 0.5 * 10 ** (-decimals)
                if m.group(2):
                    scale = 10 ** int(m.group(2).replace("−", "-"))
                    value, prec = float(f"{value * scale:.12g}"), prec * scale
                bar = rest.lstrip()[:1]
                if bar and bar in _BARS:
                    # unit printed as a fraction: numerator above, denominator below the bar
                    bars = [c for c in tail if c["text"] in _BARS]
                    x0, x1 = min(c["x0"] for c in bars) - 1, max(c["x1"] for c in bars) + 1
                    over = [c for c in chars if x0 <= (c["x0"] + c["x1"]) / 2 <= x1
                            and 2 < ym - _mid(c) <= 13 and c["text"] not in _BARS]
                    under = [c for c in chars if x0 <= (c["x0"] + c["x1"]) / 2 <= x1
                             and 2 < _mid(c) - ym <= 17 and c["text"] not in _BARS]
                    top = _join(over, gap=99).replace(" ", "")
                    letters = _join([c for c in under if not c["text"].isdigit()], gap=99).replace(" ", "")
                    power = _join([c for c in under if c["text"].isdigit()], gap=99).replace(" ", "")
                    unit = _unit_text(f"{top}/{letters}{'^' + power if power else ''}")
                    after = rest.lstrip().lstrip(_BARS).strip()
                    if after:                                   # "10 kN/m² · W" is not a plain value
                        value = None
                else:
                    unit = _unit_text(rest.lstrip("⋅· "))
                    if rest.strip() and not unit and not eqs:
                        value = None                            # a formula without a result
                    elif rest.strip() and not unit:
                        doc.issues.append(f"page {page_no}: unit of {f['name']} not read ({rest.strip()!r})")
        if value is None:
            continue
        f["has_result"] = bool(eqs)
        st = Statement(id=f"p{page_no}:{len(statements) + 1}", name=f["name"], kind="printed",
                       value=value, unit=unit, loc=f"page {page_no}",
                       raw=("= " if eqs else "≔ ") + text)
        st.note = "printed result" if eqs else "printed input"
        st.precision = prec
        f["st"] = st
        statements.append(st)

    # ---- text lines (everything not set in a maths font) --------------------
    text_chars = [c for c in chars if c["fontname"] not in math_fonts]
    lines: list[dict] = []
    for c in sorted(text_chars, key=lambda c: (round(c["top"]), c["x0"])):
        for ln in lines:
            if abs(ln["top"] - c["top"]) <= 2.2:
                ln["chars"].append(c)
                break
        else:
            lines.append({"top": c["top"], "chars": [c]})
    for ln in lines:
        ln["text"] = " ".join(_join(ln["chars"], gap=1.2).split())
        ln["x0"] = min(c["x0"] for c in ln["chars"])
        ln["bottom"] = max(c["bottom"] for c in ln["chars"])
    lines = [ln for ln in sorted(lines, key=lambda l: l["top"])
             if len(ln["text"]) >= 3 and not re.match(r"^(Page \d+ of \d+|Project( no\.)?:)", ln["text"])
             and re.search(r"[A-Za-z]{2}", ln["text"])]
    blocks: list[list[dict]] = []
    for ln in lines:
        if blocks and ln["top"] - blocks[-1][-1]["top"] <= 13.5 and abs(ln["x0"] - blocks[-1][0]["x0"]) < 30:
            blocks[-1].append(ln)
        else:
            blocks.append([ln])

    # a text block level with an equation is its label; other blocks are headings
    items = []
    for b in blocks:
        top, bottom = b[0]["top"], b[-1]["bottom"]
        owners = [f for f in found if "st" in f and top - 4 <= f["ym"] <= bottom + 4
                  and b[0]["x0"] < f["x_name"]]
        items.append((top, "block", b, owners))
    order = sorted(items, key=lambda it: it[0])
    labelled: set[str] = set()
    events = [(it[0], 0, it) for it in order] + [(f["d"]["top"], 1, f) for f in found if "st" in f]
    main_h, sub_h, sub_clause = (section + ["", ""])[:2] + [""]
    for _, kind, obj in sorted(events, key=lambda e: (e[0], e[1])):
        if kind == 0:
            _, _, b, owners = obj
            plain = [ln["text"] for ln in b if not ln["text"].startswith("(")]
            paren = " ".join(ln["text"] for ln in b if ln["text"].startswith("("))
            if owners:
                for f in owners:
                    st = f["st"]
                    st.label = " ".join(plain).rstrip(":").strip()
                    st.clause = find_clause(paren) or find_clause(st.label)
                    labelled.add(st.id)
            elif plain and len(" ".join(plain)) <= 120 and not plain[-1].endswith(":"):
                clause = find_clause(paren)
                if len(plain) >= 2:
                    main_h, sub_h, sub_clause = plain[0], plain[-1], clause
                elif clause:
                    sub_h, sub_clause = plain[0], clause
                else:
                    main_h, sub_h, sub_clause = plain[0], "", ""
        else:
            st = obj["st"]
            st.section = [h for h in (main_h, sub_h) if h]
            if not st.clause:
                st.clause = sub_clause
            m = re.search(r"\bphase\s*(\d+)", main_h, re.I)
            st.case = f"phase {m.group(1)}" if m else ""
            st.group = main_h
    section[:] = [main_h, sub_h]
    return statements


def convert_pdf(path: Path) -> SourceDocument:
    path = Path(path)
    try:
        import pdfplumber
    except ImportError as exc:                                   # pragma: no cover
        raise ConversionError("pdfplumber is not installed") from exc
    import logging
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    doc = SourceDocument(name=path.name, kind="pdf", sha256=file_sha256(path))
    doc.meta["units"] = "declared"
    section: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            doc.converter = f"pdfplumber {pdfplumber.__version__} (text layer, character positions)"
            doc.meta["pages"] = len(pdf.pages)
            info = pdf.metadata or {}
            for k_src, k in (("Author", "author"), ("Producer", "producer"), ("CreationDate", "created")):
                if info.get(k_src):
                    doc.meta[k] = str(info[k_src])
            empty = 0
            for no, page in enumerate(pdf.pages, 1):
                if not page.chars:
                    empty += 1
                    continue
                sts = _page_statements(page, no, doc, section)
                if not sts:
                    sts = _plain_text_statements(page, no)
                # a region cut by the page break is printed on both pages: keep one
                tail = [(s.name, s.value) for s in doc.statements[-4:]]
                doc.statements.extend(s for i, s in enumerate(sts) if not (i < 4 and (s.name, s.value) in tail))
    except ConversionError:
        raise
    except Exception as exc:                                     # noqa: BLE001
        raise ConversionError(f"PDF cannot be read: {exc}") from exc
    if empty:
        doc.issues.append(f"{empty} page(s) have no text layer (scanned); they need the vision "
                          "transcription path")
    if not doc.statements and empty == doc.meta.get("pages"):
        doc.meta["scanned"] = True
    doc.meta["note"] = ("printed names, values, units, text and code references; formulas are "
                        "not recovered from a print without a vision model")
    return doc


_PLAIN = re.compile(
    r"(?<![\w.])([A-Za-zΑ-Ωα-ω][\w.,]{0,14}?)\s*(?:=|≔|:=)\s*(?:[^=\n]*=\s*)?"
    r"([-−]?\d+(?:[.,]\d+)?)\s*([A-Za-zµμ°%‰][A-Za-z0-9/²³⁴·.^]{0,9})?(?=\s{2,}|\s*$|\s*[;,)])")


def _plain_text_statements(page, page_no: int) -> list[Statement]:
    """Fallback for prints that are ordinary text: ``VRd,c = 157.1 kN``."""
    out = []
    text = page.extract_text() or ""
    for line in text.splitlines():
        for m in _PLAIN.finditer(line):
            name, num, unit = m.group(1), m.group(2).replace("−", "-").replace(",", "."), m.group(3) or ""
            if unit and not U.is_unit(unit):
                unit = ""
            st = Statement(id=f"p{page_no}:{len(out) + 1}", name=name.rstrip(".,"), kind="printed",
                           value=float(num), unit=U.parse_unit(unit).text if unit else "",
                           loc=f"page {page_no}", raw=line.strip()[:160], note="printed value")
            st.precision = 0.5 * 10 ** (-(len(num.split(".")[1]) if "." in num else 0))
            st.clause = find_clause(line)
            out.append(st)
    return out
