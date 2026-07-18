"""AI-assisted QA — engineering-judgment review of tools (optional layer).

The deterministic checks (checks.py) catch mechanical issues; this module
targets what needs judgment: wrong clause application, missing validity
limits, unstated assumptions, unit inconsistencies, and pitfalls of the
method itself — reviewed against the standard the tool cites (Eurocode,
national annexes, ...).

Two ways to use it today:

1. **Prompt export** (works now, no API): ``build_review_prompt(sheet)``
   produces a complete, structured review request containing the
   machine-readable calcsheet JSON. Paste it into Claude (or any LLM)
   and you get a clause-by-clause review back.
2. **API reviewer** (wire up when an API key is provisioned): implement
   ``AIReviewer.review`` — the ``AnthropicReviewer`` skeleton shows the
   intended integration. The human always stays the approver; AI output
   is advisory and lands in the tool's review notes, never auto-merged.
"""

from __future__ import annotations

from typing import Protocol

from src.models.calculation import CalcSheet

REVIEW_INSTRUCTIONS = """\
You are a senior structural engineer performing independent QA on a
calculation tool. The tool is given below as structured JSON (schema
{schema}): metadata, inputs, formulas (with computed values) and
pass/fail checks.

Review it against {reference} and general structural engineering
practice. Report, in order of severity:

1. ERRORS — wrong formula, wrong clause, wrong coefficient, unit
   inconsistency, or a check that tests the wrong criterion.
2. VALIDITY — inputs or intermediate results outside the validity range
   of the cited clauses (state the range and the clause).
3. ASSUMPTIONS — implicit assumptions the tool makes but does not state
   (loading type, cracked/uncracked, load duration, exposure class...).
4. PITFALLS — situations where a competent user would still get a wrong
   answer (edge cases, national-annex parameters, interaction with
   other checks that this tool does not cover).
5. SUGGESTIONS — clearer symbols, missing references, better checks.

For every finding cite the clause you are checking against. If a formula
is correct, do not praise it — silence means pass. End with a verdict:
APPROVE / APPROVE-WITH-COMMENTS / REWORK.
"""


def build_review_prompt(sheet: CalcSheet) -> str:
    """Complete QA prompt for any LLM — usable today without an API."""
    reference = sheet.reference or "the applicable design standard"
    header = REVIEW_INSTRUCTIONS.format(
        schema=CalcSheet.SCHEMA, reference=reference
    )
    return (
        f"{header}\n"
        "----- TOOL (machine-readable calcsheet JSON) -----\n"
        f"{sheet.to_json()}\n"
        "----- END TOOL -----\n"
    )


class AIReviewer(Protocol):
    def review(self, sheet: CalcSheet) -> str:
        """Return the review text for a sheet."""
        ...


class AnthropicReviewer:
    """Claude-backed reviewer — skeleton until an API key is provisioned.

    Intended implementation (requirements: ``pip install anthropic``,
    env var ``ANTHROPIC_API_KEY``)::

        from anthropic import Anthropic

        client = Anthropic()
        message = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4096,
            messages=[{"role": "user",
                       "content": build_review_prompt(sheet)}],
        )
        return message.content[0].text
    """

    def review(self, sheet: CalcSheet) -> str:
        raise NotImplementedError(
            "AI review API is not wired up yet. Use "
            "`python main.py qa <slug> --prompt` to export the review "
            "prompt and paste it into Claude, or implement "
            "AnthropicReviewer per the docstring."
        )
