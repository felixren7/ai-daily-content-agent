"""Generic JSON webhook publisher."""

from __future__ import annotations

import httpx

from app.platforms.base import FormattedPost, PlatformAdapter, PlatformPost
from app.schemas import PublishResult


class WebhookAdapter(PlatformAdapter):
    name = "webhook"

    def __init__(self, url: str, bearer_token: str | None = None) -> None:
        self.url = url
        self.bearer_token = bearer_token

    def format(self, post: PlatformPost) -> FormattedPost:
        return FormattedPost(parts=[post.content], metadata={"source_urls": post.source_urls})

    def validate(self, post: FormattedPost) -> list[str]:
        return [] if post.parts and post.parts[0].strip() else ["Webhook payload is empty"]

    async def publish(self, post: PlatformPost, client: httpx.AsyncClient) -> PublishResult:
        formatted = self.format(post)
        errors = self.validate(formatted)
        if errors:
            return PublishResult(platform=self.name, success=False, error="; ".join(errors))
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        body = {
            "id": post.post_id,
            "title": post.title,
            "content": formatted.parts[0],
            "source_urls": post.source_urls,
            "image_urls": post.image_urls,
        }
        try:
            response = await client.post(self.url, headers=headers, json=body)
            response.raise_for_status()
            return PublishResult(
                platform=self.name,
                success=True,
                status_code=response.status_code,
                response_metadata={"response_excerpt": response.text[:500]},
            )
        except httpx.HTTPError as exc:
            return PublishResult(platform=self.name, success=False, error=str(exc))
