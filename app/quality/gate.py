"""Deterministic pre-publication quality checks."""

from __future__ import annotations

import re

from app.deduplication import SemanticTextEncoder
from app.schemas import GeneratedContent, QualityResult, VerifiedTopic

HYPE_PHRASES = {
    "ai is changing the world",
    "game changer",
    "game-changing",
    "revolutionary",
    "in today's rapidly evolving world",
    "transform everything",
    "unprecedented breakthrough",
}


class QualityGate:
    def __init__(
        self,
        threshold: int = 85,
        max_length: int = 2800,
        duplicate_threshold: float = 0.78,
        min_confidence: float = 0.72,
        encoder: SemanticTextEncoder | None = None,
    ) -> None:
        self.threshold = threshold
        self.max_length = max_length
        self.duplicate_threshold = duplicate_threshold
        self.min_confidence = min_confidence
        self.encoder = encoder or SemanticTextEncoder()

    @staticmethod
    def _numbers(value: str) -> set[str]:
        without_urls = re.sub(r"https?://\S+", "", value)
        return set(re.findall(r"(?<!\w)\d+(?:[.,]\d+)?%?", without_urls))

    @staticmethod
    def _supplied_evidence(verified: VerifiedTopic) -> str:
        """Return every piece of source material the generator was given.

        ``build_user_prompt`` supplies the topic title and summary, the supported
        claims, and each source title with its publication date, so a number the
        post draws from any of them is source-derived rather than invented.
        Checking the claim text alone rejects a post for citing the date it was
        handed, which is the behaviour the prompt asks for.
        """

        return " ".join(
            [
                verified.topic.title,
                verified.topic.summary,
                *(claim.text for claim in verified.claims if claim.supported),
                *verified.source_titles,
                *verified.source_publication_dates,
            ]
        )

    def evaluate(
        self,
        content: GeneratedContent,
        verified: VerifiedTopic,
        historical_content: list[str] | None = None,
    ) -> QualityResult:
        historical_content = historical_content or []
        score = 100
        issues: list[str] = []
        supported_claims = [claim for claim in verified.claims if claim.supported]
        evidence_word_count = sum(len(claim.text.split()) for claim in supported_claims)
        evidence_richness = evidence_word_count >= 10
        source_available = bool(verified.source_urls) and all(
            url.startswith(("https://", "http://")) for url in verified.source_urls
        )
        no_unsupported_claims = all(claim.supported for claim in verified.claims)
        if not source_available:
            score -= 25
            issues.append("No usable source URL")
        if verified.confidence_score < self.min_confidence:
            score -= 25
            issues.append(
                f"Verification confidence is below {self.min_confidence:.2f}"
            )
        if not evidence_richness:
            score -= 30
            issues.append("Supported source material is too thin for a substantive post")
        if not no_unsupported_claims:
            score -= min(30, 10 * sum(not claim.supported for claim in verified.claims))
            issues.append("One or more extracted claims are unsupported")

        lower = content.content.lower()
        hype_found = sorted(phrase for phrase in HYPE_PHRASES if phrase in lower)
        if hype_found:
            score -= min(20, 5 * len(hype_found))
            issues.append("Hype language: " + ", ".join(hype_found))
        length_valid = 120 <= len(content.content) <= self.max_length
        if not length_valid:
            score -= 15
            issues.append(f"Content length {len(content.content)} is outside configured bounds")

        evidence_text = self._supplied_evidence(verified)
        extra_numbers = self._numbers(content.content) - self._numbers(evidence_text)
        factual_consistency = not extra_numbers
        if not factual_consistency:
            score -= 25
            issues.append(
                "Generated content introduced unsupported numbers: " + ", ".join(extra_numbers)
            )

        paragraphs = [part.strip() for part in content.content.split("\n") if part.strip()]
        clarity = (
            len(paragraphs) >= 4
            and max((len(part.split()) for part in paragraphs), default=0) <= 80
        )
        if not clarity:
            score -= 10
            issues.append("Content needs clearer paragraph structure")
        grammar = bool(re.search(r"[.!?。！？:]", content.content))
        if not grammar:
            score -= 5
            issues.append("Content has no sentence punctuation")

        vector = self.encoder.encode(f"{content.title}. {content.summary}")
        highest_similarity = max(
            (
                self.encoder.similarity(vector, self.encoder.encode(previous))
                for previous in historical_content
            ),
            default=0.0,
        )
        not_duplicate = highest_similarity < self.duplicate_threshold
        if not not_duplicate:
            score -= 30
            issues.append(f"Content resembles publication history ({highest_similarity:.2f})")

        score = max(0, min(100, score))
        checks = {
            "source_availability": source_available,
            "confidence": verified.confidence_score >= self.min_confidence,
            "evidence_richness": evidence_richness,
            "unsupported_claims": no_unsupported_claims,
            "no_hype": not hype_found,
            "length": length_valid,
            "factual_consistency": factual_consistency,
            "clarity": clarity,
            "grammar": grammar,
            "not_duplicate": not_duplicate,
        }
        critical = (
            source_available
            and evidence_richness
            and factual_consistency
            and no_unsupported_claims
            and not_duplicate
        )
        return QualityResult(
            score=score,
            passed=score >= self.threshold and critical,
            checks=checks,
            issues=issues,
        )
