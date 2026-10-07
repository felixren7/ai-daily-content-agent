from __future__ import annotations

import httpx
import pytest

from app.platforms.base import PlatformPost, split_text
from app.platforms.telegram import TelegramAdapter
from app.platforms.twitter import TwitterAdapter
from app.platforms.webhook import WebhookAdapter

CHINESE_PARAGRAPH = "这是一个中文段落，用来验证切分不会丢失任何字符。" * 9


def post(content: str) -> PlatformPost:
    return PlatformPost(
        post_id=1, title="Test", content=content, source_urls=["https://example.com"]
    )


def stripped(value: str) -> str:
    """Remove every whitespace character so separators do not affect comparisons."""

    return "".join(value.split())


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


def test_split_text_keeps_every_character_of_an_unspaced_paragraph() -> None:
    # Chinese text has no spaces, so the paragraph is a single oversized token.
    parts = split_text(CHINESE_PARAGRAPH, 90)
    assert len(parts) > 1
    assert all(len(part) <= 90 for part in parts)
    assert stripped("".join(parts)) == stripped(CHINESE_PARAGRAPH)


def test_split_text_keeps_every_character_across_paragraphs_and_words() -> None:
    content = f"An English paragraph with words.\n\n{CHINESE_PARAGRAPH}\n\nTail paragraph."
    parts = split_text(content, 70)
    assert all(len(part) <= 70 for part in parts)
    assert stripped("".join(parts)) == stripped(content)


def test_split_text_returns_no_chunk_for_empty_input() -> None:
    assert split_text("", 100) == []


def test_split_text_rejects_a_non_positive_limit() -> None:
    with pytest.raises(ValueError):
        split_text("content", 0)


def test_twitter_adapter_keeps_the_tail_of_a_long_chinese_post() -> None:
    content = CHINESE_PARAGRAPH + "这段结尾必须出现在推文里。"
    adapter = TwitterAdapter("secret")
    formatted = adapter.format(post(content))
    assert not adapter.validate(formatted)
    assert all(len(part) <= 280 for part in formatted.parts)
    assert "这段结尾必须出现在推文里。" in "".join(formatted.parts)
