"""Tests for the Anthropic runner boundary without network access."""

from types import SimpleNamespace

import anthropic
import pytest

from app.dlm import runner

pytestmark = pytest.mark.anyio


class _Messages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class _Client:
    def __init__(self, response):
        self.messages = _Messages(response)
        self.closed = False

    async def close(self):
        self.closed = True


async def test_run_uses_prompt_and_returns_auditable_metadata(monkeypatch):
    text = anthropic.types.TextBlock(type="text", text='{"tool":"journal.list","args":{}}')
    response = SimpleNamespace(
        content=[SimpleNamespace(type="thinking"), text],
        usage=SimpleNamespace(input_tokens=7, output_tokens=3),
    )
    client = _Client(response)
    monkeypatch.setattr(runner, "get_anthropic_client", lambda: client)

    result = await runner.run(
        "intent_route",
        {"user_input": "List entries"},
        retrieval_keys=["z", "a"],
        max_tokens=42,
    )

    assert result == {
        "output": '{"tool":"journal.list","args":{}}',
        "model_version": runner.settings.dlm_model_version,
        "prompt_version": runner.settings.dlm_prompt_version,
        "retrieval_keys": ["a", "z"],
        "tokens_in": 7,
        "tokens_out": 3,
    }
    assert client.messages.kwargs["max_tokens"] == 42
    assert client.messages.kwargs["messages"][0]["content"].endswith("\nList entries\n")


async def test_run_returns_empty_output_when_no_text_block(monkeypatch):
    response = SimpleNamespace(
        content=[SimpleNamespace(type="thinking")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=2),
    )
    monkeypatch.setattr(runner, "get_anthropic_client", lambda: _Client(response))

    result = await runner.run("intent_route", {"user_input": "Nothing"})

    assert result["output"] == ""
    assert result["retrieval_keys"] == []


async def test_anthropic_client_lifecycle(monkeypatch):
    client = _Client(SimpleNamespace())
    monkeypatch.setattr(runner, "_ANTHROPIC_CLIENT", client)

    await runner.close_anthropic_client()

    assert client.closed is True
    assert runner._ANTHROPIC_CLIENT is None
    await runner.close_anthropic_client()


def test_get_anthropic_client_requires_configuration(monkeypatch):
    monkeypatch.setattr(runner.settings, "anthropic_api_key", None)
    monkeypatch.setattr(runner, "_ANTHROPIC_CLIENT", None)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        runner.get_anthropic_client()


def test_load_prompt_reports_missing_version(monkeypatch):
    monkeypatch.setattr(runner.settings, "dlm_prompt_version", "missing")

    with pytest.raises(FileNotFoundError, match="prompt"):
        runner.load_prompt("intent_route")
