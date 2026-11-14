"""Jupyter notebooks -> machine-readable statements.

The code cells are joined into one script (markdown cells become comments, so
headings and explanations are kept as context) and the script goes through
the Python converter.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..ir import SourceDocument, file_sha256
from .python_src import ConversionError, convert_source


def notebook_to_script(path: Path) -> str:
    try:
        nb = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConversionError(f"notebook cannot be read: {exc}") from exc
    out: list[str] = []
    for cell in nb.get("cells", []):
        src = cell.get("source", "")
        src = "".join(src) if isinstance(src, list) else str(src)
        if cell.get("cell_type") == "markdown":
            for line in src.splitlines():
                m = re.match(r"^\s*#{1,6}\s+(.*)$", line)
                if m:
                    out.append(f"# === {m.group(1).strip()} ===")
                elif line.strip():
                    out.append(f"# {line.strip()}")
            out.append("")
        elif cell.get("cell_type") == "code":
            for line in src.splitlines():
                # notebook magics and shell escapes are not Python
                out.append(("# " + line) if re.match(r"^\s*[%!]", line) else line)
            out.append("")
    return "\n".join(out) + "\n"


def convert_notebook(path: Path) -> SourceDocument:
    path = Path(path)
    return convert_source(notebook_to_script(path), path.name, "notebook",
                          sha256=file_sha256(path), converter="notebook cells -> python ast + isolated run")
