"""The shared LLM client: request shape, structured output, refusals and
the offline fallbacks — all without network access."""

import json
from types import SimpleNamespace

import pytest

from src.llm import (
    AnthropicLLMClient,
    LLMError,
    LLMRefusal,
    NullLLMClient,
    ScriptedLLMClient,
    get_llm_client,
    schemas,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
PDF = b"%PDF-1.7\n" + b"\x00" * 16


class _FakeStream:
    def __init__(self, message, sink, kwargs):
        self._message, self._sink, self._kwargs = message, sink, kwargs

    def __enter__(self):
        self._sink.append(self._kwargs)
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


def _fake_sdk(message, sink):
    stream = lambda **kw: _FakeStream(message, sink, kw)  # noqa: E731
    return SimpleNamespace(beta=SimpleNamespace(
        messages=SimpleNamespace(stream=stream)))


def _message(text, stop="end_turn"):
    return SimpleNamespace(
        stop_reason=stop, stop_details=None,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def test_request_uses_structured_output_vision_and_fallback():
    sink: list = []
    client = AnthropicLLMClient()
    client._client = _fake_sdk(_message(json.dumps(
        {"verdict": "APPROVE", "findings": [], "corrections": []})), sink)
    out = client.complete_json("sys", "check this", schema=schemas.REVIEW,
                               images=[PNG], documents=[PDF], task="review")
    assert out["verdict"] == "APPROVE"
    kw = sink[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["output_config"]["effort"] == "high"
    assert kw["fallbacks"] == "default"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"]
    blocks = kw["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["document", "image", "text"]
    assert blocks[1]["source"]["media_type"] == "image/png"
    assert client.usage["requests"] == 1


def test_refusal_and_truncation_raise_typed_errors():
    client = AnthropicLLMClient()
    client._client = _fake_sdk(_message("", stop="refusal"), [])
    with pytest.raises(LLMRefusal):
        client.complete_json("s", "u", schema=schemas.REVIEW)
    client._client = _fake_sdk(_message("{", stop="max_tokens"), [])
    with pytest.raises(LLMError):
        client.complete_json("s", "u", schema=schemas.REVIEW)


def test_offline_paths(monkeypatch):
    assert isinstance(get_llm_client(prefer="null"), NullLLMClient)
    monkeypatch.setenv("TOOLCHAIN_LLM", "off")
    assert not AnthropicLLMClient().available()
    with pytest.raises(LLMError):
        NullLLMClient().complete_json("s", "u")


def test_scripted_client_records_calls_and_rejects_unknown_tasks():
    llm = ScriptedLLMClient({"research": {"x": 1}})
    assert llm.complete_json("s", "u", task="research", images=[PNG]) == {"x": 1}
    assert llm.calls[0].task == "research" and llm.calls[0].n_images == 1
    with pytest.raises(LLMError):
        llm.complete_json("s", "u", task="unexpected")


def test_schemas_are_strict():
    def walk(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                walk(child)
        elif node.get("type") == "array":
            walk(node["items"])

    for schema in (schemas.INTERPRETATION, schemas.RESEARCH, schemas.REVIEW,
                   schemas.ORIGINAL_VALUES):
        walk(schema)


def test_llm_interpreter_falls_back_to_heuristic_on_failure(tmp_path):
    from examples.make_fixtures import make_messy_beam_xlsx
    from src.ingestion.interpret import LLMInterpreter
    from src.ingestion.workbook_extract import extract_workbook

    digest = extract_workbook(make_messy_beam_xlsx(tmp_path))
    interp = LLMInterpreter(ScriptedLLMClient({})).interpret(digest)
    assert interp.interpreter.startswith("heuristic (LLM unavailable")
    assert interp.variables
