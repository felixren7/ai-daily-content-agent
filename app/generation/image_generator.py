"""Optional image generation through a separately configured compatible endpoint."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field


class ImageGenerationResult(BaseModel):
    urls: list[str] = Field(default_factory=list)
    provider_metadata: dict[str, object] = Field(default_factory=dict)


class CompatibleImageGenerator:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        size: str = "1024x1024",
        timeout: float = 90,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.size = size
        self.timeout = timeout

    async def generate(self, title: str, summary: str) -> ImageGenerationResult:
        prompt = (
            "Create a clean editorial technology illustration supporting this factual AI post. "
            "Do not include logos, fabricated UI screenshots, performance numbers, or quoted text. "
            f"Topic: {title}. Context: {summary[:800]}"
        )
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.post(
                f"{self.base_url}/images/generations",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "prompt": prompt, "size": self.size, "n": 1},
            )
            response.raise_for_status()
            payload = response.json()
        urls = [item["url"] for item in payload.get("data", []) if item.get("url")]
        return ImageGenerationResult(
            urls=urls,
            provider_metadata={"model": self.model, "created": payload.get("created")},
        )
