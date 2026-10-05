from __future__ import annotations

import httpx

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
