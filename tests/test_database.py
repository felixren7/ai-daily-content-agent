from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.database import create_db_engine, get_engine, get_session_factory, open_session
from app.models import Article, Base, Source


def test_source_and_article_can_be_persisted(db_session) -> None:
    source = Source(name="Example Lab", url="https://example.com/feed", credibility=0.9)
    db_session.add(source)
    db_session.flush()
    db_session.add(
        Article(
            source_id=source.id,
            external_id="item-1",
            title="A grounded AI update",
            url="https://example.com/item-1",
            canonical_url="https://example.com/item-1",
            published_at=datetime.now(UTC),
            content_hash="a" * 64,
        )
    )
    db_session.commit()
    article = db_session.scalar(select(Article))
    assert article is not None
    assert article.source.name == "Example Lab"


def test_engine_and_session_factory_are_built_once() -> None:
    assert get_engine() is get_engine()
    assert get_session_factory() is get_session_factory()


def test_open_session_closes_without_committing() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with open_session(factory) as session:
        session.add(Source(name="Uncommitted", url="https://example.com"))
        session.flush()
    with factory() as session:
        assert session.scalar(select(Source)) is None
