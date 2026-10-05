"""Concurrent collector orchestration with per-source failure isolation."""

from __future__ import annotations

import asyncio

import httpx

from app.collectors.arxiv import ArxivCollector
from app.collectors.base import Collector, CollectorResult
from app.collectors.github import GitHubCollector
from app.collectors.rss import DEFAULT_RSS_SOURCES, RSSCollector, RSSSource
from app.config import Settings


class CollectorRegistry:
    def __init__(self, collectors: list[Collector]) -> None:
        self.collectors = collectors

    @classmethod
    def from_settings(cls, settings: Settings) -> CollectorRegistry:
        rss_sources = list(DEFAULT_RSS_SOURCES)
        for index, url in enumerate(settings.additional_rss_feeds, start=1):
            rss_sources.append(
                RSSSource(
                    name=f"Custom RSS {index}",
                    feed_url=url,
                    home_url=url,
                    credibility=0.65,
                )
            )
        collectors: list[Collector] = [
            RSSCollector(source, settings.max_articles_per_source) for source in rss_sources
        ]
        collectors.append(ArxivCollector(settings.max_articles_per_source))
        github_token = settings.github_token.get_secret_value() if settings.github_token else None
        collectors.append(GitHubCollector(settings.max_articles_per_source, github_token))
        return cls(collectors)

    async def fetch_all(self, client: httpx.AsyncClient) -> list[CollectorResult]:
        tasks = [collector.fetch(client) for collector in self.collectors]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[CollectorResult] = []
        for collector, value in zip(self.collectors, gathered, strict=True):
            if isinstance(value, Exception):
                results.append(
                    CollectorResult(
                        source=collector.name,
                        errors=[f"Unexpected {type(value).__name__}: {value}"],
                    )
                )
            else:
                results.append(value)
        return results
