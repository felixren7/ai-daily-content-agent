from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import create_db_engine
from app.llm import LLMProvider
from app.llm.base import LLMResponse
from app.models import Base, GeneratedPost, ScheduledPublication
from app.services.post_workflow import PostWorkflowService
from app.services.publisher import resolve_post_variant
from app.services.regeneration import RegenerationService
from app.services.scheduled_publisher import process_scheduled_publications
from app.services.translation import TranslationError, TranslationService


class FakeProvider(LLMProvider):
    provider_name = "fake"
    model = "fake-model"

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.system_prompt = ""
        self.user_prompt = ""

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
    ) -> LLMResponse:
        assert "untrusted DATA" in system_prompt
        assert "BEGIN_JSON" in user_prompt
        assert json_mode is True
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return LLMResponse(
            text=json.dumps(self.payload, ensure_ascii=False),
            provider=self.provider_name,
            model=self.model,
            metadata={"mocked": True},
        )


def grounded_post(*, status: str = "pending_review") -> GeneratedPost:
    source_url = "https://example.com/model-card"
    fact = (
        "The lab published a model card with evaluation details that teams can inspect "
        "before deployment."
    )
    return GeneratedPost(
        mode="news",
        style="professional",
        title="A measured model release",
        summary="The release includes a documented model card for technical review.",
        content=(
            "What happened?\n\nThe lab published a model card with evaluation details.\n\n"
            "Why it matters: teams can inspect the stated evidence before deployment.\n\n"
            f"Source: {source_url}"
        ),
        content_hash="grounded-hash",
        source_urls=[source_url],
        source_titles=["Official model card"],
        source_publication_dates=["2026-10-06T00:00:00+00:00"],
        extracted_facts=[
            {
                "text": fact,
                "source_urls": [source_url],
                "supported": True,
                "confidence": 0.94,
                "uncertainty": None,
            }
        ],
        confidence_score=0.94,
        quality_score=96,
        quality_report={"score": 96, "passed": True, "checks": {}, "issues": []},
        status=status,
        llm_provider="deepseek",
        llm_model="test-model",
        llm_metadata={},
    )


@pytest.mark.asyncio
async def test_chinese_translation_is_validated_cached_and_publishable(db_session) -> None:
    post = grounded_post()
    db_session.add(post)
    db_session.commit()
    source_url = post.source_urls[0]
    provider = FakeProvider(
        {
            "title": "一次克制的模型发布",
            "summary": "该发布提供了可供技术审查的模型卡。",
            "content": (
                "发生了什么？\n\n该实验室发布了包含评估细节的模型卡。\n\n"
                "为什么重要？团队可在部署前检查相关证据。\n\n"
                f"来源：{source_url}"
            ),
            "facts": ["该实验室发布了包含评估细节的模型卡，团队可在部署前进行检查。"],
        }
    )
    service = TranslationService(Settings(_env_file=None), provider=provider)

    translated_post, translation, cached = await service.translate_to_chinese(
        db_session, post.id
    )
    assert cached is False
    assert translation["validation"]["source_urls_preserved"] is True
    assert translation["provider"] == "fake"
    assert resolve_post_variant(translated_post, "zh")[0] == "一次克制的模型发布"

    _, second_translation, second_cached = await service.translate_to_chinese(
        db_session, post.id
    )
    assert second_cached is True
    assert second_translation == translation


@pytest.mark.asyncio
async def test_chinese_translation_rejects_new_numeric_claims(db_session) -> None:
    post = grounded_post()
    db_session.add(post)
    db_session.commit()
    provider = FakeProvider(
        {
            "title": "模型发布",
            "summary": "性能提升 99% 。",
            "content": f"性能提升 99% 。\n\n来源：{post.source_urls[0]}",
            "facts": ["性能提升 99% 。"],
        }
    )

    with pytest.raises(TranslationError, match="unsupported numbers"):
        await TranslationService(
            Settings(_env_file=None), provider=provider
        ).translate_to_chinese(db_session, post.id)


def test_translation_service_uses_the_translation_budget() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="compatible",
        compatible_api_key="key",
        compatible_base_url="https://example.com/v1",
        compatible_model="model",
        llm_max_tokens=1800,
        translation_max_tokens=12345,
        llm_timeout_seconds=222,
    )
    provider = TranslationService(settings).provider
    assert provider.max_tokens == 12345
    assert provider.timeout == 222


@pytest.mark.asyncio
async def test_translation_holds_the_body_citations_not_every_collected_url(db_session) -> None:
    # A news post collects corroborating sources but its body links only the
    # primary one, so requiring every collected URL makes the check unsatisfiable.
    post = grounded_post()
    post.source_urls = [*post.source_urls, "https://example.com/corroborating-source"]
    db_session.add(post)
    db_session.commit()
    body_url = post.source_urls[0]
    provider = FakeProvider(
        {
            "title": "一次克制的模型发布",
            "summary": "该发布提供了可供技术审查的模型卡。",
            "content": f"发生了什么？\n\n该实验室发布了包含评估细节的模型卡。\n\n来源：{body_url}",
            "facts": ["该实验室发布了包含评估细节的模型卡，团队可在部署前进行检查。"],
        }
    )

    _, translation, cached = await TranslationService(
        Settings(_env_file=None), provider=provider
    ).translate_to_chinese(db_session, post.id)

    assert cached is False
    assert body_url in translation["content"]


async def test_translation_still_rejects_a_dropped_body_citation(db_session) -> None:
    post = grounded_post()
    db_session.add(post)
    db_session.commit()
    provider = FakeProvider(
        {
            "title": "一次克制的模型发布",
            "summary": "该发布提供了可供技术审查的模型卡。",
            "content": "发生了什么？\n\n该实验室发布了包含评估细节的模型卡。（未附来源链接）",
            "facts": ["该实验室发布了包含评估细节的模型卡，团队可在部署前进行检查。"],
        }
    )

    with pytest.raises(TranslationError, match="omitted one or more source URLs"):
        await TranslationService(
            Settings(_env_file=None), provider=provider
        ).translate_to_chinese(db_session, post.id)


async def test_regeneration_preserves_evidence_and_supersedes_old_draft(db_session) -> None:
    post = grounded_post(status="quality_rejected")
    db_session.add(post)
    db_session.commit()
    source_url = post.source_urls[0]
    provider = FakeProvider(
        {
            "title": "What the new model card actually documents",
            "summary": "A source-grounded explanation of the published evaluation material.",
            "content": (
                "What happened? The lab published a model card with evaluation details that "
                "teams can inspect before deployment.\n\n"
                "Why it matters: the document gives reviewers a concrete evidence boundary.\n\n"
                "Technical view: teams can examine the stated evaluation details before making "
                "their own deployment decision.\n\n"
                "Takeaway: read the primary material and compare its claims with your use case.\n\n"
                f"Source: {source_url}"
            ),
        }
    )
    settings = Settings(_env_file=None, history_similarity_threshold=0.99)

    replacement = await RegenerationService(settings, provider=provider).regenerate(
        db_session, post.id, "Make the technical explanation clearer and keep the measured tone."
    )

    assert post.status == "superseded"
    assert replacement.id != post.id
    assert replacement.status == "pending_review"
    assert replacement.source_urls == post.source_urls
    assert replacement.llm_metadata["regenerated_from_post_id"] == post.id
    assert replacement.llm_metadata["human_feedback"].startswith("Make the technical")


async def test_regeneration_states_the_length_limit(db_session) -> None:
    post = grounded_post(status="quality_rejected")
    db_session.add(post)
    db_session.commit()
    provider = FakeProvider(
        {
            "title": "A tighter draft",
            "summary": "A short source-grounded summary of the published material.",
            "content": (
                f"A short grounded body citing the source.\n\nSource: {post.source_urls[0]}"
            ),
        }
    )
    settings = Settings(_env_file=None, max_post_length=1234)

    await RegenerationService(settings, provider=provider).regenerate(
        db_session, post.id, "Tighten the wording."
    )

    assert '"max_characters": 1234' in provider.user_prompt
    assert "max_characters limit" in provider.system_prompt


def test_approved_post_can_be_scheduled_with_explicit_language(db_session) -> None:
    post = grounded_post(status="approved")
    post.llm_metadata = {
        "translations": {
            "zh": {"title": "模型发布", "content": f"内容\n{post.source_urls[0]}"}
        }
    }
    db_session.add(post)
    db_session.commit()

    schedule = PostWorkflowService(Settings(_env_file=None)).schedule(
        db_session,
        post.id,
        datetime.now(UTC) + timedelta(hours=1),
        "zh",
    )

    assert schedule.status == "scheduled"
    assert schedule.language == "zh"
    assert schedule.post_id == post.id

    with pytest.raises(ValueError, match="active schedule"):
        asyncio.run(
            PostWorkflowService(Settings(_env_file=None)).publish(
                db_session, post.id, "zh"
            )
        )

    revised = PostWorkflowService(Settings(_env_file=None)).request_revision(
        db_session, post.id, "Replace the scheduled version with a clearer explanation."
    )
    assert revised.status == "revision_requested"
    assert schedule.status == "cancelled"
    assert schedule.processed_at is not None


@pytest.mark.asyncio
async def test_due_schedule_is_safely_consumed_in_dry_run() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        post = grounded_post(status="approved")
        session.add(post)
        session.flush()
        scheduled = ScheduledPublication(
            post_id=post.id,
            scheduled_for=datetime.now(UTC) - timedelta(minutes=1),
            language="original",
            status="scheduled",
        )
        session.add(scheduled)
        session.commit()
        schedule_id = scheduled.id

    processed = await process_scheduled_publications(Settings(_env_file=None), factory)

    assert processed == 1
    with factory() as session:
        stored = session.get(ScheduledPublication, schedule_id)
        assert stored is not None
        assert stored.status == "dry_run_skipped"
        assert stored.result_metadata == {"dry_run": True, "language": "original"}
        assert stored.processed_at is not None
