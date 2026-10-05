"""Evidence-bounded claim extraction and confidence scoring."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.schemas import CandidateTopic, FactClaim, NormalizedArticle, VerifiedTopic
from app.utils.text import normalize_text

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

CONCEPT_REFERENCES: dict[str, list[tuple[str, str]]] = {
    "Agentic AI": [("A Survey on LLM-based Autonomous Agents", "https://arxiv.org/abs/2308.11432")],
    "Model Context Protocol": [
        ("Model Context Protocol specification", "https://modelcontextprotocol.io/specification/")
    ],
    "Retrieval-Augmented Generation": [("RAG paper", "https://arxiv.org/abs/2005.11401")],
    "GraphRAG": [("Microsoft GraphRAG", "https://microsoft.github.io/graphrag/")],
    "Vector Database": [
        ("Vector database concepts", "https://www.pinecone.io/learn/vector-database/")
    ],
    "Embeddings": [("Sentence-BERT paper", "https://arxiv.org/abs/1908.10084")],
    "Mixture of Experts": [("Switch Transformers paper", "https://arxiv.org/abs/2101.03961")],
    "KV Cache": [("Attention Is All You Need", "https://arxiv.org/abs/1706.03762")],
    "Quantization": [("GPTQ paper", "https://arxiv.org/abs/2210.17323")],
    "Distillation": [("Knowledge distillation paper", "https://arxiv.org/abs/1503.02531")],
    "DPO": [("Direct Preference Optimization paper", "https://arxiv.org/abs/2305.18290")],
    "Test-Time Compute": [("Scaling LLM Test-Time Compute", "https://arxiv.org/abs/2408.03314")],
    "Vision-Language-Action Models": [("RT-2 paper", "https://arxiv.org/abs/2307.15818")],
    "Context Engineering": [("Prompting Guide", "https://www.promptingguide.ai/")],
    "Agent Memory": [("Generative Agents paper", "https://arxiv.org/abs/2304.03442")],
    "Synthetic Data": [("Self-Instruct paper", "https://arxiv.org/abs/2212.10560")],
}


def _valid_source_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _sentences(article: NormalizedArticle) -> list[str]:
    text = article.summary or article.content or article.title
    candidates = _SENTENCE_SPLIT.split(text)
    clean = [item.strip() for item in candidates if len(item.split()) >= 4]
    return clean[:6] or [article.title]


def _overlap(left: str, right: str) -> float:
    a = set(normalize_text(left).split())
    b = set(normalize_text(right).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class FactChecker:
    def __init__(self, minimum_confidence: float = 0.72) -> None:
        self.minimum_confidence = minimum_confidence

    def verify(self, topic: CandidateTopic) -> VerifiedTopic:
        if topic.mode == "concept":
            references = CONCEPT_REFERENCES.get(topic.title, [])
            claims = [
                FactClaim(
                    text=topic.summary,
                    source_urls=[url for _, url in references],
                    supported=bool(references),
                    confidence=0.86 if references else 0.45,
                    uncertainty=None if references else "No curated primary reference",
                )
            ]
            confidence = claims[0].confidence
            return VerifiedTopic(
                topic=topic,
                claims=claims,
                confidence_score=confidence,
                source_urls=[url for _, url in references],
                source_titles=[title for title, _ in references],
                source_publication_dates=[],
                rejected=confidence < self.minimum_confidence,
                rejection_reason=(
                    "Concept lacks a curated supporting source"
                    if confidence < self.minimum_confidence
                    else None
                ),
            )

        if topic.article is None:
            return VerifiedTopic(
                topic=topic,
                claims=[],
                confidence_score=0,
                source_urls=[],
                source_titles=[],
                source_publication_dates=[],
                rejected=True,
                rejection_reason="News topic has no source article",
            )
        if topic.article.metadata.get("prompt_injection_flagged"):
            source_url = str(topic.article.url)
            return VerifiedTopic(
                topic=topic,
                claims=[
                    FactClaim(
                        text=topic.article.title,
                        source_urls=[source_url],
                        supported=False,
                        confidence=0,
                        uncertainty="Source contains prompt-injection-like instructions",
                    )
                ],
                confidence_score=0,
                source_urls=[source_url],
                source_titles=[topic.article.title],
                source_publication_dates=[topic.article.published_at.isoformat()],
                rejected=True,
                rejection_reason="Primary source was flagged for prompt injection",
            )
        articles = [topic.article, *topic.related_articles]
        claims: list[FactClaim] = []
        for source in articles:
            valid_url = _valid_source_url(str(source.url))
            for sentence in _sentences(source):
                corroborated_urls = [
                    str(other.url)
                    for other in articles
                    if other is not source
                    and _overlap(sentence, f"{other.title} {other.summary}") >= 0.22
                ]
                corroboration = min(1.0, len(corroborated_urls) / 2)
                confidence = min(
                    1.0,
                    0.55 * source.source_quality
                    + (0.25 if valid_url else 0)
                    + 0.20 * corroboration,
                )
                supported = valid_url and (source.source_quality >= 0.65 or bool(corroborated_urls))
                claims.append(
                    FactClaim(
                        text=sentence,
                        source_urls=[str(source.url), *corroborated_urls],
                        supported=supported,
                        confidence=round(confidence, 3),
                        uncertainty=None if supported else "Low-credibility or unavailable source",
                    )
                )
        supported_claims = [claim for claim in claims if claim.supported]
        supported_word_count = sum(len(claim.text.split()) for claim in supported_claims)
        confidence = (
            sum(claim.confidence for claim in supported_claims) / len(supported_claims)
            if supported_claims
            else 0.0
        )
        source_urls = list(dict.fromkeys(str(article.url) for article in articles))
        rejected = (
            confidence < self.minimum_confidence
            or not supported_claims
            or supported_word_count < 10
        )
        if supported_word_count < 10:
            rejection_reason = "Source material is too thin for a grounded post"
        elif confidence < self.minimum_confidence:
            rejection_reason = (
                f"Verification confidence {confidence:.2f} is below {self.minimum_confidence:.2f}"
            )
        else:
            rejection_reason = None
        return VerifiedTopic(
            topic=topic,
            claims=claims,
            confidence_score=round(confidence, 3),
            source_urls=source_urls,
            source_titles=[article.title for article in articles],
            source_publication_dates=[article.published_at.isoformat() for article in articles],
            rejected=rejected,
            rejection_reason=rejection_reason,
        )
