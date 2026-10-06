"""Environment-driven application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI Daily Content Agent"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/content_agent.db"
    run_lock_path: Path = Path("./data/pipeline.lock")

    timezone: str = "Asia/Singapore"
    post_time: str = "09:00"
    scheduler_enabled: bool = True
    content_mode: Literal["news", "concept", "mixed"] = "mixed"
    mixed_mode_strategy: Literal["alternate", "importance"] = "importance"
    auto_publish: bool = False
    dry_run: bool = True
    dashboard_admin_token: SecretStr | None = None

    request_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    max_articles_per_source: int = Field(default=25, ge=1, le=200)
    article_max_age_hours: int = Field(default=72, ge=1, le=720)
    user_agent: str = "AI-Daily-Content-Agent/0.1 (+open-source; respectful-fetcher)"
    extra_rss_feeds: str = ""
    github_token: SecretStr | None = None

    similarity_threshold: float = Field(default=0.82, ge=0, le=1)
    history_similarity_threshold: float = Field(default=0.78, ge=0, le=1)
    min_verification_confidence: float = Field(default=0.72, ge=0, le=1)
    min_quality_score: int = Field(default=85, ge=0, le=100)
    max_post_length: int = Field(default=2800, ge=280, le=10000)

    score_recency_weight: float = Field(default=0.25, ge=0)
    score_source_quality_weight: float = Field(default=0.20, ge=0)
    score_importance_weight: float = Field(default=0.20, ge=0)
    score_novelty_weight: float = Field(default=0.15, ge=0)
    score_technical_relevance_weight: float = Field(default=0.10, ge=0)
    score_social_interest_weight: float = Field(default=0.10, ge=0)

    llm_provider: Literal["template", "deepseek", "openai", "compatible"] = "template"
    llm_temperature: float = Field(default=0.3, ge=0, le=2)
    llm_max_tokens: int = Field(default=1800, ge=200, le=8000)
    content_style: Literal[
        "technical",
        "educational",
        "news_summary",
        "beginner_friendly",
        "professional",
        "viral",
    ] = "professional"

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    compatible_api_key: SecretStr | None = None
    compatible_base_url: str | None = None
    compatible_model: str | None = None

    image_generation_enabled: bool = False
    image_api_key: SecretStr | None = None
    image_base_url: str | None = None
    image_model: str | None = None
    image_size: str = "1024x1024"

    publish_platforms: str = ""
    webhook_url: SecretStr | None = None
    webhook_bearer_token: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    twitter_bearer_token: SecretStr | None = None
    linkedin_access_token: SecretStr | None = None
    linkedin_author_urn: str | None = None
    linkedin_api_version: str = "202510"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a valid Python logging level")
        return level

    @field_validator("post_time")
    @classmethod
    def validate_post_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("POST_TIME must use HH:MM format")
        hour, minute = (int(part) for part in parts)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("POST_TIME must be a valid 24-hour time")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def validate_provider_and_weights(self) -> Settings:
        weights = self.scoring_weights
        if sum(weights.values()) <= 0:
            raise ValueError("At least one topic scoring weight must be positive")
        if self.llm_provider == "deepseek" and not self.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        if self.llm_provider == "compatible":
            missing = [
                name
                for name, value in {
                    "COMPATIBLE_API_KEY": self.compatible_api_key,
                    "COMPATIBLE_BASE_URL": self.compatible_base_url,
                    "COMPATIBLE_MODEL": self.compatible_model,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(
                    "Missing required compatible provider settings: " + ", ".join(missing)
                )
        if self.image_generation_enabled:
            image_missing = [
                name
                for name, value in {
                    "IMAGE_API_KEY": self.image_api_key,
                    "IMAGE_BASE_URL": self.image_base_url,
                    "IMAGE_MODEL": self.image_model,
                }.items()
                if not value
            ]
            if image_missing:
                raise ValueError(
                    "Missing required image generation settings: " + ", ".join(image_missing)
                )
        if self.environment == "production" and not self.dashboard_admin_token:
            raise ValueError(
                "DASHBOARD_ADMIN_TOKEN is required when ENVIRONMENT=production"
            )
        return self

    @property
    def scoring_weights(self) -> dict[str, float]:
        return {
            "recency": self.score_recency_weight,
            "source_quality": self.score_source_quality_weight,
            "importance": self.score_importance_weight,
            "novelty": self.score_novelty_weight,
            "technical_relevance": self.score_technical_relevance_weight,
            "social_interest": self.score_social_interest_weight,
        }

    @property
    def enabled_platforms(self) -> list[str]:
        return [item.strip().lower() for item in self.publish_platforms.split(",") if item.strip()]

    @property
    def additional_rss_feeds(self) -> list[str]:
        return [item.strip() for item in self.extra_rss_feeds.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
