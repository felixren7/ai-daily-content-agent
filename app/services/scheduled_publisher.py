"""Persisted delayed-publication dispatcher."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import GeneratedPost, ScheduledPublication
from app.services.publisher import PublisherService

logger = logging.getLogger(__name__)


async def process_scheduled_publications(
    settings: Settings, session_factory: sessionmaker[Session]
) -> int:
    """Publish due records once and persist an explicit terminal state."""

    now = datetime.now(UTC)
    with session_factory() as session:
        due_ids = list(
            session.scalars(
                select(ScheduledPublication.id)
                .where(
                    ScheduledPublication.status == "scheduled",
                    ScheduledPublication.scheduled_for <= now,
                )
                .order_by(ScheduledPublication.scheduled_for)
                .limit(20)
            ).all()
        )

    processed = 0
    for schedule_id in due_ids:
        with session_factory() as session:
            claimed = session.execute(
                update(ScheduledPublication)
                .where(
                    ScheduledPublication.id == schedule_id,
                    ScheduledPublication.status == "scheduled",
                )
                .values(status="processing")
            )
            if claimed.rowcount != 1:
                session.rollback()
                continue
            session.commit()
            schedule = session.get(ScheduledPublication, schedule_id)
            if schedule is None:
                continue
            try:
                post = session.get(GeneratedPost, schedule.post_id)
                if post is None:
                    raise ValueError(f"Post {schedule.post_id} no longer exists")
                if post.status != "approved":
                    raise ValueError(
                        f"Post {post.id} is {post.status}; scheduled publication requires approved"
                    )
                if settings.dry_run:
                    schedule.status = "dry_run_skipped"
                    schedule.result_metadata = {"dry_run": True, "language": schedule.language}
                else:
                    results = await PublisherService(settings).publish(
                        session,
                        post,
                        ignore_auto_publish=True,
                        language=schedule.language,
                    )
                    schedule.result_metadata = {
                        "language": schedule.language,
                        "results": [result.model_dump(mode="json") for result in results],
                    }
                    schedule.status = (
                        "published"
                        if results and all(result.success for result in results)
                        else "failed"
                    )
                schedule.processed_at = datetime.now(UTC)
                session.commit()
                processed += 1
            except Exception as exc:
                session.rollback()
                failed = session.get(ScheduledPublication, schedule_id)
                if failed:
                    failed.status = "failed"
                    failed.error = str(exc)
                    failed.processed_at = datetime.now(UTC)
                    session.commit()
                logger.exception(
                    "Scheduled publication failed",
                    extra={"schedule_id": schedule_id, "error": str(exc)},
                )
    return processed
