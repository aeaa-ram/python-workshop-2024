"""Parser registry for The Grinder.

Each file format gets a parser class exposing ``extensions`` and
``parse(path) -> ParsedTool``. New formats plug in by subclassing
``BaseParser`` — the Grinder discovers them through ``get_parser``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.models.calculation import ParsedTool

_REGISTRY: dict[str, type["BaseParser"]] = {}


class UnsupportedFormatError(Exception):
    pass


class BaseParser(ABC):
    """A reader for one legacy file format."""

    extensions: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for ext in cls.extensions:
            _REGISTRY[ext.lower()] = cls

    @abstractmethod
    def parse(self, path: Path) -> ParsedTool:
        ...


def get_parser(path: str | Path) -> BaseParser:
    ext = Path(path).suffix.lower()
    parser_cls = _REGISTRY.get(ext)
    if parser_cls is None:
        raise UnsupportedFormatError(
            f"No parser registered for '{ext}'. "
            f"Supported: {sorted(_REGISTRY)}"
        )
    return parser_cls()


def supported_extensions() -> list[str]:
    return sorted(_REGISTRY)
