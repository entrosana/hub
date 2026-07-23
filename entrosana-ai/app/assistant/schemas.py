"""Request/response schemas for the assistant endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AssistantQueryIn(BaseModel):
    input: str = Field(min_length=1, max_length=2000, description="Natural-language request.")


class AssistantQueryOut(BaseModel):
    tool: str
    args: dict[str, Any]
    kind: str  # "query" | "mutation"
    executed: bool  # False ⇒ mutation preview awaiting confirmation
    count: int
    source: str  # provider that produced the result
    intent_hash: str
    result: Any = None
    summary: str = ""
