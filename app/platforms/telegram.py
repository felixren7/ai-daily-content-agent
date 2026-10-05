"""Telegram Bot API adapter."""

from __future__ import annotations

import httpx

from app.platforms.base import FormattedPost, PlatformAdapter, PlatformPost, split_text
from app.schemas import PublishResult


class TelegramAdapter(PlatformAdapter):
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def endpoint(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def format(self, post: PlatformPost) -> FormattedPost:
        return FormattedPost(parts=split_text(post.content, 4096))

    def validate(self, post: FormattedPost) -> list[str]:
        errors = []
        if not post.parts:
            errors.append("Telegram post is empty")
        if any(len(part) > 4096 for part in post.parts):
            errors.append("Telegram message exceeds 4096 characters")
        return errors

    async def publish(self, post: PlatformPost, client: httpx.AsyncClient) -> PublishResult:
        formatted = self.format(post)
        errors = self.validate(formatted)
        if errors:
            return PublishResult(platform=self.name, success=False, error="; ".join(errors))
        message_ids: list[str] = []
        try:
            for part in formatted.parts:
                response = await client.post(
                    self.endpoint,
                    json={"chat_id": self.chat_id, "text": part, "disable_web_page_preview": False},
                )
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok"):
                    raise RuntimeError(payload.get("description", "Telegram rejected the message"))
                message_ids.append(str(payload["result"]["message_id"]))
            return PublishResult(
                platform=self.name,
                success=True,
                external_id=message_ids[0] if message_ids else None,
                response_metadata={"message_ids": message_ids},
            )
        except (httpx.HTTPError, ValueError, KeyError, RuntimeError) as exc:
            return PublishResult(platform=self.name, success=False, error=str(exc))
