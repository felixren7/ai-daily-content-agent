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


def grounded_content(sources_line: str) -> GeneratedContent:
    return GeneratedContent(
        title="Measured release",
        summary="The lab published a model card with evaluation details for independent review.",
        content=(
            "Measured release.\n\nWhat happened? The lab published a model card with evaluation "
            "details for independent review.\n\n"
            "Why it matters: teams can inspect the stated evaluation.\n\n"
            "Takeaway: compare the claims with independent tests before deployment.\n\n"
            f"Sources\n{sources_line}"
        ),
        provider="test",
        model="test",
    )


def test_citing_the_source_publication_date_is_grounded() -> None:
    # The prompt hands the generator the publication date, so quoting it in the
    # sources section is source-derived and must not count as an invented number.
    content = grounded_content("- Model card: https://example.com/model (published 2026-10-05)")
    result = QualityGate().evaluate(content, verified_topic())
    assert result.checks["factual_consistency"]
    assert result.score == 100
    assert result.passed


def test_numbers_from_a_source_title_are_grounded() -> None:
    topic = verified_topic()
    topic.source_titles = ["Llama 3.1 model card"]
    content = grounded_content("- Llama 3.1 model card: https://example.com/model")
    result = QualityGate().evaluate(content, topic)
    assert result.checks["factual_consistency"]


def test_invented_numbers_are_still_rejected() -> None:
    content = grounded_content("- Model card: https://example.com/model")
    content.content += "\n\nIt also improves throughput by 4321 tokens per second."
    result = QualityGate().evaluate(content, verified_topic())
    assert not result.checks["factual_consistency"]
    assert any("4321" in issue for issue in result.issues)


def test_confidence_threshold_follows_configuration() -> None:
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
    topic = verified_topic()  # confidence 0.9
    assert QualityGate().evaluate(content, topic).checks["confidence"]

    strict = QualityGate(min_confidence=0.95).evaluate(content, topic)
    assert not strict.checks["confidence"]
    assert strict.score == 75
    assert any("below 0.95" in issue for issue in strict.issues)


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
