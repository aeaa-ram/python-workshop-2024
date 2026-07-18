"""Output Engine — renders CalcSheets for non-coder review.

One CalcSheet, synchronized outputs:

- ``render_markdown``     -> Git-friendly .md with LaTeX math (SSOT doc)
- ``render_html``         -> print-ready, branded A4 HTML (offline SVG math)
- ``render_pdf_browser``  -> A4 PDF via headless Chromium (bookmarks +
                             self-contained machine-readable layer)
- ``render_latex``        -> full .tex document for pdflatex/tectonic
- ``reconstruct_from_pdf``-> recover the calculation from the PDF alone

Render modes: "detailed" (Mathcad three-line) and "compact" (one line).
Branding/ReportMeta control the company template (logo, initials, etc.).
"""

from pathlib import Path

from .branding import DEFAULT_BRANDING, Branding, ReportMeta
from .html_renderer import find_chromium, render_html, render_pdf_browser
from .latex_renderer import render_latex, render_pdf
from .markdown_renderer import math_to_markdown, render_markdown
from .pdf_stamp import read_embedded_calcsheet, reconstruct_from_pdf


def render_all(
    sheet,
    out_dir,
    basename: str | None = None,
    pdf: bool = False,
    branding: Branding | None = None,
    meta: ReportMeta | None = None,
    mode: str = "detailed",
) -> dict:
    """Render every supported format into ``out_dir``; returns paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = basename or _slug(sheet.title)
    paths = {
        "markdown": out / f"{name}.md",
        "html": out / f"{name}.html",
        "latex": out / f"{name}.tex",
        "json": out / f"{name}.calcsheet.json",
    }
    paths["markdown"].write_text(
        render_markdown(sheet, mode=mode), encoding="utf-8"
    )
    paths["html"].write_text(
        render_html(sheet, branding, meta, mode), encoding="utf-8"
    )
    paths["latex"].write_text(render_latex(sheet), encoding="utf-8")
    # Sidecar machine-readable twin (same payload baked into the PDF).
    paths["json"].write_text(sheet.to_json(), encoding="utf-8")
    result = {k: str(v) for k, v in paths.items()}
    if pdf:
        if find_chromium() is None:
            result["pdf"] = "(skipped — no Chromium/Chrome found)"
        else:
            result["pdf"] = str(
                render_pdf_browser(
                    sheet, out / f"{name}.pdf", branding, meta, mode
                )
            )
    return result


def _slug(title: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "calc_sheet"


__all__ = [
    "render_markdown",
    "render_latex",
    "render_html",
    "render_pdf",
    "render_pdf_browser",
    "reconstruct_from_pdf",
    "read_embedded_calcsheet",
    "find_chromium",
    "render_all",
    "math_to_markdown",
    "Branding",
    "ReportMeta",
    "DEFAULT_BRANDING",
]
