from __future__ import annotations

from datetime import UTC, datetime

from app.deduplication import DuplicateDetector
from app.schemas import NormalizedArticle


def article(title: str, url: str, summary: str = "") -> NormalizedArticle:
    return NormalizedArticle(
        source_name="Test",
        source_url="https://example.com",
        source_quality=0.9,
        external_id=url,
        title=title,
        url=url,
        canonical_url=url,
        summary=summary,
        published_at=datetime.now(UTC),
    )


def test_exact_url_duplicate_is_removed() -> None:
    detector = DuplicateDetector()
    result = detector.deduplicate(
        [
            article("First version", "https://example.com/x"),
            article("Syndicated version", "https://example.com/x"),
        ]
    )
    assert len(result.unique) == 1
    assert result.duplicates[0][1] == "canonical_url"


def test_semantic_paraphrase_is_removed() -> None:
    detector = DuplicateDetector(semantic_threshold=0.48)
    result = detector.deduplicate(
        [
            article(
                "Acme releases a new reasoning model",
                "https://a.example/x",
                "The open source model improves reasoning benchmark results.",
            ),
            article(
                "Acme launches new model for reasoning",
                "https://b.example/y",
                "The open sourced model improves results on reasoning benchmarks.",
            ),
        ]
    )
    assert len(result.unique) == 1
    assert result.duplicates[0][1] == "semantic_similarity"
