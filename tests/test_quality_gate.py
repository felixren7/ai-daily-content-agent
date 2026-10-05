from __future__ import annotations

from app.quality import QualityGate
from app.schemas import CandidateTopic, FactClaim, GeneratedContent, VerifiedTopic


def verified_topic() -> VerifiedTopic:
    return VerifiedTopic(
        topic=CandidateTopic(mode="news", title="Measured release"),
        claims=[
            FactClaim(
                text=(
                    "The lab published a model card with evaluation details for independent review."
                ),
                source_urls=["https://example.com/model"],
                supported=True,
                confidence=0.9,
            )
        ],
        confidence_score=0.9,
        source_urls=["https://example.com/model"],
        source_titles=["Model card"],
        source_publication_dates=["2026-10-05T00:00:00+00:00"],
    )


def test_grounded_post_passes_quality_gate() -> None:
    content = GeneratedContent(
        title="Measured release",
        summary="The lab published a model card with evaluation details for independent review.",
        content=(
            "Measured release.\n\nWhat happened? The lab published a model card with evaluation "
            "details for independent review.\n\n"
            "Why it matters: teams can inspect the stated evaluation.\n\n"
            "Takeaway: compare the claims with independent tests before deployment."
        ),
        provider="test",
        model="test",
    )
    result = QualityGate().evaluate(content, verified_topic())
    assert result.passed
    assert result.score == 100


def test_hype_and_unsupported_number_are_penalized() -> None:
    content = GeneratedContent(
        title="Hype",
        summary="Hype",
        content=(
            "This revolutionary game changer improves results by 99%.\n\n"
            "AI is changing the world.\n\nDetails are unavailable.\n\nRead more at the source."
        ),
        provider="test",
        model="test",
    )
    result = QualityGate().evaluate(content, verified_topic())
    assert not result.passed
    assert not result.checks["factual_consistency"]
    assert not result.checks["no_hype"]


def test_duplicate_check_compares_topics_instead_of_shared_layout() -> None:
    content = GeneratedContent(
        title="Agent Memory",
        summary="Agents persist and retrieve useful information from earlier interactions.",
        content=(
            "Term.\n\nHow it works: information is persisted and selected later.\n\n"
            "Why it matters: context can span interactions.\n\nTakeaway: evaluate retrieval."
        ),
        provider="test",
        model="test",
    )
    history = [
        "Vector Database. A database stores embeddings and retrieves records by vector similarity."
    ]
    result = QualityGate().evaluate(content, verified_topic(), history)
    assert result.checks["not_duplicate"]
