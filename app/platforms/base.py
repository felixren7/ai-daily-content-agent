"""Common social platform contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

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


def _tokenize(value: str, limit: int) -> Iterator[tuple[str, str]]:
    """Yield ``(separator, token)`` pairs, hard-splitting tokens above ``limit``.

    A token is a whitespace-delimited word. Chinese paragraphs contain no spaces
    and long URLs contain none either, so a single token can exceed the limit.
    Such a token is cut into limit-sized pieces instead of being truncated.
    Tokens that open a paragraph carry a newline separator; all others a space.
    """

    after_paragraph = False
    for line in value.split("\n"):
        line = line.strip()
        if not line:
            continue
        for position, word in enumerate(line.split()):
            separator = "\n" if position == 0 and after_paragraph else " "
            while len(word) > limit:
                yield separator, word[:limit]
                word = word[limit:]
                separator = " "
            yield separator, word
        after_paragraph = True


def split_text(value: str, limit: int) -> list[str]:
    """Split text into chunks of at most ``limit`` characters.

    Splitting prefers paragraph breaks, then word breaks, and cuts inside a token
    only when that token cannot fit on its own. Text content is never discarded;
    blank lines collapse into the single newline that separates paragraphs.
    """

    if limit <= 0:
        raise ValueError("Split limit must be positive")
    if len(value) <= limit:
        return [value] if value else []
    chunks: list[str] = []
    current = ""
    for separator, token in _tokenize(value, limit):
        if not current:
            current = token
        elif len(current) + len(separator) + len(token) <= limit:
            current += separator + token
        else:
            chunks.append(current)
            current = token
    if current:
        chunks.append(current)
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
