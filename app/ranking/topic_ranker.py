"""Configurable ranking for news candidates and evergreen concepts."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from app.schemas import CandidateTopic, NormalizedArticle
from app.utils.text import normalize_text

_IMPORTANCE_TERMS = {
    "release": 0.10,
    "model": 0.06,
    "benchmark": 0.08,
    "research": 0.06,
    "open source": 0.08,
    "safety": 0.08,
    "reasoning": 0.08,
    "agent": 0.07,
    "robotics": 0.07,
    "multimodal": 0.07,
    "inference": 0.06,
    "funding": 0.04,
}
_TECHNICAL_TERMS = {
    "architecture",
    "training",
    "inference",
    "benchmark",
    "parameter",
    "token",
    "agent",
    "reasoning",
    "multimodal",
    "robotics",
    "embedding",
    "quantization",
    "open source",
    "paper",
}
_SOCIAL_TERMS = {
    "available",
    "launch",
    "release",
    "free",
    "open source",
    "developer",
    "enterprise",
    "robot",
    "video",
    "image",
}


class TopicRanker:
    def __init__(self, weights: dict[str, float], max_age_hours: int = 72) -> None:
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Ranking weights must have a positive sum")
        self.weights = {key: value / total for key, value in weights.items()}
        self.max_age_hours = max_age_hours

    def _recency(self, article: NormalizedArticle, now: datetime) -> float:
        age_hours = max(0.0, (now - article.published_at).total_seconds() / 3600)
        if age_hours >= self.max_age_hours:
            return 0.0
        return math.exp(-age_hours / max(12, self.max_age_hours / 2))

    @staticmethod
    def _keyword_score(text: str, terms: set[str]) -> float:
        matches = sum(1 for term in terms if term in text)
        return min(1.0, matches / 4)

    def rank(
        self,
        articles: list[NormalizedArticle],
        history_similarity: dict[str, float] | None = None,
        now: datetime | None = None,
    ) -> list[CandidateTopic]:
        now = now or datetime.now(UTC)
        history_similarity = history_similarity or {}
        ranked: list[CandidateTopic] = []
        for article in articles:
            text = normalize_text(f"{article.title} {article.summary}")
            recency = self._recency(article, now)
            source_quality = article.source_quality
            importance = min(
                1.0,
                0.38 + sum(weight for term, weight in _IMPORTANCE_TERMS.items() if term in text),
            )
            duplicate_probability = history_similarity.get(article.canonical_url, 0.0)
            novelty = 1.0 - duplicate_probability
            technical = self._keyword_score(text, _TECHNICAL_TERMS)
            social = self._keyword_score(text, _SOCIAL_TERMS)
            breakdown = {
                "recency": recency,
                "source_quality": source_quality,
                "importance": importance,
                "novelty": novelty,
                "technical_relevance": technical,
                "social_interest": social,
            }
            weighted = sum(self.weights[key] * breakdown[key] for key in self.weights)
            ranked.append(
                CandidateTopic(
                    mode="news",
                    title=article.title,
                    article=article,
                    summary=article.summary,
                    score=round(weighted * 100, 2),
                    score_breakdown={
                        key: round(value * 100, 2) for key, value in breakdown.items()
                    },
                    duplicate_probability=duplicate_probability,
                )
            )
        return sorted(ranked, key=lambda item: item.score, reverse=True)
