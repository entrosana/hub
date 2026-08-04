"""Strict parsing for structured output emitted by the DLM."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class DLMOutputError(ValueError):
    """Raised when a model response is not a valid tool-call envelope."""


class ToolCallEnvelope(BaseModel):
    """The exact JSON envelope accepted from the model."""

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.DOTALL)
        text = re.sub(r"\s*```\s*$", "", text, flags=re.DOTALL)
    return text


def _short_validation_error(error: ValidationError) -> str:
    parts = []
    for detail in error.errors():
        location = ".".join(str(part) for part in detail["loc"]) or "(root)"
        parts.append(f"{location}: {detail['msg']}")
    return "; ".join(parts)


def parse_tool_call(text: str) -> ToolCallEnvelope:
    """Parse and strictly validate a model tool-call response."""
    content = _strip_fence(text)
    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise DLMOutputError(f"LLM did not return valid JSON: {content[:200]!r}") from error
    if not isinstance(value, dict):
        raise DLMOutputError("LLM tool-call output must be a JSON object")
    try:
        return ToolCallEnvelope.model_validate(value)
    except ValidationError as error:
        raise DLMOutputError(
            f"Invalid LLM tool-call envelope: {_short_validation_error(error)}"
        ) from error
