"""Point sign-in endpoints at a local mock provider (development only).

``FIESTABOARD_OAUTH_URL_OVERRIDES`` holds a JSON object mapping a URL prefix
to its replacement, for example::

    {"https://openrouter.ai": "http://localhost:9400",
     "https://plex.tv": "http://localhost:9400",
     "https://app.plex.tv": "http://localhost:9400/plex"}

Every sign-in endpoint (plugin manifests, FiestaBot AI presets, plex.tv) is
passed through :func:`override_url`, so ``scripts/mock_oauth_provider.py``
can stand in for providers whose URLs are constants. Unset (the default) it
changes nothing. It is read from the environment on every call, which only
the person running the board controls.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

URL_OVERRIDES_ENV = "FIESTABOARD_OAUTH_URL_OVERRIDES"


def _overrides() -> dict[str, str]:
    raw = os.environ.get(URL_OVERRIDES_ENV, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        logger.warning("%s is not valid JSON; ignored", URL_OVERRIDES_ENV)
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {k: v for k, v in parsed.items() if isinstance(k, str) and k and isinstance(v, str)}


def override_url(url: str) -> str:
    """*url* with the longest matching override prefix replaced, else unchanged."""
    if not url:
        return url
    overrides = _overrides()
    for prefix in sorted(overrides, key=len, reverse=True):
        if url == prefix or url.startswith((prefix.rstrip("/") + "/", prefix + "#")):
            return overrides[prefix] + url[len(prefix) :]
    return url
