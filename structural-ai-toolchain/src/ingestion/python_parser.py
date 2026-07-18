"""Raw Python script parser for The Grinder.

Reuses the notebook line conventions (``name = expr  # unit | desc``) on a
flat .py file. The module docstring becomes the tool description; a
top-of-file ``# Title: ...`` comment overrides the filename-derived title.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from src.ingestion.base import BaseParser
from src.ingestion.notebook_parser import NotebookParser
from src.models.calculation import ParsedTool


class PythonParser(BaseParser):
    extensions = (".py",)

    def parse(self, path: Path) -> ParsedTool:
        path = Path(path)
        source = path.read_text(encoding="utf-8")
        tool = ParsedTool(
            title=path.stem.replace("_", " ").title(),
            source_path=str(path),
            source_format="py",
        )
        title_match = re.search(r"^#\s*Title:\s*(.+)$", source, re.MULTILINE)
        if title_match:
            tool.title = title_match.group(1).strip()
        try:
            docstring = ast.get_docstring(ast.parse(source))
            if docstring:
                tool.description = docstring.strip().splitlines()[0]
        except SyntaxError:
            tool.warnings.append("File has syntax errors; best-effort parse.")
        # Delegate line-level extraction to the notebook parser logic.
        NotebookParser._parse_code(NotebookParser(), tool, source, set())
        return tool
