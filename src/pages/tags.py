"""Tags on pages (H9c): normalisation and limits.

A tag is Unicode NFC text with its whitespace trimmed and every inner run of
whitespace collapsed to one space, 1-:data:`MAX_TAG_LENGTH` characters, with
no control or format characters (Unicode category ``C*``: no NUL, no
right-to-left override). A page has at most :data:`MAX_TAGS`. Duplicates
compare case-insensitively (``casefold``); the first spelling, in the order
given, is kept.

Requests are **strict** (a ``ValueError``, so FastAPI's 422). Stored values
are cleaned **leniently**: ``Page`` is an extensible document, so a client
could have stored any ``tags`` extension before H9, and a page must never
fail to load (and drop out of the library) because of it.
"""

from __future__ import annotations

import unicodedata
from typing import Any

MAX_TAGS = 16
MAX_TAG_LENGTH = 32


def _normalise(raw: str) -> str:
    return unicodedata.normalize("NFC", " ".join(raw.split()))


def _problem(tag: str) -> str | None:
    if not tag:
        return "a tag cannot be empty"
    if len(tag) > MAX_TAG_LENGTH:
        return f"a tag may be at most {MAX_TAG_LENGTH} characters"
    if any(unicodedata.category(ch).startswith("C") for ch in tag):
        return "a tag cannot contain control or format characters"
    return None


def clean_tags(value: Any, *, strict: bool) -> list[str]:
    """*value* as a page's tags. Strict raises ``ValueError``; lenient drops what it cannot keep."""
    if value is None:
        return []
    if not isinstance(value, list):
        if strict:
            raise ValueError("tags must be a list of strings")
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            if strict:
                raise ValueError("every tag must be a string")
            continue
        tag = _normalise(raw)
        problem = _problem(tag)
        if problem:
            if strict:
                raise ValueError(f"{problem}: {raw!r}")
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    if len(tags) > MAX_TAGS:
        if strict:
            raise ValueError(f"a page may have at most {MAX_TAGS} tags")
        tags = tags[:MAX_TAGS]
    return tags


def has_tag(tags: list[str], wanted: str) -> bool:
    key = _normalise(wanted).casefold()
    return any(tag.casefold() == key for tag in tags)


def tag_counts(pages) -> list[dict]:
    """``[{tag, count}]`` over *pages*, case-insensitively, first spelling kept, sorted."""
    spelling: dict[str, str] = {}
    counts: dict[str, int] = {}
    for page in pages:
        for tag in page.tags:
            key = tag.casefold()
            spelling.setdefault(key, tag)
            counts[key] = counts.get(key, 0) + 1
    return [{"tag": spelling[key], "count": counts[key]} for key in sorted(counts)]
