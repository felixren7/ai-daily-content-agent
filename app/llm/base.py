"""Provider-independent language model contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(ABC):
    provider_name: str
    model: str

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
    ) -> LLMResponse:
        raise NotImplementedError
