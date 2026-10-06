"""Daily APScheduler configuration."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.services.pipeline import ContentPipeline
from app.services.run_lock import ConcurrentRunError
from app.services.scheduled_publisher import process_scheduled_publications

logger = logging.getLogger(__name__)


def create_scheduler(
    settings: Settings, session_factory: sessionmaker[Session]
) -> AsyncIOScheduler:
    timezone = ZoneInfo(settings.timezone)
    scheduler = AsyncIOScheduler(
        timezone=timezone,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
    )
    hour, minute = (int(part) for part in settings.post_time.split(":"))

    async def scheduled_run() -> None:
        try:
            await ContentPipeline(settings, session_factory).run()
        except ConcurrentRunError:
            logger.warning("Skipped scheduled run because another run is active")
        except Exception:
            logger.exception("Scheduled pipeline run failed")

    scheduler.add_job(
        scheduled_run,
        CronTrigger(hour=hour, minute=minute, timezone=timezone),
        id="daily-content-pipeline",
        replace_existing=True,
    )
    scheduler.add_job(
        process_scheduled_publications,
        IntervalTrigger(seconds=30, timezone=timezone),
        kwargs={"settings": settings, "session_factory": session_factory},
        id="scheduled-publication-dispatcher",
        replace_existing=True,
    )
    return scheduler
