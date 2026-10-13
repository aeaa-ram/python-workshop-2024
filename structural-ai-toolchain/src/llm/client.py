"""One LLM client for the whole toolchain.

Every AI step (interpreting a messy spreadsheet, researching which code
clause a formula implements, the master reviewer reading the rendered PDF
next to the original) goes through ``complete_json``: a system prompt, a
user message, optional page images / PDFs, and a JSON schema the answer
must satisfy. Callers never touch a vendor SDK, so swapping the backend,
or running fully offline, changes nothing upstream.

Implementations
---------------
- ``AnthropicLLMClient`` — Claude through the official ``anthropic`` SDK:
  streaming, adaptive thinking with an explicit effort level, schema-
  constrained JSON (``output_config.format``), vision blocks for page
  images and PDF document blocks, server-side refusal fallback.
- ``ScriptedLLMClient`` — deterministic stand-in: answers are looked up by
  ``task`` (or produced by a callable). Used by the tests and for dry runs.
- ``NullLLMClient`` — "no AI available": every pipeline falls back to its
  deterministic path and says so in the audit trail.

``get_llm_client()`` picks the best available one. Configuration:
``TOOLCHAIN_LLM_MODEL`` (default ``claude-opus-5-5``),
``TOOLCHAIN_LLM_EFFORT`` (default ``high``), ``TOOLCHAIN_LLM=off`` to force
the offline path. ``GRINDER_LLM_MODEL`` is still honoured.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Protocol, Union, runtime_checkable

DEFAULT_MODEL = (os.getenv("TOOLCHAIN_LLM_MODEL")
                 or os.getenv("GRINDER_LLM_MODEL")
                 or "claude-opus-5-5")
DEFAULT_EFFORT = os.getenv("TOOLCHAIN_LLM_EFFORT", "high")

# Models that accept the server-side refusal fallback ("default" routing).
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5",
                    "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

Attachment = Union[bytes, str, Path, tuple]


class LLMError(RuntimeError):
    """The model could not produce a usable answer (network, auth, limits,
    malformed output). Callers degrade to their deterministic path."""


class LLMRefusal(LLMError):
    """The model declined the request (``stop_reason == 'refusal'``)."""


@runtime_checkable
class LLMClient(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def complete_json(self, system: str, user: str, *,
                      schema: Optional[dict] = None,
                      images: Iterable[Attachment] = (),
                      documents: Iterable[Attachment] = (),
                      task: str = "",
                      effort: Optional[str] = None,
                      max_tokens: int = 32000) -> dict:
        ...


# ---------------------------------------------------------------------- #
# Offline client
# ---------------------------------------------------------------------- #
class NullLLMClient:
    name = "null"
    model = ""

    def available(self) -> bool:
        return False

    def complete_json(self, system: str, user: str, **_: object) -> dict:
        raise LLMError(
            "No LLM backend configured. Set ANTHROPIC_API_KEY (or run "
            "`ant auth login`) and `pip install anthropic`; until then every "
            "stage uses its deterministic path.")


# ---------------------------------------------------------------------- #
# Scripted client (tests, dry runs)
# ---------------------------------------------------------------------- #
@dataclass
class LLMCall:
    task: str
    system: str
    user: str
    n_images: int
    n_documents: int
    schema: Optional[dict]


@dataclass
class ScriptedLLMClient:
    """Answers from a table keyed by ``task``; a value may be a dict or a
    callable ``(system, user) -> dict``. Missing tasks raise ``LLMError``
    so a test notices an unexpected AI call instead of passing silently."""

    responses: dict = field(default_factory=dict)
    name: str = "scripted"
    model: str = "scripted"
    calls: list = field(default_factory=list)

    def available(self) -> bool:
        return True

    def complete_json(self, system: str, user: str, *,
                      schema: Optional[dict] = None,
                      images: Iterable[Attachment] = (),
                      documents: Iterable[Attachment] = (),
                      task: str = "", effort: Optional[str] = None,
                      max_tokens: int = 32000) -> dict:
        images, documents = list(images), list(documents)
        self.calls.append(LLMCall(task, system, user, len(images),
                                  len(documents), schema))
        if task not in self.responses:
            raise LLMError(f"ScriptedLLMClient has no answer for task {task!r}")
        answer = self.responses[task]
        if callable(answer):
            answer = answer(system, user)
        return json.loads(json.dumps(answer))  # defensive copy, JSON-clean


# ---------------------------------------------------------------------- #
# Claude
# ---------------------------------------------------------------------- #
class AnthropicLLMClient:
    name = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL,
                 effort: str = DEFAULT_EFFORT) -> None:
        self.model = model
        self.effort = effort
        self._client = None
        self.usage = {"input_tokens": 0, "output_tokens": 0, "requests": 0}

    def available(self) -> bool:
        if os.getenv("TOOLCHAIN_LLM", "").lower() in ("off", "0", "false"):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return _has_credentials()

    def _sdk(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def complete_json(self, system: str, user: str, *,
                      schema: Optional[dict] = None,
                      images: Iterable[Attachment] = (),
                      documents: Iterable[Attachment] = (),
                      task: str = "", effort: Optional[str] = None,
                      max_tokens: int = 32000) -> dict:
        import anthropic

        content: list[dict] = []
        for doc in documents:
            data, _ = _load_attachment(doc, default_mime="application/pdf")
            content.append({"type": "document", "source": {
                "type": "base64", "media_type": "application/pdf",
                "data": base64.standard_b64encode(data).decode("ascii")}})
        for img in images:
            data, mime = _load_attachment(img, default_mime="image/png")
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": mime,
                "data": base64.standard_b64encode(data).decode("ascii")}})
        content.append({"type": "text", "text": user})

        output_config: dict = {"effort": effort or self.effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        else:
            system = (system + "\n\nAnswer with one JSON object and nothing "
                      "else.")
        kwargs: dict = dict(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": content}],
            output_config=output_config,
        )
        if self.model in _FALLBACK_MODELS:
            kwargs.update(betas=[_FALLBACK_BETA], fallbacks="default")

        try:
            with self._sdk().beta.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise LLMError(f"authentication failed: {exc}") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"model {self.model!r} not found: {exc}") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"request rejected: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError(f"rate limited: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"API error {exc.status_code}: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"network error: {exc}") from exc

        self.usage["requests"] += 1
        if getattr(msg, "usage", None) is not None:
            self.usage["input_tokens"] += msg.usage.input_tokens or 0
            self.usage["output_tokens"] += msg.usage.output_tokens or 0

        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMRefusal(f"model declined ({category or 'no category'})")
        if msg.stop_reason == "max_tokens":
            raise LLMError("answer truncated at max_tokens")
        text = "".join(b.text for b in msg.content
                       if getattr(b, "type", "") == "text")
        try:
            return json.loads(text) if schema is not None \
                else parse_json_loose(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMError(f"model did not return valid JSON: {exc}") from exc


def _has_credentials() -> bool:
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
        return True
    if os.getenv("ANTHROPIC_PROFILE"):
        return True
    if os.getenv("ANTHROPIC_FEDERATION_RULE_ID") and (
            os.getenv("ANTHROPIC_IDENTITY_TOKEN_FILE")
            or os.getenv("ANTHROPIC_IDENTITY_TOKEN")):
        return True
    cfg = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (cfg / "anthropic").is_dir()


def _load_attachment(item: Attachment, default_mime: str) -> tuple[bytes, str]:
    if isinstance(item, tuple):
        data, mime = item
        return (data if isinstance(data, bytes) else Path(data).read_bytes(),
                mime)
    data = item if isinstance(item, bytes) else Path(item).read_bytes()
    return data, _sniff_mime(data, default_mime)


def _sniff_mime(data: bytes, default: str) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return default


def parse_json_loose(text: str) -> dict:
    """Parse a JSON object from free text (fenced or embedded)."""
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
    client = AnthropicLLMClient()
    if client.available():
        return client
    return NullLLMClient()


def describe(client) -> str:
    """One-line label for audit trails: which AI (if any) took part."""
    if client is None or not client.available():
        return "none (deterministic path)"
    model = getattr(client, "model", "")
    return f"{client.name}:{model}" if model else client.name
