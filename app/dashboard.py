"""Dashboard read model and guarded review actions."""

from __future__ import annotations

import asyncio
import hmac
import logging
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.database import get_db, get_session_factory
from app.models import GeneratedPost, RunHistory, Source, Topic
from app.services.pipeline import ContentPipeline
from app.services.post_workflow import (
    PostNotFoundError,
    PostWorkflowError,
    PostWorkflowService,
)
from app.services.regeneration import RegenerationError, RegenerationService
from app.services.run_lock import FileRunLock
from app.services.translation import TranslationError, TranslationService

router = APIRouter(tags=["dashboard"])
logger = logging.getLogger(__name__)

ACTION_HEADER = "AI-Daily-Content-Agent"
REVIEWABLE_STATUSES = (
    "pending_review",
    "approved",
    "revision_requested",
    "quality_rejected",
)
PIPELINE_STAGES = (
    "FETCH",
    "NORMALIZE",
    "DEDUP",
    "RANK",
    "VERIFY",
    "GENERATE",
    "QUALITY_CHECK",
    "PUBLISH",
)


class RevisionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RunNowRequest(BaseModel):
    mode: Literal["news", "concept", "mixed"] | None = None


class PublishRequest(BaseModel):
    language: Literal["original", "zh"] = "original"


class ScheduleRequest(BaseModel):
    scheduled_for: datetime
    language: Literal["original", "zh"] = "original"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _source_rows(post: GeneratedPost) -> list[dict[str, str | None]]:
    maximum = max(
        len(post.source_urls or []),
        len(post.source_titles or []),
        len(post.source_publication_dates or []),
    )
    rows: list[dict[str, str | None]] = []
    for index in range(maximum):
        rows.append(
            {
                "title": (
                    post.source_titles[index]
                    if index < len(post.source_titles or [])
                    else "Source"
                ),
                "url": post.source_urls[index] if index < len(post.source_urls or []) else None,
                "published_at": (
                    post.source_publication_dates[index]
                    if index < len(post.source_publication_dates or [])
                    else None
                ),
            }
        )
    return rows


def serialize_post(post: GeneratedPost) -> dict[str, Any]:
    report = post.quality_report or {}
    checks = report.get("checks", {})
    translations = (post.llm_metadata or {}).get("translations", {})
    chinese = translations.get("zh") if isinstance(translations, dict) else None
    schedules = sorted(
        post.scheduled_publications or [], key=lambda item: item.scheduled_for, reverse=True
    )
    return {
        "id": post.id,
        "title": post.title,
        "summary": post.summary,
        "content": post.content,
        "mode": post.mode,
        "style": post.style,
        "status": post.status,
        "quality_score": post.quality_score,
        "quality_passed": bool(report.get("passed", False)),
        "quality_checks": [
            {"key": key, "passed": bool(value)} for key, value in checks.items()
        ],
        "quality_issues": report.get("issues", []),
        "confidence_score": post.confidence_score,
        "topic_score": post.topic.score if post.topic else None,
        "facts": post.extracted_facts or [],
        "sources": _source_rows(post),
        "images": post.image_urls or [],
        "llm": {
            "provider": post.llm_provider,
            "model": post.llm_model,
            "metadata": post.llm_metadata or {},
        },
        "revision_note": post.error if post.status == "revision_requested" else None,
        "approved_at": _iso(post.approved_at),
        "published_at": _iso(post.published_at),
        "created_at": _iso(post.created_at),
        "updated_at": _iso(post.updated_at),
        "character_count": len(post.content),
        "translations": {"zh": chinese} if isinstance(chinese, dict) else {},
        "active_schedule": next(
            (
                {
                    "id": item.id,
                    "scheduled_for": _iso(item.scheduled_for),
                    "language": item.language,
                    "status": item.status,
                }
                for item in schedules
                if item.status in {"scheduled", "processing"}
            ),
            None,
        ),
        "schedule_history": [
            {
                "id": item.id,
                "scheduled_for": _iso(item.scheduled_for),
                "language": item.language,
                "status": item.status,
                "processed_at": _iso(item.processed_at),
                "error": item.error,
            }
            for item in schedules[:5]
        ],
    }


def serialize_run(run: RunHistory) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "mode": run.mode,
        "status": run.status,
        "step": run.current_step,
        "counts": run.counts or {},
        "errors": run.error_logs or [],
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }


def _stage_state(run: RunHistory | None, stage: str) -> str:
    if run is None:
        return "waiting"
    if run.current_step == "DONE" or run.status == "done":
        return "complete"
    if run.current_step == "FAILED" or run.status == "failed":
        return "failed" if stage == PIPELINE_STAGES[-1] else "complete"
    try:
        current_index = PIPELINE_STAGES.index(run.current_step)
        stage_index = PIPELINE_STAGES.index(stage)
    except ValueError:
        return "waiting"
    if stage_index < current_index:
        return "complete"
    if stage_index == current_index:
        return "active"
    return "waiting"


def _require_dashboard_action(
    x_requested_with: str | None = Header(default=None),
    x_dashboard_token: str | None = Header(default=None),
) -> Settings:
    settings = get_settings()
    if x_requested_with != ACTION_HEADER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing dashboard action header",
        )
    configured = settings.dashboard_admin_token
    if configured:
        supplied = x_dashboard_token or ""
        if not hmac.compare_digest(configured.get_secret_value(), supplied):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid dashboard token",
            )
    return settings


def _workflow_error(exc: PostWorkflowError) -> HTTPException:
    status_code = 404 if isinstance(exc, PostNotFoundError) else 409
    return HTTPException(status_code=status_code, detail=str(exc))


@router.get("/api/dashboard")
def dashboard_data(
    request: Request,
    post_id: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    settings = get_settings()
    post_statement = (
        select(GeneratedPost)
        .options(selectinload(GeneratedPost.topic), selectinload(GeneratedPost.concept))
        .options(selectinload(GeneratedPost.scheduled_publications))
        .where(GeneratedPost.status.in_(REVIEWABLE_STATUSES))
        .order_by(desc(GeneratedPost.created_at))
        .limit(50)
    )
    review_queue = list(session.scalars(post_statement).all())
    selected = next((post for post in review_queue if post.id == post_id), None)
    if selected is None and review_queue:
        selected = review_queue[0]

    recent_runs = list(
        session.scalars(
            select(RunHistory).order_by(desc(RunHistory.started_at)).limit(8)
        ).all()
    )
    latest_run = recent_runs[0] if recent_runs else None
    scheduler = getattr(request.app.state, "scheduler", None)
    job = scheduler.get_job("daily-content-pipeline") if scheduler else None
    next_run = _iso(job.next_run_time) if job and job.next_run_time else None

    pending_count = session.scalar(
        select(func.count()).select_from(GeneratedPost).where(
            GeneratedPost.status == "pending_review"
        )
    ) or 0
    source_count = session.scalar(select(func.count()).select_from(Source)) or 0
    topic_count = session.scalar(select(func.count()).select_from(Topic)) or 0
    latest_counts = latest_run.counts if latest_run else {}
    pipeline_task = getattr(request.app.state, "pipeline_task", None)
    pipeline_running = bool(pipeline_task and not pipeline_task.done()) or bool(
        latest_run and latest_run.status == "running"
    )

    return {
        "system": {
            "name": settings.app_name,
            "environment": settings.environment,
            "timezone": settings.timezone,
            "post_time": settings.post_time,
            "mode": settings.content_mode,
            "auto_publish": settings.auto_publish,
            "dry_run": settings.dry_run,
            "scheduler_enabled": settings.scheduler_enabled,
            "next_run_at": next_run,
            "destinations": settings.enabled_platforms,
            "dashboard_auth_required": bool(settings.dashboard_admin_token),
            "quality_threshold": settings.min_quality_score,
            "confidence_threshold": settings.min_verification_confidence,
            "llm_provider": settings.llm_provider,
            "pipeline_running": pipeline_running,
            "refresh_interval_seconds": 5,
        },
        "metrics": {
            "fetched": latest_counts.get("fetched", 0),
            "duplicates": latest_counts.get("duplicates", 0),
            "ranked": latest_counts.get("ranked", 0),
            "pending": pending_count,
            "sources": source_count,
            "topics": topic_count,
        },
        "pipeline": [
            {"key": stage, "state": _stage_state(latest_run, stage)}
            for stage in PIPELINE_STAGES
        ],
        "selected_post": serialize_post(selected) if selected else None,
        "review_queue": [
            {
                "id": post.id,
                "title": post.title,
                "mode": post.mode,
                "status": post.status,
                "quality_score": post.quality_score,
                "confidence_score": post.confidence_score,
                "created_at": _iso(post.created_at),
            }
            for post in review_queue
        ],
        "latest_run": serialize_run(latest_run) if latest_run else None,
        "recent_runs": [serialize_run(run) for run in recent_runs],
    }


@router.post("/api/posts/{post_id}/approve")
def approve_post(
    post_id: int,
    session: Session = Depends(get_db),
    settings: Settings = Depends(_require_dashboard_action),
) -> dict[str, Any]:
    try:
        post = PostWorkflowService(settings).approve(session, post_id)
        session.commit()
    except PostWorkflowError as exc:
        session.rollback()
        raise _workflow_error(exc) from exc
    return {
        "message": "Post approved for publication",
        "post": serialize_post(post),
        "dry_run": settings.dry_run,
    }


@router.post("/api/posts/{post_id}/revision")
def request_revision(
    post_id: int,
    payload: RevisionRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(_require_dashboard_action),
) -> dict[str, Any]:
    try:
        post = PostWorkflowService(settings).request_revision(
            session, post_id, payload.reason
        )
        session.commit()
    except PostWorkflowError as exc:
        session.rollback()
        raise _workflow_error(exc) from exc
    return {"message": "Revision requested", "post": serialize_post(post)}


@router.post("/api/posts/{post_id}/publish")
async def publish_post(
    post_id: int,
    payload: PublishRequest | None = None,
    session: Session = Depends(get_db),
    settings: Settings = Depends(_require_dashboard_action),
) -> dict[str, Any]:
    language = payload.language if payload else "original"
    try:
        post, results, skipped = await PostWorkflowService(settings).publish(
            session, post_id, language
        )
        session.commit()
    except PostWorkflowError as exc:
        session.rollback()
        raise _workflow_error(exc) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "message": "Dry run: publication skipped" if skipped else "Publication attempt complete",
        "post": serialize_post(post),
        "dry_run_skipped": skipped,
        "results": [result.model_dump(mode="json") for result in results],
        "language": language,
    }


@router.post("/api/posts/{post_id}/translate/zh")
async def translate_post_to_chinese(
    post_id: int,
    session: Session = Depends(get_db),
    settings: Settings = Depends(_require_dashboard_action),
) -> dict[str, Any]:
    try:
        post, translation, cached = await TranslationService(settings).translate_to_chinese(
            session, post_id
        )
        session.commit()
    except (TranslationError, RuntimeError) as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "message": "Chinese translation loaded" if cached else "Chinese translation generated",
        "post": serialize_post(post),
        "translation": translation,
        "cached": cached,
    }


@router.post("/api/posts/{post_id}/regenerate")
async def regenerate_post(
    post_id: int,
    payload: RevisionRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(_require_dashboard_action),
) -> dict[str, Any]:
    try:
        replacement = await RegenerationService(settings).regenerate(
            session, post_id, payload.reason
        )
        session.commit()
    except (RegenerationError, RuntimeError) as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "message": "A revised draft was generated",
        "post": serialize_post(replacement),
        "post_id": replacement.id,
    }


@router.post("/api/posts/{post_id}/schedule")
def schedule_post(
    post_id: int,
    payload: ScheduleRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(_require_dashboard_action),
) -> dict[str, Any]:
    try:
        schedule = PostWorkflowService(settings).schedule(
            session, post_id, payload.scheduled_for, payload.language
        )
        session.commit()
    except PostWorkflowError as exc:
        session.rollback()
        raise _workflow_error(exc) from exc
    return {
        "message": "Publication scheduled",
        "schedule": {
            "id": schedule.id,
            "scheduled_for": _iso(schedule.scheduled_for),
            "language": schedule.language,
            "status": schedule.status,
            "dry_run": settings.dry_run,
        },
    }


async def _run_pipeline_task(settings: Settings, mode: str | None) -> None:
    try:
        await ContentPipeline(settings, get_session_factory()).run(mode=mode)
    except Exception as exc:
        logger.exception("Dashboard-triggered pipeline failed", extra={"error": str(exc)})


@router.post("/api/pipeline/run")
async def run_pipeline_now(
    request: Request,
    payload: RunNowRequest | None = None,
    settings: Settings = Depends(_require_dashboard_action),
) -> dict[str, Any]:
    active = getattr(request.app.state, "pipeline_task", None)
    if active and not active.done():
        raise HTTPException(status_code=409, detail="A pipeline run is already active")
    if FileRunLock(settings.run_lock_path).is_active():
        raise HTTPException(status_code=409, detail="Another pipeline process holds the run lock")
    mode = payload.mode if payload else None
    task = asyncio.create_task(_run_pipeline_task(settings, mode))
    request.app.state.pipeline_task = task
    return {
        "message": "Pipeline run started",
        "mode": mode or settings.content_mode,
        "status": "accepted",
    }
