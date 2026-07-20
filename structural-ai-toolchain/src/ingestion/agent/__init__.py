"""Agentic ingestion — the thorough, interactive conversion workflow.

Use ``ingest(path)`` for the full loop (console questions inline), or
``ingest(path, answers={...})`` for scripted/batch mode.
"""

from src.ingestion.agent.casefile import CaseFile, Decision, Fragment
from src.ingestion.agent.interaction import (
    ConsoleInteraction,
    DeferInteraction,
    Question,
    ScriptedInteraction,
)
from src.ingestion.agent.workflow import (
    AgenticIngestion,
    IngestionResult,
    ingest,
)

__all__ = [
    "ingest",
    "AgenticIngestion",
    "IngestionResult",
    "CaseFile",
    "Fragment",
    "Decision",
    "Question",
    "ConsoleInteraction",
    "ScriptedInteraction",
    "DeferInteraction",
]
