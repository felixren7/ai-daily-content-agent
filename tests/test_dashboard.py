from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import create_db_engine, get_db
from app.main import app
from app.models import Base, GeneratedPost, RunHistory, Topic
from app.services.post_workflow import PostWorkflowError, PostWorkflowService


def _post(*, quality: int = 93, status: str = "pending_review") -> GeneratedPost:
    return GeneratedPost(
        mode="news",
        style="professional",
        title="A grounded AI update",
        summary="A factual summary for review.",
        content="What happened?\n\nA documented event occurred.\n\nWhy it matters: evidence.",
        content_hash="hash",
        source_urls=["https://example.com/source"],
        source_titles=["Primary source"],
        source_publication_dates=["2026-10-06T00:00:00+00:00"],
        extracted_facts=[
            {
                "text": "A documented event occurred.",
                "source_urls": ["https://example.com/source"],
                "supported": True,
                "confidence": 0.94,
                "uncertainty": None,
            }
        ],
        confidence_score=0.94,
        quality_score=quality,
        quality_report={
            "score": quality,
            "passed": quality >= 85,
            "checks": {"source_availability": True, "unsupported_claims": True},
            "issues": [],
        },
        status=status,
        llm_provider="template",
        llm_model="deterministic-template-v1",
    )


def test_dashboard_renders_live_database_data() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        topic = Topic(mode="news", title="AI update", score=88.5, selected=True)
        session.add(topic)
        session.flush()
        post = _post()
        post.topic_id = topic.id
        session.add(post)
        session.add(
            RunHistory(
                run_id="1b671a64-4f6a-4de9-8db6-5386f643aa01",
                mode="news",
                status="done",
                current_step="DONE",
                counts={"fetched": 42, "duplicates": 7, "ranked": 12, "post_id": 1},
                finished_at=datetime.now(UTC),
            )
        )
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app, raise_server_exceptions=True)
        page = client.get("/")
        assert page.status_code == 200
        assert "Review &amp; approve" in page.text

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        payload = response.json()
        assert payload["metrics"]["fetched"] == 42
        assert payload["selected_post"]["title"] == "A grounded AI update"
        assert payload["selected_post"]["topic_score"] == 88.5
        assert all(stage["state"] == "complete" for stage in payload["pipeline"])
        client.close()
    finally:
        app.dependency_overrides.clear()


def test_dashboard_approval_requires_action_header() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(_post())
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        rejected = client.post("/api/posts/1/approve")
        assert rejected.status_code == 400

        approved = client.post(
            "/api/posts/1/approve",
            headers={"X-Requested-With": "AI-Daily-Content-Agent"},
        )
        assert approved.status_code == 200
        assert approved.json()["post"]["status"] == "approved"

        dry_run = client.post(
            "/api/posts/1/publish",
            headers={"X-Requested-With": "AI-Daily-Content-Agent"},
        )
        assert dry_run.status_code == 200
        assert dry_run.json()["dry_run_skipped"] is True

        revision = client.post(
            "/api/posts/1/revision",
            headers={"X-Requested-With": "AI-Daily-Content-Agent"},
            json={"reason": "Clarify the technical example and keep the source boundary."},
        )
        assert revision.status_code == 200
        assert revision.json()["post"]["status"] == "revision_requested"
        client.close()
    finally:
        app.dependency_overrides.clear()


def test_workflow_rejects_post_below_quality_threshold(db_session) -> None:
    post = _post(quality=50)
    db_session.add(post)
    db_session.commit()

    service = PostWorkflowService(Settings(_env_file=None))
    try:
        service.approve(db_session, post.id)
    except PostWorkflowError as exc:
        assert "below the required" in str(exc)
    else:
        raise AssertionError("A low-quality post must not be approved")
