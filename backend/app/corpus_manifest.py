"""The corpus provenance record (data/manifest.json), read from the request path.

Written by backend/corpus when it fetches the sources, and never read by
ingestion. It is the only place a document's human-readable name survives:
ingestion derives its own title from the document's content, which for a legal
corpus yields things like "2024/1689" or the doc_id itself — fine as an internal
label, useless under a citation.

Best-effort throughout. A corpus assembled without the fetcher has no manifest,
and everything here degrades to the caller's fallback rather than failing.
"""

import functools
import json
from typing import Any

from app.config import settings


@functools.lru_cache(maxsize=1)
def _entries() -> list[dict[str, Any]]:
    if not settings.manifest_path.is_file():
        return []
    return json.loads(settings.manifest_path.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def titles() -> dict[str, str]:
    """doc_id -> the name a reader should see under a citation."""
    return {entry["id"]: entry["title"] for entry in _entries() if entry.get("title")}


@functools.lru_cache(maxsize=1)
def source_urls() -> dict[str, str]:
    """doc_id -> where the document came from."""
    return {entry["id"]: entry["source_url"] for entry in _entries() if entry.get("source_url")}


def reset() -> None:
    """Drop every cached view together. The manifest does not change while the
    API runs, so this exists for tests — and clearing only one of two caches
    would leave a stale view behind."""
    for cached in (_entries, titles, source_urls):
        cached.cache_clear()
