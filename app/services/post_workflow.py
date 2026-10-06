"""Shared review, approval, and publication workflow for generated posts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import GeneratedPost, ScheduledPublication
from app.schemas import PublishResult
from app.services.publisher import PublisherService, resolve_post_variant


class PostWorkflowError(ValueError):
    """Raised when a post cannot make the requested workflow transition."""


class PostNotFoundError(PostWorkflowError):
    """Raised when a post does not exist."""


class PostWorkflowService:
    """Apply consistent review safeguards across the dashboard and CLI."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_post(self, session: Session, post_id: int) -> GeneratedPost:
        post = session.get(GeneratedPost, post_id)
        if post is None:
            raise PostNotFoundError(f"Post {post_id} not found")
        return post

    @staticmethod
    def cancel_active_schedules(post: GeneratedPost, reason: str) -> int:
        cancelled = 0
        for schedule in post.scheduled_publications:
            if schedule.status in {"scheduled", "processing"}:
                schedule.status = "cancelled"
                schedule.processed_at = datetime.now(UTC)
                schedule.error = reason
                cancelled += 1
        return cancelled

    def approve(self, session: Session, post_id: int) -> GeneratedPost:
        post = self.get_post(session, post_id)
        if post.status not in {"pending_review", "revision_requested"}:
            raise PostWorkflowError(
                f"Post {post_id} cannot be approved from status {post.status}"
            )
        if post.quality_score < self.settings.min_quality_score:
            raise PostWorkflowError(
                f"Quality score {post.quality_score} is below the required "
                f"{self.settings.min_quality_score}"
            )
        if post.confidence_score < self.settings.min_verification_confidence:
            raise PostWorkflowError(
                f"Confidence {post.confidence_score:.2f} is below the required "
                f"{self.settings.min_verification_confidence:.2f}"
            )
        post.status = "approved"
        post.approved_at = datetime.now(UTC)
        post.error = None
        session.flush()
        return post

    def request_revision(self, session: Session, post_id: int, reason: str) -> GeneratedPost:
        post = self.get_post(session, post_id)
        if post.status not in {"pending_review", "approved"}:
            raise PostWorkflowError(
                f"Post {post_id} cannot request revision from status {post.status}"
            )
        clean_reason = " ".join(reason.split())
        if not clean_reason:
            raise PostWorkflowError("A revision reason is required")
        if len(clean_reason) > 1000:
            raise PostWorkflowError("Revision reason must be 1000 characters or fewer")
        post.status = "revision_requested"
        post.approved_at = None
        post.error = f"Human review: {clean_reason}"
        self.cancel_active_schedules(post, "Cancelled because the post entered revision")
        session.flush()
        return post

    async def publish(
        self, session: Session, post_id: int, language: str = "original"
    ) -> tuple[GeneratedPost, list[PublishResult], bool]:
        post = self.get_post(session, post_id)
        if post.status != "approved":
            raise PostWorkflowError("Post must be approved before publication")
        if any(
            item.status in {"scheduled", "processing"}
            for item in post.scheduled_publications
        ):
            raise PostWorkflowError(
                "Post already has an active schedule; request a revision to replace it"
            )
        resolve_post_variant(post, language)
        if self.settings.dry_run:
            return post, [], True
        results = await PublisherService(self.settings).publish(
            session, post, ignore_auto_publish=True, language=language
        )
        return post, results, False

    def schedule(
        self,
        session: Session,
        post_id: int,
        scheduled_for: datetime,
        language: str = "original",
    ) -> ScheduledPublication:
        post = self.get_post(session, post_id)
        if post.status != "approved":
            raise PostWorkflowError("Post must be approved before it can be scheduled")
        if scheduled_for.tzinfo is None:
            raise PostWorkflowError("Scheduled publication time must include a timezone")
        publish_at = scheduled_for.astimezone(UTC)
        now = datetime.now(UTC)
        if publish_at <= now + timedelta(seconds=30):
            raise PostWorkflowError(
                "Scheduled publication must be at least 30 seconds in the future"
            )
        if publish_at > now + timedelta(days=365):
            raise PostWorkflowError("Scheduled publication cannot be more than one year ahead")
        resolve_post_variant(post, language)
        active = next(
            (
                item
                for item in post.scheduled_publications
                if item.status in {"scheduled", "processing"}
            ),
            None,
        )
        if active:
            raise PostWorkflowError(
                f"Post {post_id} already has active schedule {active.id}"
            )
        schedule = ScheduledPublication(
            scheduled_for=publish_at,
            language=language,
            status="scheduled",
        )
        post.scheduled_publications.append(schedule)
        session.flush()
        return schedule
