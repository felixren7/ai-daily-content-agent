from __future__ import annotations

import httpx
import pytest

from app.llm.compatible_provider import DeepSeekProvider


async def test_compatible_provider_parses_response_without_real_api() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.path == "/chat/completions"
        return httpx.Response(
            200,
            json={
                "id": "req-1",
                "model": "deepseek-test",
                "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 10},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekProvider(
            "test-key", "https://api.example", "deepseek-test", client=client
        )
        result = await provider.complete("system", "user", json_mode=True)
    assert result.provider == "deepseek"
    assert result.text == '{"ok": true}'
    assert result.metadata["usage"]["total_tokens"] == 10


async def test_empty_content_reports_the_exhausted_budget() -> None:
    # A reasoning model charges its thinking against max_tokens, so it can return
    # an empty body. Callers must not be left reporting that as malformed JSON.
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "req-2",
                "model": "deepseek-test",
                "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
                "usage": {"completion_tokens": 1800},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekProvider(
            "test-key",
            "https://api.example",
            "deepseek-test",
            client=client,
            max_tokens=1800,
        )
        with pytest.raises(RuntimeError, match="returned no content.*max_tokens=1800"):
            await provider.complete("system", "user", json_mode=True)
