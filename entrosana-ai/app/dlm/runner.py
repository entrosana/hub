"""DLM runner -- the one entry point for LLM calls."""
from pathlib import Path
from typing import Any

import anthropic

from app.core.config import settings

PROMPTS_ROOT = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a versioned prompt from disk.  Raises if missing."""
    path = PROMPTS_ROOT / settings.dlm_prompt_version / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"prompt {name!r} version {settings.dlm_prompt_version!r} not found at {path}"
        )
    return path.read_text(encoding="utf-8")


async def run(
    prompt_name: str,
    input_data: dict[str, Any],
    *,
    retrieval_keys: list[str] | None = None,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Run a DLM call.  Deterministic.  Auditable.

    Returns a dict:
        {
          "output":           <str>,
          "model_version":    <str>,
          "prompt_version":   <str>,
          "retrieval_keys":   <list[str]>,
          "tokens_in":        <int>,
          "tokens_out":       <int>,
        }

    Callers MUST forward the returned dict to audit.record_dlm() so it lands
    in the dlm_interactions table.
    """
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    template = load_prompt(prompt_name)
    user_prompt = template.format(**input_data)
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.dlm_model_version,
        max_tokens=max_tokens,
        temperature=settings.dlm_temperature,
        messages=[{"role": "user", "content": user_prompt}],
    )
    output_text = resp.content[0].text if resp.content else ""
    return {
        "output": output_text,
        "model_version": settings.dlm_model_version,
        "prompt_version": settings.dlm_prompt_version,
        "retrieval_keys": sorted(retrieval_keys or []),
        "tokens_in": resp.usage.input_tokens,
        "tokens_out": resp.usage.output_tokens,
    }
