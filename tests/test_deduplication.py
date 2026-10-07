from __future__ import annotations

from datetime import UTC, datetime

from app.deduplication import DuplicateDetector, SemanticTextEncoder
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


def test_encoder_cache_returns_an_identical_vector() -> None:
    text = "Acme releases a reasoning model with a measured evaluation."
    encoder = SemanticTextEncoder()
    first = encoder.encode(text)
    assert encoder.encode(text) == first
    assert SemanticTextEncoder(cache_size=0).encode(text) == first


def test_history_similarity_encodes_each_text_once() -> None:
    class CountingEncoder(SemanticTextEncoder):
        def __init__(self) -> None:
            super().__init__()
            self.computations = 0

        def _vectorize(self, text: str) -> list[float]:
            self.computations += 1
            return super()._vectorize(text)

    encoder = CountingEncoder()
    detector = DuplicateDetector(encoder=encoder)
    history = ["First post. A summary.", "Second post. Another summary.", "Third post. More."]
    for index in range(5):
        detector.history_similarity(
            article(f"Candidate {index}", f"https://example.com/{index}"), history
        )
    # Five candidate texts plus three history texts, rather than 5 * (1 + 3).
    assert encoder.computations == 8
