from __future__ import annotations

import httpx

from app.collectors.rss import RSSCollector, RSSSource


async def test_rss_collector_normalizes_items() -> None:
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Lab</title>
    <item><guid>x-1</guid><title>New model released</title>
    <link>https://example.com/post?utm_source=rss</link>
    <description><![CDATA[<p>Measured result.</p>]]></description>
    <pubDate>Sun, 05 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>"""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=feed)

    source = RSSSource(
        name="Lab",
        feed_url="https://example.com/rss",
        home_url="https://example.com",
        credibility=0.9,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await RSSCollector(source).fetch(client)
    assert not result.errors
    assert len(result.articles) == 1
    assert result.articles[0].canonical_url == "https://example.com/post"
    assert result.articles[0].summary == "Measured result."


async def test_rss_collector_contains_source_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    source = RSSSource(
        name="Lab",
        feed_url="https://example.com/rss",
        home_url="https://example.com",
        credibility=0.9,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await RSSCollector(source).fetch(client)
    assert result.articles == []
    assert result.errors
