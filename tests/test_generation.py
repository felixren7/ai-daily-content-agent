from __future__ import annotations

import json

from app.generation import ContentGenerator
from app.generation.prompts import build_user_prompt
from app.llm import LLMProvider
from app.llm.base import LLMResponse
from app.schemas import CandidateTopic, FactClaim, VerifiedTopic


def verified_topic() -> VerifiedTopic:
    return VerifiedTopic(
        topic=CandidateTopic(
            mode="news",
            title="Measured release",
            summary="The lab published a model card with evaluation details.",
        ),
        claims=[
            FactClaim(
                text="The lab published a model card with evaluation details for review.",
                source_urls=["https://example.com/model"],
                supported=True,
                confidence=0.9,
            )
        ],
        confidence_score=0.9,
        source_urls=["https://example.com/model"],
        source_titles=["Model card"],
        source_publication_dates=["2026-10-05T00:00:00+00:00"],
    )


class RecordingProvider(LLMProvider):
    provider_name = "recording"
    model = "recording-v1"

    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
    ) -> LLMResponse:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return LLMResponse(
            text=json.dumps({"title": "Title", "summary": "Summary", "content": "Content"}),
            provider=self.provider_name,
            model=self.model,
        )


def test_user_prompt_states_the_configured_length_limit() -> None:
    # The quality gate rejects an over-length post, so the generator has to be
    # told the bound it is measured against.
    prompt = build_user_prompt(verified_topic(), "professional", 2800)
    assert "under 2800 characters" in prompt


def test_user_prompt_still_carries_the_untrusted_data_boundary() -> None:
    prompt = build_user_prompt(verified_topic(), "professional", 2800)
    assert "BEGIN_JSON" in prompt
    assert "untrusted source DATA" in prompt


async def test_content_generator_forwards_its_length_limit() -> None:
    provider = RecordingProvider()
    await ContentGenerator(provider, max_length=1234).generate(verified_topic())
    assert "under 1234 characters" in provider.user_prompt
