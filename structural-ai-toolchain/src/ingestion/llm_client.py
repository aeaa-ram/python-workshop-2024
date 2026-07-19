"""LLM client abstraction for the AI Grinder.

Kept deliberately thin so the interpreter never talks to a vendor SDK
directly. Two implementations:

- ``AnthropicLLMClient`` — Claude via the ``anthropic`` SDK. Requires
  ``pip install anthropic`` and ``ANTHROPIC_API_KEY``. Model defaults to a
  current Claude (override with ``GRINDER_LLM_MODEL``).
- ``NullLLMClient`` — always "unavailable"; makes the pipeline fall back
  to the deterministic heuristic interpreter, so nothing breaks offline.

``get_llm_client()`` returns the best available client. The client only
does one thing: ``complete_json(system, user)`` -> parsed dict, so the
interpreter can depend on structured output regardless of backend.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional, Protocol, runtime_checkable

DEFAULT_MODEL = os.getenv("GRINDER_LLM_MODEL", "claude-sonnet-5")


@runtime_checkable
class LLMClient(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 4096) -> dict:
        """Return the model's JSON response as a dict."""
        ...


class NullLLMClient:
    name = "null"

    def available(self) -> bool:
        return False

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 4096) -> dict:
        raise RuntimeError(
            "No LLM backend configured. Set ANTHROPIC_API_KEY and "
            "`pip install anthropic`, or the Grinder uses its heuristic "
            "interpreter instead."
        )


class AnthropicLLMClient:
    name = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._client = None

    def available(self) -> bool:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def _ensure(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def complete_json(self, system: str, user: str,
                      max_tokens: int = 4096) -> dict:
        client = self._ensure()
        # Nudge JSON-only output; parse defensively (strip prose/fences).
        msg = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system + "\n\nRespond with a single valid JSON object "
                            "and nothing else.",
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in msg.content
            if getattr(block, "type", None) == "text"
        )
        return _parse_json_loose(text)


def _parse_json_loose(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    return json.loads(text)


def get_llm_client(prefer: Optional[str] = None) -> LLMClient:
    """Best available client. ``prefer='null'`` forces the offline path."""
    if prefer == "null":
        return NullLLMClient()
    anthropic_client = AnthropicLLMClient()
    if anthropic_client.available():
        return anthropic_client
    return NullLLMClient()
