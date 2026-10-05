from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ranking import TopicRanker
from app.schemas import NormalizedArticle


def make_article(title: str, hours_old: int, source_quality: float) -> NormalizedArticle:
    return NormalizedArticle(
        source_name="Lab",
        source_url="https://example.com",
        source_quality=source_quality,
        external_id=title,
        title=title,
        url=f"https://example.com/{hours_old}/{source_quality}",
        canonical_url=f"https://example.com/{hours_old}/{source_quality}",
        summary="Technical model benchmark and inference details for developers",
        published_at=datetime.now(UTC) - timedelta(hours=hours_old),
    )


def test_recent_primary_source_ranks_above_old_weak_source() -> None:
    weights = {
        "recency": 0.25,
        "source_quality": 0.20,
        "importance": 0.20,
        "novelty": 0.15,
        "technical_relevance": 0.10,
        "social_interest": 0.10,
    }
    ranker = TopicRanker(weights)
    recent = make_article("Lab releases an open source reasoning model", 1, 0.98)
    old = make_article("A minor AI opinion", 70, 0.55)
    ranked = ranker.rank([old, recent])
    assert ranked[0].title == recent.title
    assert ranked[0].score > ranked[1].score


def test_history_similarity_reduces_novelty() -> None:
    ranker = TopicRanker({"novelty": 1.0})
    item = make_article("Repeated story", 1, 0.9)
    score = ranker.rank([item], {item.canonical_url: 0.9})[0]
    assert score.score == 10.0
