"""Build only explicitly enabled and fully configured adapters."""

from __future__ import annotations

from app.config import Settings
from app.platforms.base import PlatformAdapter
from app.platforms.linkedin import LinkedInAdapter
from app.platforms.telegram import TelegramAdapter
from app.platforms.twitter import TwitterAdapter
from app.platforms.webhook import WebhookAdapter


def _secret(value):
    return value.get_secret_value() if value else None


def build_adapters(settings: Settings) -> list[PlatformAdapter]:
    adapters: list[PlatformAdapter] = []
    for name in settings.enabled_platforms:
        if name in {"twitter", "x"}:
            token = _secret(settings.twitter_bearer_token)
            if not token:
                raise ValueError("TWITTER_BEARER_TOKEN is required for the X adapter")
            adapters.append(TwitterAdapter(token))
        elif name == "linkedin":
            token = _secret(settings.linkedin_access_token)
            if not token or not settings.linkedin_author_urn:
                raise ValueError(
                    "LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN are required for LinkedIn"
                )
            adapters.append(
                LinkedInAdapter(token, settings.linkedin_author_urn, settings.linkedin_api_version)
            )
        elif name == "telegram":
            token = _secret(settings.telegram_bot_token)
            if not token or not settings.telegram_chat_id:
                raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
            adapters.append(TelegramAdapter(token, settings.telegram_chat_id))
        elif name == "webhook":
            url = _secret(settings.webhook_url)
            if not url:
                raise ValueError("WEBHOOK_URL is required for the webhook adapter")
            adapters.append(WebhookAdapter(url, _secret(settings.webhook_bearer_token)))
        else:
            raise ValueError(f"Unknown publication platform: {name}")
    return adapters
