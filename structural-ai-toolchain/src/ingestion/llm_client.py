"""Backward-compatible import path; the client now lives in ``src.llm``."""

from src.llm.client import (  # noqa: F401
    DEFAULT_MODEL,
    AnthropicLLMClient,
    LLMClient,
    LLMError,
    NullLLMClient,
    ScriptedLLMClient,
    get_llm_client,
    parse_json_loose as _parse_json_loose,
)
