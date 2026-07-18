"""Mathcad (.mcdx) parser — MOCK implementation.

A .mcdx file is a ZIP container (Open Packaging Conventions, like .docx)
whose payload is ``mathcad/worksheet.xml``: math regions serialized as
MathML-like XML with <ml:define>, <ml:eval> and <ml:id> nodes.

Planned real implementation:
1. unzip and read ``mathcad/worksheet.xml``
2. walk <regions> in worksheet order (top-to-bottom, left-to-right)
3. map <ml:define> -> ParsedVariable(role='input' | 'derived')
   and <ml:eval> -> displayed results / checks
4. translate the operator tree (<ml:apply><ml:mult/>...) into our
   expression strings, carrying <ml:unitReference> into the unit field

Until that lands, this mock detects the container, extracts what little
it safely can (worksheet presence, region count) and returns a ParsedTool
flagged for manual conversion — so the rest of the pipeline (gatekeeper,
repository layout, reporting) can already be exercised end-to-end.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from src.ingestion.base import BaseParser
from src.models.calculation import ParsedTool


class MathcadParser(BaseParser):
    extensions = (".mcdx",)

    def parse(self, path: Path) -> ParsedTool:
        path = Path(path)
        tool = ParsedTool(
            title=path.stem.replace("_", " ").title(),
            source_path=str(path),
            source_format="mcdx",
        )
        tool.warnings.append(
            "MOCK PARSER: .mcdx conversion is not implemented yet. "
            "The file was registered for provenance; its math regions "
            "must be converted manually or wait for the worksheet.xml "
            "translator (see module docstring for the plan)."
        )
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
            if any("worksheet.xml" in n for n in names):
                tool.description = (
                    "Mathcad worksheet detected "
                    f"({len(names)} parts in container)."
                )
            else:
                tool.warnings.append(
                    "Container does not look like a Mathcad Prime file "
                    "(no worksheet.xml)."
                )
        except (zipfile.BadZipFile, FileNotFoundError):
            tool.warnings.append(
                "File is not a readable ZIP container; it may be a legacy "
                "binary .mcd/.xmcd worksheet."
            )
        return tool
