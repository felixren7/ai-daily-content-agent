"""Text cleaning and deterministic identifiers for untrusted fetched content."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_SPACE_RE = re.compile(r"\s+")
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"<\s*(system|assistant|tool)\s*>", re.IGNORECASE),
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
