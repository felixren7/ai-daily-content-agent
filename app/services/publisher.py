"""Publication orchestration and audit logging."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import GeneratedPost, PublicationHistory
from app.platforms import PlatformPost, build_adapters
from app.schemas import PublishResult


class PublisherService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def publish(
        self,
        session: Session,
        post: GeneratedPost,
        *,
        ignore_auto_publish: bool = False,
    ) -> list[PublishResult]:
        if self.settings.dry_run:
            return []
        if not ignore_auto_publish and not self.settings.auto_publish:
            return []
        if post.quality_score < self.settings.min_quality_score:
            raise ValueError("Post does not meet the configured quality threshold")
        if post.confidence_score < self.settings.min_verification_confidence:
            raise ValueError("Post does not meet the verification confidence threshold")
        adapters = build_adapters(self.settings)
        if not adapters:
            raise ValueError("No publication adapters are enabled")
        platform_post = PlatformPost(
            post_id=post.id,
            title=post.title,
            content=post.content,
            source_urls=post.source_urls,
            image_urls=post.image_urls,
        )
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds, follow_redirects=True
        ) as client:
            results = [await adapter.publish(platform_post, client) for adapter in adapters]
        now = datetime.now(UTC)
        for result in results:
            session.add(
                PublicationHistory(
                    post_id=post.id,
                    platform=result.platform,
                    status="published" if result.success else "failed",
                    external_id=result.external_id,
                    response_metadata=result.response_metadata,
                    error=result.error,
                    published_at=now if result.success else None,
                )
            )
        successes = sum(result.success for result in results)
        if successes == len(results):
            post.status = "published"
            post.published_at = now
        elif successes:
            post.status = "partially_published"
            post.published_at = now
        else:
            post.status = "publish_failed"
            post.error = "; ".join(result.error or "Unknown error" for result in results)
        session.flush()
        return results
