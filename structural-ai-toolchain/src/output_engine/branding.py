"""Report branding & per-report metadata.

Everything a Mathcad-style structural calc sheet needs on the page:
company name + logo (top-left), project/title block, prepared/checked/
approved initials, revision, status, a black page border, and OK / NOT OK
verdict styling. All configurable — swap ``Branding`` to rebrand every
report at once.

The default ships a **placeholder** Ramboll-flavoured wordmark. Replace
it with the official asset by pointing ``logo_path`` at an .svg/.png file
(or editing ``assets/logo.svg``); nothing else changes.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path

# Placeholder wordmark — NOT the official logo. Replace via logo_path or by
# editing assets/logo.svg. Kept deliberately simple/typographic.
_PLACEHOLDER_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="150" height="34" '
    'viewBox="0 0 150 34" role="img" aria-label="Company logo placeholder">'
    '<rect width="150" height="34" rx="3" fill="#0033A0"/>'
    '<text x="12" y="23" font-family="Arial, Helvetica, sans-serif" '
    'font-size="18" font-weight="700" letter-spacing="1" fill="#ffffff">'
    'RAMBÖLL</text></svg>'
)


@dataclass
class Branding:
    """Company-wide look; one instance rebrands every report."""

    company_name: str = "Ramboll"
    company_tagline: str = "Bright ideas. Sustainable change."
    logo_path: str = ""            # .svg or .png; empty -> placeholder
    primary: str = "#0033A0"       # header/border ink
    accent: str = "#00A0D2"        # rules / highlights
    light: str = "#EEF2F8"         # zebra / panels
    ok_color: str = "#1E7D32"      # passing verification
    not_ok_color: str = "#C62828"  # failing verification
    ok_label: str = "OK"
    not_ok_label: str = "NOT OK"
    page_border: bool = True       # Mathcad-like black frame

    def logo_markup(self) -> str:
        """Inline logo as SVG markup or a data-URI <img> (self-contained)."""
        if not self.logo_path:
            return _PLACEHOLDER_LOGO_SVG
        path = Path(self.logo_path)
        if not path.exists():
            return _PLACEHOLDER_LOGO_SVG
        if path.suffix.lower() == ".svg":
            svg = path.read_text(encoding="utf-8")
            return svg[svg.index("<svg"):] if "<svg" in svg else svg
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(path.read_bytes()).decode()
        return (
            f'<img class="logo-img" alt="{self.company_name} logo" '
            f'src="data:{mime};base64,{b64}">'
        )


@dataclass
class ReportMeta:
    """Per-report cartouche data (the header/footer fields)."""

    project: str = ""
    project_no: str = ""
    prepared_by: str = ""     # initials
    checked_by: str = ""      # reviewer initials
    approved_by: str = ""     # approver initials
    status: str = "DRAFT"     # DRAFT / ISSUED / SUPERSEDED ...
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_sheet(cls, sheet) -> "ReportMeta":
        """Sensible defaults pulled from the sheet when not supplied."""
        return cls(
            project=getattr(sheet, "project", "") or "",
            prepared_by=_initials(getattr(sheet, "author", "") or ""),
            status="DRAFT",
        )


def _initials(name: str) -> str:
    parts = [p for p in name.replace(".", " ").split() if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][:2].upper()
    return "".join(p[0] for p in parts[:3]).upper()


DEFAULT_BRANDING = Branding()
