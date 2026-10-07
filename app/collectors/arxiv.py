"""arXiv API collector for recent AI research papers."""

from __future__ import annotations

import feedparser
import httpx

from app.collectors.base import Collector, CollectorResult
from app.collectors.rss import _entry_datetime
from app.schemas import NormalizedArticle
from app.utils.text import canonicalize_url, contains_prompt_injection, sanitize_untrusted_html


class ArxivCollector(Collector):
    name = "arXiv AI"
    endpoint = "https://export.arxiv.org/api/query"

    def __init__(self, max_items: int = 25) -> None:
        self.max_items = max_items

    async def fetch(self, client: httpx.AsyncClient) -> CollectorResult:
        result = CollectorResult(source=self.name)
        params = {
            "search_query": "cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.CV OR cat:cs.RO",
            "start": 0,
            "max_results": self.max_items,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        try:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            result.errors.append(f"{type(exc).__name__}: {exc}")
            return result
        parsed = feedparser.parse(response.content)
        for entry in parsed.entries[: self.max_items]:
            link = entry.get("link") or entry.get("id")
            if not link:
                continue
            title = sanitize_untrusted_html(entry.get("title", ""), 1024)
            summary = sanitize_untrusted_html(entry.get("summary", ""))
            authors = [item.get("name", "") for item in entry.get("authors", [])]
            result.articles.append(
                NormalizedArticle(
                    source_name=self.name,
                    source_url="https://arxiv.org/",
                    source_quality=0.96,
                    external_id=str(entry.get("id") or link),
                    title=title,
                    url=link,
                    canonical_url=canonicalize_url(link),
                    summary=summary,
                    content=summary,
                    author=", ".join(authors[:5]) or None,
                    published_at=_entry_datetime(entry),
                    metadata={
                        "collector": "arxiv",
                        "categories": entry.get("tags", []),
                        "prompt_injection_flagged": contains_prompt_injection(
                            f"{title}\n{summary}"
                        ),
                    },
                )
            )
        return result
