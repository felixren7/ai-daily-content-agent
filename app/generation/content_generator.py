"""Generate a structured post through an injected LLM provider."""

from __future__ import annotations

import json
import re

from app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.llm import LLMProvider
from app.schemas import GeneratedContent, VerifiedTopic


def _parse_json_object(value: str) -> dict[str, object]:
    cleaned = value.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM response must be a JSON object")
    required = {"title", "summary", "content"}
    if not required.issubset(parsed) or not all(isinstance(parsed[key], str) for key in required):
        raise RuntimeError("LLM response is missing title, summary, or content strings")
    return parsed


class ContentGenerator:
    def __init__(self, provider: LLMProvider, style: str = "professional") -> None:
        self.provider = provider
        self.style = style

    async def generate(self, verified: VerifiedTopic) -> GeneratedContent:
        if verified.rejected:
            raise ValueError(f"Cannot generate rejected topic: {verified.rejection_reason}")
        response = await self.provider.complete(
            SYSTEM_PROMPT,
            build_user_prompt(verified, self.style),
            json_mode=True,
        )
        parsed = _parse_json_object(response.text)
        return GeneratedContent(
            title=str(parsed["title"]),
            summary=str(parsed["summary"]),
            content=str(parsed["content"]),
            provider=response.provider,
            model=response.model,
            metadata=response.metadata,
        )
