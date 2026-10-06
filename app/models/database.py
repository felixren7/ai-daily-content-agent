"""Relational models for collected content and publication history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Source(TimestampMixin, Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    url: Mapped[str] = mapped_column(String(2048))
    kind: Mapped[str] = mapped_column(String(40), default="rss")
    credibility: Mapped[float] = mapped_column(Float, default=0.8)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    articles: Mapped[list[Article]] = relationship(back_populates="source")


class Article(TimestampMixin, Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_source_external", "source_id", "external_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(1024))
    url: Mapped[str] = mapped_column(String(2048), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    raw_content: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    canonical_url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    embedding_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    source: Mapped[Source] = relationship(back_populates="articles")
    topics: Mapped[list[Topic]] = relationship(back_populates="article")


class Topic(TimestampMixin, Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(1024))
    score: Mapped[float] = mapped_column(Float, default=0, index=True)
    score_breakdown: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    duplicate_probability: Mapped[float] = mapped_column(Float, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="candidate", index=True)

    article: Mapped[Article | None] = relationship(back_populates="topics")
    generated_posts: Mapped[list[GeneratedPost]] = relationship(back_populates="topic")


class Concept(TimestampMixin, Base):
    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(255), unique=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(100), default="general")
    importance: Mapped[float] = mapped_column(Float, default=0.7)
    novelty: Mapped[float] = mapped_column(Float, default=0.7)
    times_published: Mapped[int] = mapped_column(Integer, default=0)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    generated_posts: Mapped[list[GeneratedPost]] = relationship(back_populates="concept")


class GeneratedPost(TimestampMixin, Base):
    __tablename__ = "generated_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    concept_id: Mapped[int | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(30), index=True)
    style: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(1024))
    summary: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_titles: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_publication_dates: Mapped[list[str]] = mapped_column(JSON, default=list)
    extracted_facts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence_score: Mapped[float] = mapped_column(Float, default=0)
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    quality_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    llm_provider: Mapped[str] = mapped_column(String(100))
    llm_model: Mapped[str] = mapped_column(String(255))
    llm_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    topic: Mapped[Topic | None] = relationship(back_populates="generated_posts")
    concept: Mapped[Concept | None] = relationship(back_populates="generated_posts")
    publications: Mapped[list[PublicationHistory]] = relationship(back_populates="post")
    scheduled_publications: Mapped[list[ScheduledPublication]] = relationship(
        back_populates="post"
    )


class PublicationHistory(TimestampMixin, Base):
    __tablename__ = "publication_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("generated_posts.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    external_id: Mapped[str | None] = mapped_column(String(512))
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    post: Mapped[GeneratedPost] = relationship(back_populates="publications")


class ScheduledPublication(TimestampMixin, Base):
    __tablename__ = "scheduled_publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("generated_posts.id", ondelete="CASCADE"), index=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    language: Mapped[str] = mapped_column(String(20), default="original")
    status: Mapped[str] = mapped_column(String(40), default="scheduled", index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    post: Mapped[GeneratedPost] = relationship(back_populates="scheduled_publications")


class RunHistory(TimestampMixin, Base):
    __tablename__ = "run_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    mode: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(40), index=True, default="running")
    current_step: Mapped[str] = mapped_column(String(40), default="START")
    counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    error_logs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
