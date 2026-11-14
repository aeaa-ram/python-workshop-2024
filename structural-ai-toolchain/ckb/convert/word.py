"""Word reports -> machine-readable statements.

A report states results in running text, in tables and in equation-editor
objects.  The converter walks the document in order, keeps the headings as
context, and reads every printed quantity (``VRd,c = 157.1 kN``).  Equations
typed with the equation editor are linearised, and a formula written in plain
arithmetic is accepted if it reproduces the printed result.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..ir import SourceDocument, file_sha256
from .python_src import ConversionError, find_clause
from .records import build_from_records

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
_NUM = r"[-−]?\d+(?:[.,]\d+)?"
_UNIT = r"[A-Za-zµμ°%‰][A-Za-z0-9/²³⁴·.^]{0,9}"
_EQ = re.compile(
    rf"(?<![\w.])(?P<name>[A-Za-zΑ-Ωα-ω][\w.,]{{0,16}}?)\s*(?:=|≔|:=)\s*(?P<body>[^=;\n]*?)"
    rf"(?:=\s*(?P<val>{_NUM})\s*(?P<unit>{_UNIT})?)?(?=\s*(?:[;\n]|$|\s{{2,}}))")


def _text(el) -> str:
    """Text of a paragraph, including equation-editor content in reading order."""
    out = []
    for node in el.iter():
        if node.tag in (_W + "t", _M + "t"):
            out.append(node.text or "")
        elif node.tag == _W + "tab":
            out.append("  ")
        elif node.tag == _W + "br":
            out.append("\n")
    return "".join(out)


def _formula(body: str) -> str:
    """Plain arithmetic typed in a report, as a Python expression (or '')."""
    s = body.strip().replace("·", "*").replace("×", "*").replace("⋅", "*").replace("−", "-")
    s = s.replace("^", "**").replace(",", ".") if re.search(r"\d,\d", s) else s.replace("^", "**")
    s = re.sub(r"(?<=[A-Za-z0-9_)])\.(?=[A-Za-z_])", "_", s)        # V.Rd -> V_Rd
    if not s or not re.search(r"[A-Za-z_]", s) or re.search(r"[^\w\s.+\-*/(),]", s):
        return ""
    return s


def convert_word(path: Path) -> SourceDocument:
    path = Path(path)
    try:
        import docx
    except ImportError as exc:                                   # pragma: no cover
        raise ConversionError("python-docx is not installed") from exc
    try:
        document = docx.Document(str(path))
    except Exception as exc:                                     # noqa: BLE001
        raise ConversionError(f"Word file cannot be opened: {exc}") from exc
    doc = SourceDocument(name=path.name, kind="word", sha256=file_sha256(path),
                         converter=f"python-docx {getattr(docx, '__version__', '')}".strip())
    doc.meta["units"] = "declared"
    props = document.core_properties
    for key, val in (("author", props.author), ("title", props.title)):
        if val:
            doc.meta[key] = val
    styles = {p._p: (p.style.name if p.style is not None else "") for p in document.paragraphs}
    records: list[dict] = []
    section: list[str] = []
    clause_ctx = ""

    def scan(text: str, where: str):
        nonlocal clause_ctx
        clause_here = find_clause(text)
        for line in text.splitlines():
            for m in _EQ.finditer(line):
                name, body = m.group("name").rstrip(".,"), m.group("body") or ""
                val, unit = m.group("val"), m.group("unit") or ""
                if val is None:
                    m2 = re.fullmatch(rf"\s*({_NUM})\s*({_UNIT})?\s*", body)
                    if not m2:
                        continue
                    val, unit, body = m2.group(1), m2.group(2) or "", ""
                num = val.replace("−", "-").replace(",", ".")
                records.append({
                    "name": name, "value": float(num), "unit": unit, "formula": _formula(body),
                    "label": line.strip()[:140], "clause": clause_here or clause_ctx,
                    "section": list(section), "loc": where,
                    "precision": 0.5 * 10 ** (-(len(num.split(".")[1]) if "." in num else 0)) if body.strip() else 0.0,
                })

    n_par = n_tab = 0
    for child in document.element.body.iterchildren():
        if child.tag == _W + "p":
            n_par += 1
            text = _text(child).strip()
            if not text:
                continue
            style = styles.get(child, "")
            if style.lower().startswith(("heading", "title", "überschrift", "rubrik", "overskrift")):
                level = int(re.search(r"(\d+)", style).group(1)) if re.search(r"\d", style) else 1
                section[:] = section[:max(level - 1, 0)] + [text]
                clause_ctx = find_clause(text)
                continue
            scan(text, f"paragraph {n_par}")
        elif child.tag == _W + "tbl":
            n_tab += 1
            for r, row in enumerate(child.iter(_W + "tr"), 1):
                cells = [_text(c).strip() for c in row.iter(_W + "tc")]
                joined = "   ".join(cells)
                before = len(records)
                scan(joined, f"table {n_tab} row {r}")
                if len(records) == before and len(cells) >= 2:
                    # "symbol | value | unit" or "description | symbol | value | unit"
                    for i, c in enumerate(cells):
                        if re.fullmatch(_NUM, c) and i >= 1:
                            unit = cells[i + 1] if i + 1 < len(cells) and re.fullmatch(_UNIT, cells[i + 1]) else ""
                            records.append({"name": cells[i - 1], "value": float(c.replace(",", ".").replace("−", "-")),
                                            "unit": unit, "label": " ".join(cells[:i - 1]) or cells[i - 1],
                                            "clause": clause_ctx, "section": list(section),
                                            "loc": f"table {n_tab} row {r}"})
                            break
    build_from_records(doc, records)
    return doc
