"""Machine-readable stamping & reconstruction for generated PDFs.

Every report PDF carries the complete calculation as structured JSON —
an *AI-proof* layer: a future model (or any script) reads the exact
inputs, formulas, values and check verdicts from the file itself instead
of OCR-ing the typeset math.

The PRIMARY, attachment-free channel is a self-contained layer baked into
the **page content**: invisible sentinel-wrapped base64(gzip(json)) text
(added by the HTML renderer). It survives ordinary text extraction, so
handing someone only the PDF is enough — ``reconstruct_from_pdf`` gets the
data back with pdftotext or any PDF text extractor, no attachment needed.

Two extra belt-and-braces channels are also written by ``stamp_pdf``:
1. an embedded-file attachment ``calcsheet.json`` (/EmbeddedFiles), and
2. document metadata incl. a ``/CalcSheetSchema`` key.
These help when a viewer surfaces attachments, but the system of record
does NOT depend on them — the in-page layer and the sidecar/manifest do.
"""

from __future__ import annotations

import base64
import gzip
import json
import re
import shutil
import subprocess
from pathlib import Path

from src.models.calculation import CalcSheet

ATTACHMENT_NAME = "calcsheet.json"
_MR_RE = re.compile(r"@@CALCSHEET/1@@(.*?)@@END@@", re.DOTALL)


def stamp_pdf(pdf_path: str | Path, sheet: CalcSheet) -> Path:
    """Embed the sheet's JSON payload + metadata into an existing PDF."""
    from pypdf import PdfReader, PdfWriter

    pdf_path = Path(pdf_path)
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter(clone_from=reader)  # clone keeps pages AND outline
    writer.add_attachment(
        ATTACHMENT_NAME, sheet.to_json().encode("utf-8")
    )
    writer.add_metadata(
        {
            "/Title": sheet.title,
            "/Author": sheet.author or "Structural AI Toolchain",
            "/Subject": sheet.reference or sheet.description,
            "/Creator": "Structural AI Toolchain output engine",
            "/Keywords": (
                "structural-ai-toolchain, machine-readable, "
                f"embedded:{ATTACHMENT_NAME}"
            ),
            "/CalcSheetSchema": CalcSheet.SCHEMA,
        }
    )
    with open(pdf_path, "wb") as fh:
        writer.write(fh)
    return pdf_path


def _extract_text(pdf_path: str | Path) -> str:
    """Best-effort full-text extraction, pdftotext first then pypdf."""
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        out = subprocess.run(
            [pdftotext, "-nopgbrk", "-q", str(pdf_path), "-"],
            capture_output=True, text=True,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def reconstruct_from_pdf(pdf_path: str | Path) -> dict:
    """Reconstruct the calculation from the PDF ALONE (no attachment).

    Reads the self-contained in-page machine-readable layer. This is the
    intended path: give someone only the PDF and they get the full
    structured data back, immune to the attachment-stripping that plagues
    modern PDF round-trips.
    """
    text = _extract_text(pdf_path)
    match = _MR_RE.search(text)
    if match:
        b64 = re.sub(r"[^A-Za-z0-9+/=]", "", match.group(1))
        raw = gzip.decompress(base64.b64decode(b64))
        return json.loads(raw.decode("utf-8"))
    # fall back to the attachment channel if the text layer is gone
    try:
        return read_embedded_calcsheet(pdf_path)
    except Exception as exc:
        raise ValueError(
            f"No machine-readable calcsheet found in {pdf_path} "
            "(neither the in-page layer nor an attachment)."
        ) from exc


def read_embedded_calcsheet(pdf_path: str | Path) -> dict:
    """Extract the calcsheet from the embedded-file attachment channel."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    attachments = reader.attachments
    if ATTACHMENT_NAME not in attachments:
        raise ValueError(
            f"{pdf_path} has no embedded {ATTACHMENT_NAME} attachment; try "
            "reconstruct_from_pdf() which reads the in-page layer instead."
        )
    payload = attachments[ATTACHMENT_NAME]
    raw = payload[0] if isinstance(payload, list) else payload
    return json.loads(raw.decode("utf-8"))
