"""The agentic ingestion orchestrator.

Not a one-shot parse: a state machine that atomises the source, researches
it, asks the engineer inline, rebuilds, verifies, and LOOPS until the
result converges — every value replicated, every unit consistent, every
open point either answered or explicitly deferred to a human. Thorough
over fast, by design: convergence is the exit condition, not a timer.

    intake ──► ┌────────────────────────────────────────────┐
               │ decompose → research → clarify →           │
               │ reconstruct → verify                       │◄─ loop until
               └────────────────────────────────────────────┘   converged
                             │ clean / stable
                             ▼
                    reflect → deliver (+ audit trail)

Convergence: no verification errors AND no newly-answerable questions.
If an iteration changes nothing (same errors, same open items), the loop
stops and the remaining items are surfaced as deferred — the agent never
spins, and never fabricates an answer to force progress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.ingestion.agent.casefile import CaseFile
from src.ingestion.agent.interaction import (
    ConsoleInteraction,
    DeferInteraction,
    InteractionChannel,
)
from src.ingestion.agent import stages


@dataclass
class WorkflowContext:
    interaction: InteractionChannel
    repo_dir: Path
    llm: object = None
    slug: str = ""
    render_pdf: bool = True
    meta: object = None
    unit_aware: bool = False
    parser_interpreter: str = ""
    plan: list = field(default_factory=list)
    sheet: object = None
    noise_candidates: list = field(default_factory=list)


@dataclass
class IngestionResult:
    case: CaseFile
    paths: dict
    converged: bool
    iterations: int
    errors: list
    deferred: list

    def summary(self) -> str:
        state = "CONVERGED" if self.converged else "NEEDS INPUT"
        lines = [f"[{state}] '{self.case.title}' after "
                 f"{self.iterations} iteration(s)"]
        kept = self.case.kept()
        lines.append(
            f"  {sum(1 for f in kept if f.kind == 'input')} inputs · "
            f"{sum(1 for f in kept if f.kind == 'derived')} steps · "
            f"{sum(1 for f in kept if f.kind == 'check')} checks · "
            f"{sum(1 for f in kept if f.kind == 'image')} figures · "
            f"{len(self.case.decisions)} decisions taken")
        for e in self.errors:
            lines.append(f"  ⛔ {e}")
        for q in self.deferred:
            lines.append(f"  ❓ deferred: {q.prompt[:80]}")
        return "\n".join(lines)


class AgenticIngestion:
    def __init__(
        self,
        source_path: str | Path,
        repo_dir: str | Path = "repository",
        interaction: InteractionChannel | None = None,
        llm: object = None,
        max_iterations: int = 12,
        render_pdf: bool = True,
        meta: object = None,
        slug: str = "",
    ) -> None:
        self.source_path = Path(source_path)
        self.max_iterations = max_iterations
        if llm is None:
            from src.ingestion.llm_client import get_llm_client

            llm = get_llm_client()
        self.ctx = WorkflowContext(
            interaction=interaction or ConsoleInteraction(),
            repo_dir=Path(repo_dir), llm=llm, render_pdf=render_pdf,
            meta=meta, slug=slug)
        self.case = CaseFile(
            source_path=str(self.source_path),
            source_format=self.source_path.suffix.lstrip(".").lower())

    # -------------------------------------------------------------- #
    def run(self) -> IngestionResult:
        case, ctx = self.case, self.ctx
        stages.stage_intake(case, ctx)
        if not ctx.slug:
            from src.ingestion.grinder import slugify

            ctx.slug = slugify(case.title)

        previous_state = None
        converged = False
        for iteration in range(1, self.max_iterations + 1):
            case.iterations = iteration
            case.log("loop", f"— iteration {iteration} —")
            stages.stage_decompose(case, ctx)
            stages.stage_research(case, ctx)
            stages.stage_clarify(case, ctx)
            stages.stage_reconstruct(case, ctx)
            verification = stages.stage_verify(case, ctx)

            state = self._state_fingerprint(verification)
            if not verification["errors"] and not case.unresolved():
                converged = True
                case.log("loop", f"converged after {iteration} iteration(s)")
                break
            if state == previous_state:
                case.log("loop", "no further progress possible without "
                                 "human input — stopping cleanly")
                break
            previous_state = state

        stages.stage_reflect(case, ctx)
        paths = stages.stage_deliver(case, ctx)

        deferred = list(getattr(ctx.interaction, "deferred", []))
        return IngestionResult(
            case=case, paths=paths, converged=converged,
            iterations=case.iterations,
            errors=case.verification.get("errors", []),
            deferred=deferred)

    def _state_fingerprint(self, verification: dict) -> tuple:
        return (tuple(sorted(verification.get("errors", []))),
                tuple(sorted(f.fid for f in self.case.unresolved())),
                tuple(sorted(d.qid for d in self.case.decisions)))


def ingest(
    source_path: str | Path,
    repo_dir: str | Path = "repository",
    answers: dict | None = None,
    interactive: bool = True,
    **kwargs,
) -> IngestionResult:
    """Convenience entry point.

    ``answers`` -> scripted (batch) mode; ``interactive=False`` without
    answers -> defer mode (never blocks, defers open questions).
    """
    from src.ingestion.agent.interaction import ScriptedInteraction

    if answers is not None:
        channel: InteractionChannel = ScriptedInteraction(answers)
    elif interactive:
        channel = ConsoleInteraction()
    else:
        channel = DeferInteraction()
    return AgenticIngestion(
        source_path, repo_dir, interaction=channel, **kwargs).run()
