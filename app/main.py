"""FastAPI service, operator dashboard, and operational endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dashboard import router as dashboard_router
from app.database import get_db, get_session_factory, init_db, open_session
from app.models import GeneratedPost, RunHistory
from app.scheduler import create_scheduler
from app.services.concepts import seed_concepts
from app.utils.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with open_session() as session:
        seed_concepts(session)
        session.commit()
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = create_scheduler(settings, get_session_factory())
        scheduler.start()
    app.state.scheduler = scheduler
    app.state.pipeline_task = None
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/assets", StaticFiles(directory=static_dir), name="assets")
app.include_router(dashboard_router)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(static_dir / "dashboard.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready")
def ready(session: Session = Depends(get_db)) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready"}


@app.get("/posts")
def list_posts(limit: int = 20, session: Session = Depends(get_db)) -> list[dict[str, object]]:
    posts = session.scalars(
        select(GeneratedPost).order_by(desc(GeneratedPost.created_at)).limit(min(limit, 100))
    ).all()
    return [
        {
            "id": post.id,
            "title": post.title,
            "mode": post.mode,
            "status": post.status,
            "quality_score": post.quality_score,
            "confidence_score": post.confidence_score,
            "created_at": post.created_at,
        }
        for post in posts
    ]


@app.get("/runs")
def list_runs(limit: int = 20, session: Session = Depends(get_db)) -> list[dict[str, object]]:
    runs = session.scalars(
        select(RunHistory).order_by(desc(RunHistory.started_at)).limit(min(limit, 100))
    ).all()
    return [
        {
            "run_id": run.run_id,
            "status": run.status,
            "step": run.current_step,
            "counts": run.counts,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        }
        for run in runs
    ]
