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

# Ramboll wordmark recreation (SVG). This is a close approximation for the
# report template, NOT the official trademarked asset — drop the official
# file at assets/logo.svg (or set Branding.logo_path) to replace it.
_PLACEHOLDER_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 232 56" '
    'role="img" aria-label="Ramboll">'
    '<rect x="0" y="0" width="232" height="56" rx="10" fill="#00A0DF"/>'
    '<text x="116" y="39" text-anchor="middle" '
    'font-family="Arial, Helvetica, sans-serif" font-size="34" '
    'font-weight="800" letter-spacing="1.5" fill="#ffffff">'
    'RAMBØLL</text></svg>'
)


def _default_logo() -> str:
    """Prefer the on-disk asset (assets/logo.svg) so a dropped-in official
    logo is used automatically; else the embedded recreation."""
    from pathlib import Path

    asset = Path(__file__).resolve().parents[2] / "assets" / "logo.svg"
    if asset.exists():
        try:
            svg = asset.read_text(encoding="utf-8")
            return svg[svg.index("<svg"):]
        except Exception:
            pass
    return _PLACEHOLDER_LOGO_SVG


@dataclass
class Branding:
    """Company-wide look; one instance rebrands every report."""

    company_name: str = "Ramboll"
    company_tagline: str = "Bright ideas. Sustainable change."
    logo_path: str = ""            # .svg or .png; empty -> asset/recreation
    primary: str = "#13293D"       # header/border ink (deep navy)
    accent: str = "#00A0DF"        # Ramboll cyan — rules / highlights
    light: str = "#EAF1F6"         # zebra / panels
    ok_color: str = "#1E7D32"      # passing verification
    not_ok_color: str = "#C62828"  # failing verification
    ok_label: str = "OK"
    not_ok_label: str = "NOT OK"
    page_border: bool = True       # Mathcad-like black frame

    def logo_markup(self) -> str:
        """Inline logo as SVG markup or a data-URI <img> (self-contained)."""
        if not self.logo_path:
            return _default_logo()
        path = Path(self.logo_path)
        if not path.exists():
            return _default_logo()
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
