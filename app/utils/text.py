"""Text cleaning and deterministic identifiers for untrusted fetched content."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_SPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+")
_TRAILING_PUNCTUATION = ".,;:!?。，；：！？)】」'\""
# Patterns must describe an instruction aimed at a model, not the vocabulary of
# the subject matter. Ordinary AI reporting discusses system prompts, developer
# messages, and prompt engineering constantly, and a flagged article is rejected
# outright by the verifier, so matching those terms would discard real news.
_INJECTION_PATTERNS = (
    re.compile(
        r"(?:ignore|disregard)\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\s+instructions",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|repeat|print|output|disclose|leak)\s+(?:me\s+)?(?:your|the)\s+"
        r"(?:system\s+|developer\s+)?(?:prompt|instructions)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\byou\s+are\s+now\s+(?:a|an|in)\b", re.IGNORECASE),
    re.compile(r"<\s*(?:system|assistant|tool|developer)\s*>", re.IGNORECASE),
)
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


def sanitize_untrusted_html(value: str, max_length: int = 20_000) -> str:
    """Convert fetched HTML to inert plain text with bounded size.

    The result remains untrusted data. Callers must never interpolate it as an
    instruction outside clearly-delimited prompt data sections.
    """

    soup = BeautifulSoup(value or "", "html.parser")
    for node in soup(["script", "style", "iframe", "object", "form", "noscript"]):
        node.decompose()
    text = html.unescape(soup.get_text(" ", strip=True))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cc" or ch in "\n\t")
    return _SPACE_RE.sub(" ", text).strip()[:max_length]


def contains_prompt_injection(value: str) -> bool:
    return any(pattern.search(value or "") for pattern in _INJECTION_PATTERNS)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = re.sub(r"[^\w\s-]", " ", value)
    return _SPACE_RE.sub(" ", value).strip()


def stable_hash(*values: str) -> str:
    payload = "\n".join(normalize_text(value) for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cited_urls(value: str) -> list[str]:
    """Return the distinct URLs a text cites, in order of appearance.

    Trailing punctuation is excluded, so a URL followed by a period or a Chinese
    full stop still compares equal to the same URL written elsewhere. Use this to
    check that a rewritten or translated body kept the citations it started with:
    a post cites fewer URLs in its body than the pipeline collected for it.
    """

    matched = (url.rstrip(_TRAILING_PUNCTUATION) for url in _URL_RE.findall(value or ""))
    return list(dict.fromkeys(url for url in matched if url))


def canonicalize_url(url: str) -> str:
    parts = urlsplit(str(url).strip())
    scheme = parts.scheme.lower() or "https"
    hostname = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        hostname = f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    return urlunsplit((scheme, hostname, path, urlencode(sorted(query)), ""))
