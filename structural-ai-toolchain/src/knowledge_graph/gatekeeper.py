"""The Gatekeeper — duplicate detection for new submissions.

Before The Grinder writes a new tool into ``/repository``, the gatekeeper
scores it against every existing tool and returns a verdict per match:

- score >= 0.80  -> 'duplicate'  (grind is blocked unless forced)
- score >= 0.55  -> 'similar'    (warning: review before merging)
- otherwise      -> not reported

Thresholds are deliberately conservative for the MVP; they should be
tuned once the repository holds real converted tools, and eventually
replaced/augmented by embedding similarity (see similarity.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.knowledge_graph.indexer import ToolRecord, load_records
from src.knowledge_graph.similarity import combined_score
from src.models.calculation import ParsedTool

DUPLICATE_THRESHOLD = 0.80
SIMILAR_THRESHOLD = 0.55


@dataclass
class Match:
    slug: str
    title: str
    score: float
    verdict: str  # 'duplicate' | 'similar'

    def __str__(self) -> str:
        icon = "⛔" if self.verdict == "duplicate" else "⚠️"
        return (
            f"{icon} {self.verdict.upper()} (score {self.score:.2f}): "
            f"'{self.title}' [{self.slug}]"
        )


def check_submission(
    submission: ParsedTool | ToolRecord,
    repo_dir: str | Path = "repository",
) -> list[Match]:
    """Score a hypothetical/incoming tool against the repository.

    Accepts either a freshly parsed tool or a raw ToolRecord (so the CLI
    can also answer "would this idea be a duplicate?" without a file).
    """
    if isinstance(submission, ParsedTool):
        record = ToolRecord(
            slug="__submission__",
            title=submission.title,
            description=submission.description,
            reference=submission.reference,
            variables=[v.name for v in submission.variables],
            formulas=[
                v.expression for v in submission.variables if v.expression
            ],
            checks=submission.checks,
        )
    else:
        record = submission

    existing = load_records(repo_dir)
    corpus = [r.document() for r in existing] + [record.document()]
    matches: list[Match] = []
    for other in existing:
        if other.slug == record.slug:
            continue
        score = combined_score(
            record.document(),
            other.document(),
            record.title,
            other.title,
            set(record.variables),
            set(other.variables),
            corpus,
        )
        if score >= DUPLICATE_THRESHOLD:
            matches.append(Match(other.slug, other.title, score, "duplicate"))
        elif score >= SIMILAR_THRESHOLD:
            matches.append(Match(other.slug, other.title, score, "similar"))
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches


def check_request(
    title: str,
    description: str = "",
    variables: list[str] | None = None,
    repo_dir: str | Path = "repository",
) -> list[Match]:
    """Check a *hypothetical* tool request (no file yet) — e.g. before an
    engineer starts building 'crack width checker v2'."""
    record = ToolRecord(
        slug="__request__",
        title=title,
        description=description,
        variables=variables or [],
    )
    return check_submission(record, repo_dir)
