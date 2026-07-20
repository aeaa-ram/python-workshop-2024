"""Inline human-in-the-loop: the agent asks WHILE it builds, not after.

A ``Question`` carries context, the agent's suggestion and its rationale,
so answering takes seconds. Three channels:

- ``ConsoleInteraction`` — interactive prompts on screen (CLI use).
- ``ScriptedInteraction`` — answers supplied up-front (batch/CI/tests),
  falling back to the agent's suggested default.
- ``DeferInteraction``  — never blocks: records the question, applies the
  default, and marks the decision 'deferred' so a human revisits it.

Every Q&A is recorded in the case file as a Decision — the audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Question:
    qid: str
    stage: str
    prompt: str
    options: list = field(default_factory=list)   # [] -> free text
    default: str = ""
    context: str = ""       # what the agent was looking at
    rationale: str = ""     # why it suggests the default


class InteractionChannel(Protocol):
    def ask(self, question: Question) -> tuple[str, str]:
        """Return (answer, answered_by)."""
        ...


class ConsoleInteraction:
    """Interactive prompts during the build (python main.py ingest ...)."""

    def ask(self, q: Question) -> tuple[str, str]:
        print(f"\n┌─ [{q.stage}] question {q.qid} " + "─" * 30)
        if q.context:
            print(f"│ context : {q.context}")
        print(f"│ {q.prompt}")
        if q.rationale:
            print(f"│ suggest : {q.default}   ({q.rationale})")
        if q.options:
            for i, opt in enumerate(q.options, 1):
                print(f"│   {i}) {opt}")
            raw = input(f"└─ answer [1-{len(q.options)}, Enter={q.default}]: ")
            raw = raw.strip()
            if not raw:
                return q.default, "default"
            if raw.isdigit() and 1 <= int(raw) <= len(q.options):
                return q.options[int(raw) - 1], "user"
            return raw, "user"
        raw = input(f"└─ answer [Enter={q.default}]: ").strip()
        return (raw, "user") if raw else (q.default, "default")


class ScriptedInteraction:
    """Pre-supplied answers keyed by qid (or matched by prompt substring)."""

    def __init__(self, answers: dict[str, str] | None = None) -> None:
        self.answers = dict(answers or {})
        self.transcript: list[tuple[Question, str]] = []

    def ask(self, q: Question) -> tuple[str, str]:
        answer, by = q.default, "default"
        if q.qid in self.answers:
            answer, by = self.answers[q.qid], "script"
        else:
            for key, val in self.answers.items():
                if key.lower() in q.prompt.lower():
                    answer, by = val, "script"
                    break
        self.transcript.append((q, answer))
        return answer, by


class DeferInteraction:
    """Never blocks; defaults everything and marks it for human follow-up."""

    def __init__(self) -> None:
        self.deferred: list[Question] = []

    def ask(self, q: Question) -> tuple[str, str]:
        self.deferred.append(q)
        return q.default, "deferred"
