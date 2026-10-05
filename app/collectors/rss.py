"""RSS/Atom collector for authoritative AI sources."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime

import feedparser
import httpx
from dateutil import parser as date_parser
from pydantic import BaseModel, Field, HttpUrl

from app.collectors.base import Collector, CollectorResult
from app.schemas import NormalizedArticle
from app.utils.text import canonicalize_url, contains_prompt_injection, sanitize_untrusted_html


class RSSSource(BaseModel):
    name: str
    feed_url: HttpUrl
    home_url: HttpUrl
    credibility: float = Field(ge=0, le=1)


DEFAULT_RSS_SOURCES = [
    RSSSource(
        name="OpenAI News",
        feed_url="https://openai.com/news/rss.xml",
        home_url="https://openai.com/news/",
        credibility=0.98,
    ),
    RSSSource(
        name="Google AI",
        feed_url="https://blog.google/technology/ai/rss/",
        home_url="https://blog.google/technology/ai/",
        credibility=0.95,
    ),
    RSSSource(
        name="Google DeepMind",
        feed_url="https://deepmind.google/blog/rss.xml",
        home_url="https://deepmind.google/blog/",
        credibility=0.98,
    ),
    RSSSource(
        name="Microsoft Research",
        feed_url="https://www.microsoft.com/en-us/research/feed/",
        home_url="https://www.microsoft.com/en-us/research/",
        credibility=0.94,
    ),
    RSSSource(
        name="NVIDIA AI",
        feed_url="https://blogs.nvidia.com/blog/category/deep-learning/feed/",
        home_url="https://blogs.nvidia.com/blog/category/deep-learning/",
        credibility=0.94,
    ),
    RSSSource(
        name="Hugging Face",
        feed_url="https://huggingface.co/blog/feed.xml",
        home_url="https://huggingface.co/blog",
        credibility=0.93,
    ),
    RSSSource(
        name="MIT AI News",
        feed_url="https://news.mit.edu/rss/topic/artificial-intelligence2",
        home_url="https://news.mit.edu/topic/artificial-intelligence2",
        credibility=0.93,
    ),
]


def _entry_datetime(entry: feedparser.FeedParserDict) -> datetime:
    struct_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if struct_time:
        return datetime.fromtimestamp(calendar.timegm(struct_time), tz=UTC)
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            parsed = date_parser.parse(raw)
            return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)
        except (ValueError, TypeError, OverflowError):
            pass
    return datetime.now(UTC)


class RSSCollector(Collector):
    def __init__(self, source: RSSSource, max_items: int = 25) -> None:
        self.source = source
        self.name = source.name
        self.max_items = max_items

    async def fetch(self, client: httpx.AsyncClient) -> CollectorResult:
        result = CollectorResult(source=self.name)
        try:
            response = await client.get(str(self.source.feed_url))
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            result.errors.append(f"{type(exc).__name__}: {exc}")
            return result

        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            result.errors.append(f"Feed parse error: {parsed.bozo_exception}")
            return result

        for entry in parsed.entries[: self.max_items]:
            link = entry.get("link") or entry.get("id")
            title = sanitize_untrusted_html(entry.get("title", ""), max_length=1024)
            if not link or not title:
                continue
            summary_html = entry.get("summary") or entry.get("description") or ""
            summary = sanitize_untrusted_html(summary_html)
            content_parts = entry.get("content") or []
            content_html = " ".join(part.get("value", "") for part in content_parts)
            content = sanitize_untrusted_html(content_html) or summary
            result.articles.append(
                NormalizedArticle(
                    source_name=self.source.name,
                    source_url=str(self.source.home_url),
                    source_quality=self.source.credibility,
                    external_id=str(entry.get("id") or canonicalize_url(link)),
                    title=title,
                    url=link,
                    canonical_url=canonicalize_url(link),
                    summary=summary,
                    content=content,
                    author=sanitize_untrusted_html(entry.get("author", ""), 255) or None,
                    published_at=_entry_datetime(entry),
                    metadata={
                        "collector": "rss",
                        "prompt_injection_flagged": contains_prompt_injection(
                            f"{title}\n{summary}\n{content}"
                        ),
                    },
                )
            )
        return result
