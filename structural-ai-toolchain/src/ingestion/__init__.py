"""The Grinder — ingestion & conversion adapters.

Importing this package registers all parsers with the format registry.
"""

from src.ingestion import (  # noqa: F401 — imports register parsers
    excel_parser,
    mathcad_parser,
    notebook_parser,
    python_parser,
)
from src.ingestion.base import get_parser, supported_extensions
from src.ingestion.grinder import DuplicateToolError, GrindResult, grind

__all__ = [
    "grind",
    "GrindResult",
    "DuplicateToolError",
    "get_parser",
    "supported_extensions",
]
