"""X API v2 adapter using OAuth 2.0 user-context bearer credentials."""

from __future__ import annotations

import httpx

from app.platforms.base import FormattedPost, PlatformAdapter, PlatformPost, split_text
from app.schemas import PublishResult


class TwitterAdapter(PlatformAdapter):
    name = "twitter"
    endpoint = "https://api.x.com/2/tweets"

    def __init__(self, bearer_token: str) -> None:
        self.bearer_token = bearer_token

    def format(self, post: PlatformPost) -> FormattedPost:
        chunks = split_text(post.content, 270)
        total = len(chunks)
        parts = [
            f"{chunk}\n\n{index}/{total}" if total > 1 else chunk
            for index, chunk in enumerate(chunks, 1)
        ]
        return FormattedPost(parts=parts)

    def validate(self, post: FormattedPost) -> list[str]:
        errors = []
        if not post.parts:
            errors.append("X post is empty")
        if any(len(part) > 280 for part in post.parts):
            errors.append("An X thread part exceeds 280 characters")
        return errors

    async def publish(self, post: PlatformPost, client: httpx.AsyncClient) -> PublishResult:
        formatted = self.format(post)
        errors = self.validate(formatted)
        if errors:
            return PublishResult(platform=self.name, success=False, error="; ".join(errors))
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        reply_to: str | None = None
        root_id: str | None = None
        try:
            for part in formatted.parts:
                body: dict[str, object] = {"text": part}
                if reply_to:
                    body["reply"] = {"in_reply_to_tweet_id": reply_to}
                response = await client.post(self.endpoint, headers=headers, json=body)
                response.raise_for_status()
                tweet_id = str(response.json()["data"]["id"])
                root_id = root_id or tweet_id
                reply_to = tweet_id
            return PublishResult(platform=self.name, success=True, external_id=root_id)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            return PublishResult(platform=self.name, success=False, error=str(exc))
