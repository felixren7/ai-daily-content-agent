"""Exact and semantic duplicate detection without heavyweight model downloads."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.schemas import NormalizedArticle
from app.utils.text import canonicalize_url, normalize_text, stable_hash

_ALIASES = {
    "artificial intelligence": "ai",
    "large language models": "llm",
    "large language model": "llm",
    "llms": "llm",
    "announced": "release",
    "announces": "release",
    "launched": "release",
    "launches": "release",
    "released": "release",
    "releases": "release",
    "unveiled": "release",
    "unveils": "release",
    "open sourced": "open source",
}


class SemanticTextEncoder:
    """Deterministic hashed feature encoder for semantic-ish similarity.

    It combines canonicalized concepts, word n-grams, and character n-grams.
    The interface can later be replaced by a model-backed embedding provider.
    """

    name = "hashed-concept-ngram-v1"

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    def _canonicalize(self, text: str) -> str:
        normalized = normalize_text(text)
        for phrase, replacement in _ALIASES.items():
            normalized = re.sub(rf"\b{re.escape(phrase)}\b", replacement, normalized)
        return normalized

    def encode(self, text: str) -> list[float]:
        normalized = self._canonicalize(text)
        tokens = normalized.split()
        features = list(tokens)
        features.extend(f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False))
        compact = normalized.replace(" ", "")
        features.extend(compact[index : index + 3] for index in range(max(0, len(compact) - 2)))
        vector = [0.0] * self.dimensions
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % self.dimensions
            vector[index] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude:
            vector = [value / magnitude for value in vector]
        return vector

    @staticmethod
    def similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        return max(0.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))


@dataclass
class DeduplicationResult:
    unique: list[NormalizedArticle] = field(default_factory=list)
    duplicates: list[tuple[NormalizedArticle, str, float]] = field(default_factory=list)


class DuplicateDetector:
    def __init__(
        self, semantic_threshold: float = 0.82, encoder: SemanticTextEncoder | None = None
    ):
        self.semantic_threshold = semantic_threshold
        self.encoder = encoder or SemanticTextEncoder()

    def deduplicate(self, articles: list[NormalizedArticle]) -> DeduplicationResult:
        result = DeduplicationResult()
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()
        fingerprints: list[tuple[str, list[float]]] = []
        ordered = sorted(
            articles, key=lambda item: (item.source_quality, item.published_at), reverse=True
        )
        for article in ordered:
            url = article.canonical_url or canonicalize_url(str(article.url))
            content_hash = stable_hash(article.title, article.summary)
            if url in seen_urls:
                result.duplicates.append((article, "canonical_url", 1.0))
                continue
            if content_hash in seen_hashes:
                result.duplicates.append((article, "content_hash", 1.0))
                continue
            normalized_title = normalize_text(article.title)
            vector = self.encoder.encode(f"{article.title}. {article.summary[:600]}")
            duplicate_reason: tuple[str, float] | None = None
            for prior_title, prior_vector in fingerprints:
                title_ratio = SequenceMatcher(None, normalized_title, prior_title).ratio()
                semantic_score = self.encoder.similarity(vector, prior_vector)
                if title_ratio >= 0.92:
                    duplicate_reason = ("title_similarity", title_ratio)
                    break
                if semantic_score >= self.semantic_threshold:
                    duplicate_reason = ("semantic_similarity", semantic_score)
                    break
            if duplicate_reason:
                result.duplicates.append((article, *duplicate_reason))
                continue
            seen_urls.add(url)
            seen_hashes.add(content_hash)
            fingerprints.append((normalized_title, vector))
            result.unique.append(article)
        return result

    def history_similarity(self, article: NormalizedArticle, historical_texts: list[str]) -> float:
        if not historical_texts:
            return 0.0
        candidate = self.encoder.encode(f"{article.title}. {article.summary[:600]}")
        return max(
            self.encoder.similarity(candidate, self.encoder.encode(text))
            for text in historical_texts
        )
