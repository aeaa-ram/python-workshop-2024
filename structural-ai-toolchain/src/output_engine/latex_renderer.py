r"""LaTeX renderer: CalcSheet -> complete A4 report (.tex) and optional PDF.

Produces a self-contained article with colored header/footer bands
(fancyhdr + xcolor) so the typeset PDF looks like a company calculation
report, not a plain LaTeX article. Compile with pdflatex, xelatex or
tectonic; ``render_pdf`` shells out to pdflatex when it is installed.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from src.models.calculation import CalcSheet, fmt_number, unit_latex

# Corporate palette — swap these three definitions to rebrand every report.
_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=22mm,headheight=30pt,includeheadfoot]{geometry}
\usepackage{amsmath}
\usepackage[table]{xcolor}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{array}
\definecolor{BrandPrimary}{HTML}{1F3A5F}
\definecolor{BrandAccent}{HTML}{2E86AB}
\definecolor{BrandLight}{HTML}{EDF2F7}
\definecolor{PassGreen}{HTML}{1E7D32}
\definecolor{FailRed}{HTML}{C62828}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{1.5pt}
\renewcommand{\headrule}{\hbox to\headwidth{\color{BrandAccent}\leaders\hrule height \headrulewidth\hfill}}
\renewcommand{\footrulewidth}{0.8pt}
\renewcommand{\footrule}{\hbox to\headwidth{\color{BrandAccent}\leaders\hrule height \footrulewidth\hfill}}
\newcommand{\calccheckpass}[1]{\noindent\colorbox{PassGreen}{\textcolor{white}{\textbf{~PASS~}}}\; #1}
\newcommand{\calccheckfail}[1]{\noindent\colorbox{FailRed}{\textcolor{white}{\textbf{~FAIL~}}}\; #1}
"""


def _escape(text: str) -> str:
    for char, repl in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ):
        text = text.replace(char, repl)
    return text


def render_latex(sheet: CalcSheet) -> str:
    lines: list[str] = [_PREAMBLE]
    title = _escape(sheet.title)
    project = _escape(sheet.project) if sheet.project else "—"
    lines.append(
        r"\fancyhead[L]{\textcolor{BrandPrimary}{\textbf{"
        + project
        + r"}}}"
    )
    lines.append(
        r"\fancyhead[R]{\textcolor{BrandPrimary}{" + title + r"}}"
    )
    lines.append(
        r"\fancyfoot[L]{\small\textcolor{BrandPrimary}{Rev. "
        + _escape(sheet.revision)
        + " — "
        + _escape(sheet.created)
        + r"}}"
    )
    lines.append(
        r"\fancyfoot[C]{\small\textcolor{BrandPrimary}"
        r"{Structural AI Toolchain}}"
    )
    lines.append(
        r"\fancyfoot[R]{\small\textcolor{BrandPrimary}"
        r"{Page \thepage\ of \pageref{LastPage}}}"
    )
    lines.append(r"\begin{document}")

    # Title block
    lines.append(r"\begin{center}")
    lines.append(
        r"{\LARGE\bfseries\color{BrandPrimary} " + title + r"}\\[4pt]"
    )
    if sheet.reference:
        lines.append(
            r"{\color{BrandAccent}\large "
            + _escape(sheet.reference)
            + r"}\\[2pt]"
        )
    if sheet.author:
        lines.append(r"{\small Prepared by: " + _escape(sheet.author) + r"}")
    lines.append(r"\end{center}")
    if sheet.description:
        lines.append(r"\noindent " + _escape(sheet.description) + r"\par")
    lines.append(r"\vspace{6pt}")

    section_no = 0
    input_buffer: list = []
    body: list[str] = []

    def flush_inputs() -> None:
        if not input_buffer:
            return
        body.append(r"\rowcolors{2}{BrandLight}{white}")
        body.append(
            r"\noindent\begin{tabular}"
            r"{>{$}l<{$} r l p{7cm}}"
        )
        body.append(
            r"\rowcolor{BrandPrimary}"
            r"\textcolor{white}{\textbf{Symbol}} & "
            r"\textcolor{white}{\textbf{Value}} & "
            r"\textcolor{white}{\textbf{Unit}} & "
            r"\textcolor{white}{\textbf{Description}} \\"
        )
        for item in input_buffer:
            body.append(
                f"{item.latex_lhs} & {fmt_number(item.value)} & "
                f"{_escape(item.unit)} & {_escape(item.description)} \\\\"
            )
        body.append(r"\end{tabular}\par\vspace{8pt}")
        input_buffer.clear()

    for item in sheet.items:
        if item.kind == "section":
            flush_inputs()
            section_no += 1
            body.append(
                r"\section*{\color{BrandPrimary}"
                + f"{section_no}.\\ {_escape(item.name)}"
                + r"}"
            )
        elif item.kind == "text":
            flush_inputs()
            body.append(_escape(item.text) + r"\par")
        elif item.kind == "input":
            input_buffer.append(item)
        elif item.kind == "calc":
            flush_inputs()
            if item.description:
                body.append(
                    r"\noindent\textbf{" + _escape(item.description) + r"}"
                )
            result = fmt_number(item.value)
            rendered_unit = unit_latex(item.unit)
            unit = f"\\ {rendered_unit}" if rendered_unit else ""
            body.append(r"\begin{align*}")
            body.append(f"{item.latex_lhs} &= {item.latex_symbolic} \\\\")
            body.append(f"&= {item.latex_substituted} \\\\")
            body.append(f"&= \\mathbf{{{result}}}{unit}")
            body.append(r"\end{align*}")
        elif item.kind == "check":
            flush_inputs()
            content = f"${item.latex_symbolic}$"
            if item.description:
                content += r" \small(" + _escape(item.description) + ")"
            cmd = r"\calccheckpass" if item.passed else r"\calccheckfail"
            body.append(cmd + "{" + content + r"}\par\vspace{4pt}")
    flush_inputs()

    lines.extend(body)
    lines.append(r"\end{document}")
    return "\n".join(lines)


def render_pdf(sheet: CalcSheet, out_path: str | Path) -> Path:
    """Compile the sheet to PDF via pdflatex.

    Raises RuntimeError with actionable guidance when no LaTeX toolchain is
    installed — in that case use ``render_html`` and print from a browser.
    """
    pdflatex = shutil.which("pdflatex")
    if pdflatex is None:
        raise RuntimeError(
            "pdflatex is not installed. Either install TeX Live "
            "(apt install texlive-latex-recommended texlive-latex-extra) "
            "or render_html() and print to PDF from a browser."
        )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tex_file = Path(tmp) / "report.tex"
        tex_file.write_text(render_latex(sheet), encoding="utf-8")
        for _ in range(2):  # two passes for LastPage references
            subprocess.run(
                [pdflatex, "-interaction=nonstopmode", tex_file.name],
                cwd=tmp,
                check=True,
                capture_output=True,
            )
        shutil.copy(Path(tmp) / "report.pdf", out_path)
    return out_path
