"""Collector interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel, Field

from app.schemas import NormalizedArticle


class CollectorResult(BaseModel):
    source: str
    articles: list[NormalizedArticle] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class Collector(ABC):
    name: str

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> CollectorResult:
        raise NotImplementedError
