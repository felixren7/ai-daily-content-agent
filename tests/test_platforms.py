from __future__ import annotations

import httpx

from app.platforms.base import PlatformPost
from app.platforms.telegram import TelegramAdapter
from app.platforms.twitter import TwitterAdapter
from app.platforms.webhook import WebhookAdapter


def post(content: str) -> PlatformPost:
    return PlatformPost(
        post_id=1, title="Test", content=content, source_urls=["https://example.com"]
    )


def test_twitter_adapter_splits_long_content() -> None:
    adapter = TwitterAdapter("secret")
    formatted = adapter.format(post("word " * 200))
    assert len(formatted.parts) > 1
    assert not adapter.validate(formatted)
    assert all(len(part) <= 280 for part in formatted.parts)


async def test_webhook_adapter_posts_expected_payload() -> None:
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(202, text="accepted")

    adapter = WebhookAdapter("https://hooks.example/publish", "token")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await adapter.publish(post("Grounded content."), client)
    assert result.success
    assert result.status_code == 202
    assert seen["id"] == 1


def test_telegram_adapter_respects_message_limit() -> None:
    adapter = TelegramAdapter("secret", "123")
    formatted = adapter.format(post("word " * 2000))
    assert not adapter.validate(formatted)
    assert all(len(part) <= 4096 for part in formatted.parts)
