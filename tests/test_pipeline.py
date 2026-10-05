from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.collectors.base import Collector, CollectorResult
from app.collectors.registry import CollectorRegistry
from app.config import Settings
from app.database import create_db_engine
from app.llm.template_provider import TemplateProvider
from app.models import Base, GeneratedPost
from app.schemas import CandidateTopic, NormalizedArticle
from app.services.pipeline import ContentPipeline


class FakeCollector(Collector):
    name = "Official Lab"

    async def fetch(self, client):
        return CollectorResult(
            source=self.name,
            articles=[
                NormalizedArticle(
                    source_name=self.name,
                    source_url="https://lab.example",
                    source_quality=0.98,
                    external_id="release-1",
                    title="Official Lab releases a documented reasoning model",
                    url="https://lab.example/releases/model",
                    canonical_url="https://lab.example/releases/model",
                    summary=(
                        "Official Lab published a reasoning model and documented its evaluation "
                        "method for developers."
                    ),
                    content="The primary source documents the model evaluation method.",
                    published_at=datetime.now(UTC),
                    metadata={"collector": "test"},
                )
            ],
        )


async def test_complete_pipeline_saves_dry_run_post(tmp_path) -> None:
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///:memory:",
        run_lock_path=tmp_path / "run.lock",
        content_mode="news",
        llm_provider="template",
        dry_run=True,
        scheduler_enabled=False,
    )
    pipeline = ContentPipeline(
        settings,
        factory,
        collector_registry=CollectorRegistry([FakeCollector()]),
        llm_provider=TemplateProvider(),
    )
    result = await pipeline.run(dry_run=True)
    assert result.status == "done"
    assert result.post_id is not None
    assert result.content and "Sources" in result.content
    with factory() as session:
        post = session.scalar(select(GeneratedPost))
        assert post is not None
        assert post.status == "pending_review"
        assert post.source_urls == ["https://lab.example/releases/model"]


def test_related_sources_require_event_level_similarity(tmp_path) -> None:
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        run_lock_path=tmp_path / "run.lock",
        llm_provider="template",
        scheduler_enabled=False,
    )
    pipeline = ContentPipeline(
        settings,
        factory,
        collector_registry=CollectorRegistry([FakeCollector()]),
        llm_provider=TemplateProvider(),
    )
    primary = NormalizedArticle(
        source_name="Official Lab",
        source_url="https://lab.example",
        source_quality=0.98,
        external_id="model",
        title="Official Lab releases a documented reasoning model",
        url="https://lab.example/model",
        canonical_url="https://lab.example/model",
        summary="The lab documented the reasoning model evaluation method.",
        published_at=datetime.now(UTC),
    )
    unrelated = NormalizedArticle(
        source_name="University",
        source_url="https://university.example",
        source_quality=0.95,
        external_id="workers",
        title="Researchers document worker protests",
        url="https://university.example/workers",
        canonical_url="https://university.example/workers",
        summary="A book studies workplace protests and employer responses in technology companies.",
        published_at=datetime.now(UTC),
    )
    candidate = CandidateTopic(
        mode="news", title=primary.title, article=primary, summary=primary.summary
    )
    attached = pipeline._attach_related(candidate, [primary, unrelated])
    assert attached.related_articles == []
