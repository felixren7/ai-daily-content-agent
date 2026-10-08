"""End-to-end autonomous content pipeline."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors import CollectorRegistry
from app.config import Settings
from app.deduplication import DuplicateDetector
from app.generation import ContentGenerator
from app.generation.image_generator import CompatibleImageGenerator
from app.llm import LLMProvider, create_llm_provider
from app.models import Article, GeneratedPost, RunHistory, Source, Topic
from app.quality import QualityGate
from app.ranking import TopicRanker
from app.schemas import CandidateTopic, NormalizedArticle
from app.services.concepts import seed_concepts, select_concept
from app.services.publisher import PublisherService
from app.services.run_lock import FileRunLock
from app.utils.logging import run_id_context
from app.utils.text import canonicalize_url, stable_hash
from app.verification import FactChecker

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    run_id: str
    status: str
    post_id: int | None = None
    selected_title: str | None = None
    content: str | None = None
    quality_score: int | None = None
    confidence_score: float | None = None
    fetched_count: int = 0
    duplicate_count: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


class ContentPipeline:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        collector_registry: CollectorRegistry | None = None,
        llm_provider: LLMProvider | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.collectors = collector_registry or CollectorRegistry.from_settings(settings)
        self.llm_provider = llm_provider or create_llm_provider(settings)
        self.progress = progress or (lambda _: None)
        self.detector = DuplicateDetector(settings.similarity_threshold)
        self.ranker = TopicRanker(settings.scoring_weights, settings.article_max_age_hours)
        self.fact_checker = FactChecker(settings.min_verification_confidence)
        self.quality_gate = QualityGate(
            settings.min_quality_score,
            settings.max_post_length,
            settings.history_similarity_threshold,
            min_confidence=settings.min_verification_confidence,
            # Share one encoder so a text cached here also serves duplicate detection.
            encoder=self.detector.encoder,
        )

    def _step(self, run: RunHistory, session: Session, step: str, message: str) -> None:
        run.current_step = step
        session.commit()
        logger.info(message, extra={"step": step})
        self.progress(message)

    async def fetch_articles(self) -> tuple[list[NormalizedArticle], list[dict[str, str]]]:
        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": (
                "application/rss+xml, application/atom+xml, application/json, "
                "text/xml;q=0.9, */*;q=0.5"
            ),
        }
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            results = await self.collectors.fetch_all(client)
        articles = [article for result in results for article in result.articles]
        errors = [
            {"source": result.source, "error": error}
            for result in results
            for error in result.errors
        ]
        cutoff = datetime.now(UTC) - timedelta(hours=self.settings.article_max_age_hours)
        articles = [article for article in articles if article.published_at >= cutoff]
        return articles, errors

    def persist_articles(
        self, session: Session, articles: list[NormalizedArticle]
    ) -> dict[str, Article]:
        persisted: dict[str, Article] = {}
        for item in articles:
            source = session.scalar(select(Source).where(Source.name == item.source_name))
            if source is None:
                source = Source(
                    name=item.source_name,
                    url=item.source_url,
                    kind=str(item.metadata.get("collector", "rss")),
                    credibility=item.source_quality,
                )
                session.add(source)
                session.flush()
            elif source.credibility != item.source_quality:
                # Follow the configured credibility so the rank command and the
                # dashboard read the same number the run verified against.
                source.credibility = item.source_quality
            article = session.scalar(
                select(Article).where(
                    Article.source_id == source.id, Article.external_id == item.external_id
                )
            )
            if article is None:
                article = Article(
                    source_id=source.id,
                    external_id=item.external_id,
                    title=item.title,
                    url=str(item.url),
                    canonical_url=item.canonical_url or canonicalize_url(str(item.url)),
                    summary=item.summary,
                    raw_content=item.content,
                    author=item.author,
                    published_at=item.published_at,
                    content_hash=stable_hash(item.title, item.summary),
                    embedding=self.detector.encoder.encode(f"{item.title}. {item.summary[:600]}"),
                    embedding_metadata={"encoder": self.detector.encoder.name},
                    extra_metadata=item.metadata,
                )
                session.add(article)
                session.flush()
            persisted[item.canonical_url] = article
        session.commit()
        return persisted

    @staticmethod
    def published_history(session: Session) -> list[str]:
        """Load every generated post once per run for the similarity comparisons.

        Ranking and the quality gate both compare against the complete history, so
        the caller loads it a single time and passes it to both. The scan is
        deliberately unbounded: a new post must stay distinguishable from every
        earlier one, so do not add a LIMIT here.
        """

        return [
            f"{title}. {summary}"
            for title, summary in session.execute(
                select(GeneratedPost.title, GeneratedPost.summary)
            ).all()
        ]

    def rank_articles(
        self,
        session: Session,
        articles: list[NormalizedArticle],
        *,
        history: list[str] | None = None,
    ) -> tuple[list[CandidateTopic], int]:
        deduped = self.detector.deduplicate(articles)
        history = self.published_history(session) if history is None else history
        similarities = {
            item.canonical_url: self.detector.history_similarity(item, history)
            for item in deduped.unique
        }
        ranked = self.ranker.rank(deduped.unique, similarities)
        ranked = [
            item
            for item in ranked
            if item.duplicate_probability < self.settings.history_similarity_threshold
        ]
        return ranked, len(deduped.duplicates)

    def _attach_related(
        self, candidate: CandidateTopic, articles: list[NormalizedArticle]
    ) -> CandidateTopic:
        if candidate.article is None:
            return candidate
        primary_vector = self.detector.encoder.encode(
            f"{candidate.article.title}. {candidate.article.summary[:600]}"
        )
        related: list[tuple[float, NormalizedArticle]] = []
        for item in articles:
            if item.canonical_url == candidate.article.canonical_url:
                continue
            score = self.detector.encoder.similarity(
                primary_vector,
                self.detector.encoder.encode(f"{item.title}. {item.summary[:600]}"),
            )
            # Corroborating sources must describe the same event, not merely share broad AI terms.
            if score >= 0.65:
                related.append((score, item))
        candidate.related_articles = [item for _, item in sorted(related, reverse=True)[:3]]
        return candidate

    def _choose_mode(self, session: Session, ranked_news: list[CandidateTopic]) -> str:
        if self.settings.content_mode != "mixed":
            return self.settings.content_mode
        if self.settings.mixed_mode_strategy == "importance":
            return "news" if ranked_news and ranked_news[0].score >= 65 else "concept"
        previous = session.scalar(
            select(GeneratedPost.mode).order_by(desc(GeneratedPost.created_at)).limit(1)
        )
        return "concept" if previous == "news" else "news"

    def _select_verified_candidate(
        self,
        session: Session,
        mode: str,
        ranked_news: list[CandidateTopic],
        all_articles: list[NormalizedArticle],
    ):
        if mode == "concept":
            concept = select_concept(session)
            if concept is None:
                raise RuntimeError("No active frontier concepts are available")
            return self.fact_checker.verify(concept)
        for candidate in ranked_news:
            verified = self.fact_checker.verify(self._attach_related(candidate, all_articles))
            if not verified.rejected:
                return verified
            # Without this the rejection of every candidate is invisible, which is
            # how a source below the solo-credibility floor fails silently.
            logger.info(
                "Rejected candidate %r: %s",
                candidate.title,
                verified.rejection_reason,
                extra={"step": "VERIFY"},
            )
        raise RuntimeError("No news candidate passed fact verification")

    async def run(
        self,
        *,
        dry_run: bool | None = None,
        mode: str | None = None,
    ) -> PipelineRunResult:
        effective_dry_run = self.settings.dry_run if dry_run is None else dry_run
        run_id = str(uuid.uuid4())
        token = run_id_context.set(run_id)
        result = PipelineRunResult(run_id=run_id, status="running")
        with FileRunLock(self.settings.run_lock_path):
            with self.session_factory() as session:
                run = RunHistory(run_id=run_id, mode=mode or self.settings.content_mode)
                session.add(run)
                session.commit()
                try:
                    seed_concepts(session)
                    session.commit()
                    self._step(run, session, "FETCH", "Fetching AI sources...")
                    articles, source_errors = await self.fetch_articles()
                    result.fetched_count = len(articles)
                    result.errors = source_errors
                    self.progress(f"Found {len(articles)} articles")
                    self._step(run, session, "NORMALIZE", "Normalizing and storing articles...")
                    article_records = self.persist_articles(session, articles)

                    self._step(run, session, "DEDUP", "Removing duplicate stories...")
                    history = self.published_history(session)
                    ranked, duplicate_count = self.rank_articles(
                        session, articles, history=history
                    )
                    result.duplicate_count = duplicate_count
                    self.progress(f"Removed {duplicate_count} duplicates")
                    self._step(run, session, "RANK", f"Ranking {len(ranked)} topics...")
                    selected_mode = mode or self._choose_mode(session, ranked)
                    self._step(run, session, "VERIFY", "Verifying sources...")
                    verified = self._select_verified_candidate(
                        session, selected_mode, ranked, articles
                    )
                    result.selected_title = verified.topic.title
                    self.progress(f"Selected: {verified.topic.title}")

                    article_id = None
                    if verified.topic.article:
                        record = article_records.get(verified.topic.article.canonical_url)
                        article_id = record.id if record else None
                    topic_record = Topic(
                        article_id=article_id,
                        mode=verified.topic.mode,
                        title=verified.topic.title,
                        score=verified.topic.score,
                        score_breakdown=verified.topic.score_breakdown,
                        duplicate_probability=verified.topic.duplicate_probability,
                        selected=True,
                        status="verified",
                    )
                    session.add(topic_record)
                    session.flush()

                    self._step(run, session, "GENERATE", "Generating post...")
                    generated = await ContentGenerator(
                        self.llm_provider,
                        self.settings.content_style,
                        self.settings.max_post_length,
                    ).generate(verified)
                    image_urls: list[str] = []
                    if self.settings.image_generation_enabled:
                        assert self.settings.image_api_key is not None
                        assert self.settings.image_base_url is not None
                        assert self.settings.image_model is not None
                        image_result = await CompatibleImageGenerator(
                            self.settings.image_api_key.get_secret_value(),
                            self.settings.image_base_url,
                            self.settings.image_model,
                            self.settings.image_size,
                        ).generate(generated.title, generated.summary)
                        image_urls = image_result.urls
                    self._step(run, session, "QUALITY_CHECK", "Evaluating content quality...")
                    quality = self.quality_gate.evaluate(generated, verified, history)
                    result.quality_score = quality.score
                    result.confidence_score = verified.confidence_score
                    self.progress(f"Quality score: {quality.score}")

                    status = "pending_review"
                    if not quality.passed:
                        status = "quality_rejected"
                    elif self.settings.auto_publish and not effective_dry_run:
                        status = "approved"
                    post = GeneratedPost(
                        topic_id=topic_record.id,
                        concept_id=verified.topic.concept_id,
                        mode=verified.topic.mode,
                        style=self.settings.content_style,
                        title=generated.title,
                        summary=generated.summary,
                        content=generated.content,
                        content_hash=stable_hash(generated.content),
                        source_urls=verified.source_urls,
                        source_titles=verified.source_titles,
                        source_publication_dates=verified.source_publication_dates,
                        extracted_facts=[
                            claim.model_dump(mode="json") for claim in verified.claims
                        ],
                        image_urls=image_urls,
                        confidence_score=verified.confidence_score,
                        quality_score=quality.score,
                        quality_report=quality.model_dump(mode="json"),
                        status=status,
                        llm_provider=generated.provider,
                        llm_model=generated.model,
                        llm_metadata=generated.metadata,
                    )
                    session.add(post)
                    session.commit()
                    result.post_id = post.id
                    result.content = post.content
                    self._step(
                        run, session, "PUBLISH", "Saving post and evaluating publication mode..."
                    )

                    if effective_dry_run:
                        self.progress("DRY RUN — publication skipped.")
                    elif not self.settings.auto_publish:
                        self.progress("AUTO_PUBLISH=false — post stored as pending_review.")
                    elif not quality.passed:
                        self.progress("Quality gate failed — publication skipped.")
                    else:
                        await PublisherService(self.settings).publish(session, post)
                        session.commit()
                        self.progress(f"Publication status: {post.status}")

                    if verified.topic.concept_id:
                        concept = verified.topic.concept_id
                        from app.models import Concept

                        concept_record = session.get(Concept, concept)
                        if concept_record:
                            concept_record.times_published += 1
                            concept_record.last_published_at = datetime.now(UTC)

                    run.status = "done"
                    run.current_step = "DONE"
                    run.counts = {
                        "fetched": len(articles),
                        "duplicates": duplicate_count,
                        "ranked": len(ranked),
                        "post_id": post.id,
                    }
                    run.error_logs = source_errors
                    run.finished_at = datetime.now(UTC)
                    session.commit()
                    result.status = "done"
                    self.progress("DONE")
                    return result
                except Exception as exc:
                    session.rollback()
                    failed_run = session.scalar(
                        select(RunHistory).where(RunHistory.run_id == run_id)
                    )
                    if failed_run:
                        failed_run.status = "failed"
                        failed_run.current_step = "FAILED"
                        failed_run.error_logs = [
                            *result.errors,
                            {"source": "pipeline", "error": str(exc)},
                        ]
                        failed_run.finished_at = datetime.now(UTC)
                        session.commit()
                    logger.exception("Pipeline failed", extra={"step": "FAILED", "error": str(exc)})
                    result.status = "failed"
                    raise
                finally:
                    run_id_context.reset(token)
