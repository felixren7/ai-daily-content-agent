from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.models import Article, Source


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
