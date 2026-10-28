"""Optional discovery labels. They never select a renderer or grant capabilities."""

from typing import Any


def display_metadata(raw: Any) -> dict[str, Any]:
    """Ignore malformed optional metadata without hiding an otherwise usable plugin."""
    raw = raw if isinstance(raw, dict) else {}

    def label(value: Any) -> str:
        return value.strip()[:160] if isinstance(value, str) else ""

    def labels(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(text for item in value[:100] if (text := label(item))))

    return {
        "category": label(raw.get("category")),
        "manufacturer": label(raw.get("manufacturer")),
        "models": labels(raw.get("models")),
        "keywords": labels(raw.get("keywords")),
    }
