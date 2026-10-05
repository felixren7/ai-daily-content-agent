"""Social publication adapters."""

from app.platforms.base import FormattedPost, PlatformAdapter, PlatformPost
from app.platforms.registry import build_adapters

__all__ = ["FormattedPost", "PlatformAdapter", "PlatformPost", "build_adapters"]
