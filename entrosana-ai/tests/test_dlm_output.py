"""Strict DLM tool-call envelope parsing tests."""

import json

import pytest

from app.dlm.intent import ToolCall, _parse_tool_call
from app.dlm.output import DLMOutputError, parse_tool_call


def test_valid_tool_call_parses_to_existing_tool_call():
    text = '{"tool":"journal.list","args":{"date_from":"2026-05-01"}}'

    parsed = parse_tool_call(text)
    routed = _parse_tool_call(text)

    assert parsed.tool == "journal.list"
    assert parsed.args == {"date_from": "2026-05-01"}
    assert routed == ToolCall("journal.list", {"date_from": "2026-05-01"})


@pytest.mark.parametrize(
    "text",
    [
        '```json\n{"tool":"journal.list","args":{}}\n```',
        '```\n{"tool":"journal.list","args":{}}\n```',
    ],
)
def test_markdown_fences_are_stripped(text):
    assert parse_tool_call(text).tool == "journal.list"


@pytest.mark.parametrize(
    "text",
    [
        '{"args":{}}',
        '{"tool":""}',
        '{"tool":"x","args":{},"evil":1}',
        "[]",
        '"tool"',
        "42",
        '{"tool":"x","args":[]}',
        '{"tool":"x","args":"nope"}',
    ],
)
def test_malformed_envelopes_raise_dlm_output_error(text):
    with pytest.raises(DLMOutputError):
        parse_tool_call(text)


def test_missing_args_defaults_to_empty_object():
    assert parse_tool_call('{"tool":"journal.list"}').args == {}


def test_invalid_json_error_is_truncated():
    oversized = "x" * 1000

    with pytest.raises(DLMOutputError) as exc_info:
        parse_tool_call(oversized)

    message = str(exc_info.value)
    assert len(message) < len(oversized)
    assert oversized not in message


def test_dlm_output_error_is_value_error():
    assert issubclass(DLMOutputError, ValueError)


def test_parse_tool_call_accepts_json_serialized_envelope():
    text = json.dumps({"tool": "journal.list", "args": {"limit": 10}})

    assert _parse_tool_call(text).args == {"limit": 10}
