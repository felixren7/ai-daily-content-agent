"""Content source collectors."""

from app.collectors.arxiv import ArxivCollector
from app.collectors.base import Collector, CollectorResult
from app.collectors.github import GitHubCollector
from app.collectors.registry import CollectorRegistry
from app.collectors.rss import DEFAULT_RSS_SOURCES, RSSCollector, RSSSource

__all__ = [
    "ArxivCollector",
    "Collector",
    "CollectorRegistry",
    "CollectorResult",
    "DEFAULT_RSS_SOURCES",
    "GitHubCollector",
    "RSSCollector",
    "RSSSource",
]
