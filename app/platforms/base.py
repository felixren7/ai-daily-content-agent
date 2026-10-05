"""Common social platform contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel, Field

from app.schemas import PublishResult


class PlatformPost(BaseModel):
    post_id: int
    title: str
    content: str
    source_urls: list[str] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)


class FormattedPost(BaseModel):
    parts: list[str]
    metadata: dict[str, object] = Field(default_factory=dict)


def split_text(value: str, limit: int) -> list[str]:
    if len(value) <= limit:
        return [value]
    paragraphs = [part.strip() for part in value.split("\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        words = paragraph.split()
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = word[:limit]
        if current and len(current) + 1 <= limit:
            current += "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


class PlatformAdapter(ABC):
    name: str

    @abstractmethod
    def format(self, post: PlatformPost) -> FormattedPost:
        raise NotImplementedError

    @abstractmethod
    def validate(self, post: FormattedPost) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def publish(self, post: PlatformPost, client: httpx.AsyncClient) -> PublishResult:
        raise NotImplementedError
