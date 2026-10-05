"""Provider construction from validated settings."""

from __future__ import annotations

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.compatible_provider import CompatibleAPIProvider, DeepSeekProvider, OpenAIProvider
from app.llm.template_provider import TemplateProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    common = {
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "timeout": max(30, settings.request_timeout_seconds),
    }
    if settings.llm_provider == "template":
        return TemplateProvider()
    if settings.llm_provider == "deepseek":
        assert settings.deepseek_api_key is not None
        return DeepSeekProvider(
            settings.deepseek_api_key.get_secret_value(),
            settings.deepseek_base_url,
            settings.deepseek_model,
            **common,
        )
    if settings.llm_provider == "openai":
        assert settings.openai_api_key is not None
        return OpenAIProvider(
            settings.openai_api_key.get_secret_value(),
            settings.openai_base_url,
            settings.openai_model,
            **common,
        )
    assert settings.compatible_api_key is not None
    assert settings.compatible_base_url is not None
    assert settings.compatible_model is not None
    return CompatibleAPIProvider(
        settings.compatible_api_key.get_secret_value(),
        settings.compatible_base_url,
        settings.compatible_model,
        **common,
    )
