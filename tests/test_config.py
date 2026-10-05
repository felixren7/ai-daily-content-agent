from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_default_settings_are_safe_for_local_execution() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "template"
    assert settings.dry_run is True
    assert settings.auto_publish is False
    assert sum(settings.scoring_weights.values()) == pytest.approx(1.0)


def test_deepseek_provider_requires_secret() -> None:
    with pytest.raises(ValidationError, match="DEEPSEEK_API_KEY"):
        Settings(_env_file=None, llm_provider="deepseek", deepseek_api_key=None)


def test_post_time_and_timezone_are_validated() -> None:
    settings = Settings(_env_file=None, post_time="9:05", timezone="Asia/Singapore")
    assert settings.post_time == "09:05"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, post_time="25:00")
