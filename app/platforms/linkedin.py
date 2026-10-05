"""LinkedIn Posts API adapter."""

from __future__ import annotations

import httpx

from app.platforms.base import FormattedPost, PlatformAdapter, PlatformPost
from app.schemas import PublishResult


class LinkedInAdapter(PlatformAdapter):
    name = "linkedin"
    endpoint = "https://api.linkedin.com/rest/posts"

    def __init__(self, access_token: str, author_urn: str, api_version: str) -> None:
        self.access_token = access_token
        self.author_urn = author_urn
        self.api_version = api_version

    def format(self, post: PlatformPost) -> FormattedPost:
        return FormattedPost(parts=[post.content])

    def validate(self, post: FormattedPost) -> list[str]:
        errors = []
        if len(post.parts) != 1 or not post.parts[0].strip():
            errors.append("LinkedIn post is empty")
        if post.parts and len(post.parts[0]) > 3000:
            errors.append("LinkedIn post exceeds 3000 characters")
        if not self.author_urn.startswith("urn:li:"):
            errors.append("LinkedIn author must be a valid URN")
        return errors

    async def publish(self, post: PlatformPost, client: httpx.AsyncClient) -> PublishResult:
        formatted = self.format(post)
        errors = self.validate(formatted)
        if errors:
            return PublishResult(platform=self.name, success=False, error="; ".join(errors))
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "LinkedIn-Version": self.api_version,
            "X-Restli-Protocol-Version": "2.0.0",
        }
        body = {
            "author": self.author_urn,
            "commentary": formatted.parts[0],
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED"},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        try:
            response = await client.post(self.endpoint, headers=headers, json=body)
            response.raise_for_status()
            return PublishResult(
                platform=self.name,
                success=True,
                external_id=response.headers.get("x-restli-id"),
                status_code=response.status_code,
            )
        except httpx.HTTPError as exc:
            return PublishResult(platform=self.name, success=False, error=str(exc))
