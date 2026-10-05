"""Pydantic schemas passed between pipeline stages."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class NormalizedArticle(BaseModel):
    source_name: str
    source_url: str
    source_quality: float = Field(ge=0, le=1)
    external_id: str
    title: str = Field(min_length=3, max_length=1024)
    url: HttpUrl
    canonical_url: str = ""
    summary: str = ""
    content: str = ""
    author: str | None = None
    published_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class CandidateTopic(BaseModel):
    mode: Literal["news", "concept"]
    title: str
    article: NormalizedArticle | None = None
    concept_id: int | None = None
    summary: str = ""
    score: float = Field(default=0, ge=0, le=100)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    duplicate_probability: float = Field(default=0, ge=0, le=1)
    related_articles: list[NormalizedArticle] = Field(default_factory=list)


class FactClaim(BaseModel):
    text: str
    source_urls: list[str]
    supported: bool
    confidence: float = Field(ge=0, le=1)
    uncertainty: str | None = None


class VerifiedTopic(BaseModel):
    topic: CandidateTopic
    claims: list[FactClaim]
    confidence_score: float = Field(ge=0, le=1)
    source_urls: list[str]
    source_titles: list[str]
    source_publication_dates: list[str]
    rejected: bool = False
    rejection_reason: str | None = None


class GeneratedContent(BaseModel):
    title: str
    summary: str
    content: str
    provider: str
    model: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityResult(BaseModel):
    score: int = Field(ge=0, le=100)
    passed: bool
    checks: dict[str, bool]
    issues: list[str] = Field(default_factory=list)


class PublishResult(BaseModel):
    platform: str
    success: bool
    external_id: str | None = None
    status_code: int | None = None
    response_metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
