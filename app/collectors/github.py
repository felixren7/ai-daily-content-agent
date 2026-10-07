"""GitHub Search API collector for fast-growing AI repositories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.collectors.base import Collector, CollectorResult
from app.schemas import NormalizedArticle
from app.utils.text import canonicalize_url, contains_prompt_injection, sanitize_untrusted_html


class GitHubCollector(Collector):
    name = "GitHub AI Projects"
    endpoint = "https://api.github.com/search/repositories"

    def __init__(self, max_items: int = 15, token: str | None = None) -> None:
        self.max_items = min(max_items, 100)
        self.token = token

    async def fetch(self, client: httpx.AsyncClient) -> CollectorResult:
        result = CollectorResult(source=self.name)
        since = (datetime.now(UTC) - timedelta(days=14)).date().isoformat()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = await client.get(
                self.endpoint,
                params={
                    "q": f"topic:artificial-intelligence created:>={since}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": self.max_items,
                },
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            result.errors.append(f"{type(exc).__name__}: {exc}")
            return result
        for item in payload.get("items", []):
            link = item.get("html_url")
            if not link:
                continue
            description = sanitize_untrusted_html(item.get("description") or "")
            created_at = item.get("created_at") or datetime.now(UTC).isoformat()
            result.articles.append(
                NormalizedArticle(
                    source_name=self.name,
                    source_url="https://github.com/trending",
                    source_quality=0.78,
                    external_id=str(item.get("id") or link),
                    title=sanitize_untrusted_html(item.get("full_name", ""), 1024),
                    url=link,
                    canonical_url=canonicalize_url(link),
                    summary=description,
                    content=description,
                    author=item.get("owner", {}).get("login"),
                    published_at=created_at,
                    metadata={
                        "collector": "github",
                        "prompt_injection_flagged": contains_prompt_injection(
                            f"{item.get('full_name', '')}\n{description}"
                        ),
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "language": item.get("language"),
                        "pushed_at": item.get("pushed_at"),
                    },
                )
            )
        return result
