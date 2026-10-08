"""OpenAI-compatible chat-completions provider implemented with HTTP."""

from __future__ import annotations

from typing import Any

import httpx

from app.llm.base import LLMProvider, LLMResponse


class CompatibleAPIProvider(LLMProvider):
    provider_name = "compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1800,
        timeout: float = 60,
        client: httpx.AsyncClient | None = None,
        provider_name: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.client = client
        if provider_name:
            self.provider_name = provider_name

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
        try:
            response = await client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=payload
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            raise RuntimeError(
                f"{self.provider_name} API returned HTTP {exc.response.status_code}: {body}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"{self.provider_name} API request failed: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"{self.provider_name} returned an invalid response shape") from exc
        if not (text or "").strip():
            # A reasoning model charges its thinking against max_tokens, so it can
            # exhaust the budget before emitting any answer. Without this the caller
            # only sees an empty body and reports it as malformed JSON.
            raise RuntimeError(
                f"{self.provider_name} returned no content "
                f"(finish_reason={choice.get('finish_reason')}) within "
                f"max_tokens={self.max_tokens}; raise the token budget for this call"
            )
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=data.get("model", self.model),
            metadata={
                "request_id": data.get("id"),
                "finish_reason": choice.get("finish_reason"),
                "usage": usage,
            },
        )


class DeepSeekProvider(CompatibleAPIProvider):
    provider_name = "deepseek"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["provider_name"] = "deepseek"
        super().__init__(*args, **kwargs)


class OpenAIProvider(CompatibleAPIProvider):
    provider_name = "openai"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["provider_name"] = "openai"
        super().__init__(*args, **kwargs)
