"""Stage 2 - conversion: every source file becomes a ``SourceDocument``.

    Mathcad Prime  .mcdx            mcad2py -> Python -> statements, checked against stored results
    Excel          .xlsx .xlsm      formulas parsed, checked against cached values
    Python         .py              ast + isolated run
    Jupyter        .ipynb           cells -> script -> as Python
    PDF            .pdf             printed quantities from the text layer (benchmarks)
    Word           .docx            printed quantities, headings, typed formulas
    scan / photo   .png .jpg .pdf   vision model, verified by re-evaluation

A file that cannot be converted raises ``ConversionError``; the pipeline
records the reason and carries on with the other files.
"""
from __future__ import annotations

from pathlib import Path

from ..ir import SourceDocument
from .python_src import ConversionError

KINDS = {
    ".mcdx": "mathcad", ".xlsx": "excel", ".xlsm": "excel", ".py": "python",
    ".ipynb": "notebook", ".pdf": "pdf", ".docx": "word",
    ".png": "scan", ".jpg": "scan", ".jpeg": "scan", ".tif": "scan", ".tiff": "scan",
    ".webp": "scan", ".gif": "scan",
}
NOT_SUPPORTED = {
    ".xls": "old Excel format: open it and save as .xlsx",
    ".xlsb": "binary Excel format: open it and save as .xlsx",
    ".doc": "old Word format: open it and save as .docx",
    ".xmcd": "Mathcad 15 format: convert the worksheet to Mathcad Prime (.mcdx)",
    ".mcd": "Mathcad 15 format: convert the worksheet to Mathcad Prime (.mcdx)",
}


def kind_of(path: Path) -> str | None:
    return KINDS.get(Path(path).suffix.lower())


def convert_file(path: Path, llm=None, vision: bool = False) -> SourceDocument:
    """Convert one file.  ``vision`` also asks the model to read formulas from a PDF."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in NOT_SUPPORTED:
        raise ConversionError(NOT_SUPPORTED[ext])
    kind = KINDS.get(ext)
    if kind is None:
        raise ConversionError(f"file type {ext or '(none)'} is not a calculation format the converter knows")
    if kind == "mathcad":
        from .mathcad import convert_mathcad
        return convert_mathcad(path)
    if kind == "excel":
        from .excel import convert_excel
        return convert_excel(path)
    if kind == "python":
        from .python_src import convert_python
        return convert_python(path)
    if kind == "notebook":
        from .notebook import convert_notebook
        return convert_notebook(path)
    if kind == "word":
        from .word import convert_word
        return convert_word(path)
    if kind == "pdf":
        from .pdf import convert_pdf
        doc = convert_pdf(path)
        if doc.meta.get("scanned") or vision:
            from .scan import convert_scan
            try:
                seen = convert_scan(path, llm=llm, kind="pdf")
            except ConversionError as exc:
                if doc.meta.get("scanned"):
                    raise
                doc.issues.append(f"formulas not recovered: {exc}")
                return doc
            seen.meta.update({k: v for k, v in doc.meta.items() if k not in seen.meta})
            return seen
        return doc
    from .scan import convert_scan
    return convert_scan(path, llm=llm)
