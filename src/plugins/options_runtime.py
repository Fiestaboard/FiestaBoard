"""Runtime for the plugin remote-options endpoint (Phase 2 §2, slice 4).

Concurrency guard, response caches, refresh throttle and payload ceilings for
``POST /plugins/{plugin_id}/options/{options_id}``. All of it grew up inside
``src/api_server.py``, which meant the extracted plugins router could only
reach it with a thirteen-name call-time ``from src.api_server import ...``
inside the handler — the seam the 2026-09 audit counted going up 4.2x across
Phase 1, and the reason serving one options lookup dragged the whole 10k-line
app module back into the process.

None of it touches the FastAPI app object, so it lives here instead
(recipe addendum 7: give a homeless collaborator a real module rather than
threading it through as a parameter). ``src.api_server`` re-imports every
name, so anything patching ``src.api_server.<name>`` still binds; the router
imports from here and is patched at ``src.plugins.options_runtime.<name>``.

The two module-level caches are process-global by design — an options catalog
is the same for every request — which is also why tests that care about cache
state patch ``_PLUGIN_OPTIONS_CACHE`` / ``_plugin_options_last_refresh``
rather than hoping for a cold start.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from typing import Any

from .errors import PluginOptionsThrottled

logger = logging.getLogger(__name__)


# ── Plugin remote options ────────────────────────────────────────────────────

# Hard ceiling on how many options core will hand to the browser, whatever the
# plugin returns. A picker that renders 50k rows wedges the settings dialog.
PLUGIN_OPTIONS_MAX_RETURNED = 1000
PLUGIN_OPTIONS_DEFAULT_CACHE_SECONDS = 300

# Display-string ceilings, enforced by core rather than trusted to the plugin.
# Different fields get different room because the picker gives them different
# room. Over-long strings are trimmed, never a reason to drop the choice.
PLUGIN_OPTIONS_MAX_LABEL_CHARS = 200
PLUGIN_OPTIONS_MAX_DESCRIPTION_CHARS = 200
PLUGIN_OPTIONS_MAX_PREVIEW_CHARS = 120
PLUGIN_OPTIONS_MAX_GROUP_CHARS = 80

# A continuation token is opaque to core, but it still has to fit back into a
# request, and it is one more thing a plugin can make arbitrarily large.
PLUGIN_OPTIONS_MAX_CURSOR_CHARS = 512

PLUGIN_OPTIONS_MAX_PAYLOAD_BYTES = 512 * 1024

# Wall-clock budget for one options lookup. Longer than a plugin's own HTTP
# timeout should be, short enough that a stuck picker gives up while the
# settings dialog is still open.
PLUGIN_OPTIONS_TIMEOUT_SECONDS = 20.0

# How many options lookups may occupy worker threads at once. See
# _bounded_options_call for why this is not just politeness.
PLUGIN_OPTIONS_MAX_CONCURRENCY = 4
_PLUGIN_OPTIONS_SEMAPHORE = asyncio.Semaphore(PLUGIN_OPTIONS_MAX_CONCURRENCY)


async def _bounded_options_call(work: Any, timeout: float) -> Any:
    """Run blocking *work* on a worker thread with a hard wall-clock deadline.

    ``asyncio.wait_for`` cancels the *await*, never the thread. A plugin that
    hangs on a socket keeps its worker forever no matter what we do here, so
    the semaphore is released from the task's done-callback — when the thread
    genuinely finishes — rather than when we stop waiting for it.

    That ordering is the whole point. Releasing on timeout would let four hung
    lookups free their slots, the next four start fresh threads, and so on
    until the default executor is exhausted and *every* other
    ``asyncio.to_thread`` caller in the process starves behind a plugin nobody
    is even waiting on. Holding the slot until the thread returns caps the
    damage at ``PLUGIN_OPTIONS_MAX_CONCURRENCY`` threads.
    """
    await _PLUGIN_OPTIONS_SEMAPHORE.acquire()
    task = asyncio.ensure_future(asyncio.to_thread(work))

    def _release(finished: Any) -> None:
        _PLUGIN_OPTIONS_SEMAPHORE.release()
        if not finished.cancelled():
            # Retrieve any exception so a lookup that fails after we gave up
            # does not surface as "exception was never retrieved".
            finished.exception()

    task.add_done_callback(_release)
    # shield() so the timeout abandons the wait without cancelling the task —
    # cancelling it would drop the done-callback's release on the floor.
    return await asyncio.wait_for(asyncio.shield(task), timeout)


# Answers are cached per (plugin instance, provider, effective config, query)
# so that typing in a search box does not hammer an upstream API. Bounded so a
# long-lived process cannot accumulate one entry per keystroke forever.
PLUGIN_OPTIONS_CACHE_MAX_ENTRIES = 512
_PLUGIN_OPTIONS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_plugin_options_cache_lock = threading.Lock()


def _config_fingerprint(config: dict[str, Any]) -> str:
    """Return a stable digest of an effective plugin config.

    Two installs of the same plugin with different credentials must never read
    each other's cached options, and the digest keeps the secrets themselves
    out of the cache key. ``default=str`` because a config may legitimately
    hold values JSON does not know (e.g. a datetime from a draft form).
    """
    blob = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _plugin_options_cache_key(
    plugin_id: str,
    options_id: str,
    config_digest: str,
    body: Any,  # PluginOptionsRequestBody (moved to src/plugins/routes.py); duck-typed here
    limit: int,
) -> str:
    """Build the cache key for one options question.

    ``plugin_id`` is the *full* key, instance label included: ``weather:home``
    and ``weather:cabin`` are different installs with different configs and
    must never share an entry.
    """
    blob = json.dumps(
        {
            "plugin_id": plugin_id,
            "options_id": options_id,
            "config": config_digest,
            "parent": body.parent,
            "query": body.query,
            "limit": limit,
            "cursor": body.cursor,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _plugin_options_cache_get(key: str) -> tuple[float, dict[str, Any]] | None:
    """Return the ``(stored_at, payload)`` entry for *key*, fresh or not."""
    with _plugin_options_cache_lock:
        return _PLUGIN_OPTIONS_CACHE.get(key)


def _plugin_options_cache_put(key: str, payload: dict[str, Any]) -> None:
    """Store *payload* under *key*, evicting the oldest entry when full."""
    with _plugin_options_cache_lock:
        if key not in _PLUGIN_OPTIONS_CACHE and len(_PLUGIN_OPTIONS_CACHE) >= PLUGIN_OPTIONS_CACHE_MAX_ENTRIES:
            oldest = min(_PLUGIN_OPTIONS_CACHE, key=lambda k: _PLUGIN_OPTIONS_CACHE[k][0])
            _PLUGIN_OPTIONS_CACHE.pop(oldest, None)
        _PLUGIN_OPTIONS_CACHE[key] = (time.monotonic(), payload)


def _stale_options_payload(cache_key: str, reason: str) -> dict[str, Any] | None:
    """Return the last good answer for *cache_key*, flagged stale, or ``None``.

    Expiry is deliberately ignored here. Once a lookup has failed, an old list
    plus a visible "this may be out of date" is strictly better for the user
    than an empty picker — they are usually re-opening a dialog to change one
    unrelated field.
    """
    entry = _plugin_options_cache_get(cache_key)
    if entry is None:
        return None
    return {**entry[1], "cached": True, "stale": True, "error": reason}


# A cache-bypassing refresh is the one thing a user can trigger by hand that
# reaches straight through to somebody else's API. One per second per question
# is plenty for a Retry button and stops a stuck client from becoming a DoS.
PLUGIN_OPTIONS_REFRESH_MIN_INTERVAL_SECONDS = 1.0
_plugin_options_last_refresh: dict[str, float] = {}


def _plugin_options_refresh_throttle(cache_key: str) -> None:
    """Reject a forced refresh that lands too soon after the previous one.

    Keyed per question rather than globally so a slow provider cannot lock out
    refreshes for every other field in the dialog.
    """
    now = time.monotonic()
    with _plugin_options_cache_lock:
        previous = _plugin_options_last_refresh.get(cache_key, 0.0)
        if previous and (now - previous) < PLUGIN_OPTIONS_REFRESH_MIN_INTERVAL_SECONDS:
            raise PluginOptionsThrottled("Options refresh is rate-limited. Please wait a moment and try again.")
        _plugin_options_last_refresh[cache_key] = now
        # Bounded alongside the cache it shadows.
        if len(_plugin_options_last_refresh) > PLUGIN_OPTIONS_CACHE_MAX_ENTRIES:
            oldest = min(_plugin_options_last_refresh, key=_plugin_options_last_refresh.get)  # type: ignore[arg-type]
            _plugin_options_last_refresh.pop(oldest, None)


def _declared_options_ids(manifest: Any) -> set[str]:
    """Return the ``options_id``s this plugin's own manifest declares."""
    from .manifest import collect_options_ids

    if manifest is None:
        return set()
    return collect_options_ids(getattr(manifest, "settings_schema", None) or {})


def _options_cache_seconds(manifest: Any, options_id: str) -> int:
    """Return the cache TTL this provider declares, or the platform default."""
    from .manifest import options_cache_seconds

    declared = options_cache_seconds(getattr(manifest, "settings_schema", None) or {}, options_id)
    return PLUGIN_OPTIONS_DEFAULT_CACHE_SECONDS if declared is None else declared


def _truncate(text: Any, ceiling: int) -> str | None:
    """Clip a plugin-supplied display string to *ceiling* characters."""
    if text is None:
        return None
    return (text if isinstance(text, str) else str(text))[:ceiling]


def _serialise_option(option: Any, plugin_id: str, options_id: str) -> dict[str, Any] | None:
    """Render one plugin-supplied option, or ``None`` if it must be dropped.

    Truncation rather than rejection for the display strings: a 10KB label
    breaks the layout, but discarding the option would lose a choice the user
    needs. ``value`` is the exception — it is written verbatim into
    config.json, so a non-scalar there becomes an un-comparable blob that only
    fails much later, somewhere unrelated.
    """
    value = getattr(option, "value", None)
    if not isinstance(value, str | int | float | bool):
        logger.warning(
            "Plugin '%s' options provider '%s' returned an option with a non-scalar value (%s); dropping it",
            plugin_id,
            options_id,
            type(value).__name__,
        )
        return None

    return {
        "value": value,
        "label": _truncate(getattr(option, "label", None), PLUGIN_OPTIONS_MAX_LABEL_CHARS),
        "description": _truncate(getattr(option, "description", None), PLUGIN_OPTIONS_MAX_DESCRIPTION_CHARS),
        "group": _truncate(getattr(option, "group", None), PLUGIN_OPTIONS_MAX_GROUP_CHARS),
        "preview": _truncate(getattr(option, "preview", None), PLUGIN_OPTIONS_MAX_PREVIEW_CHARS),
        "disabled": bool(getattr(option, "disabled", False)),
        "meta": getattr(option, "meta", None),
    }


def _serialise_options(options: Any, limit: int, plugin_id: str, options_id: str) -> tuple[list[dict[str, Any]], bool]:
    """Return ``(sanitised_options, truncated)`` for one provider's answer."""
    kept: list[dict[str, Any]] = []
    truncated = False
    for option in options or []:
        if len(kept) >= limit:
            truncated = True
            break
        rendered = _serialise_option(option, plugin_id, options_id)
        if rendered is not None:
            kept.append(rendered)
    return kept, truncated


def _fit_options_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Trim *payload* in place until it fits the response byte budget.

    A count ceiling is not a size ceiling: 1000 options each carrying a full
    label, description, preview and group is most of a megabyte, and the
    typical FiestaBoard talks to a Raspberry Pi over a home LAN.

    Measured with ``json.dumps`` defaults, which are looser than the compact
    separators FastAPI actually serialises with — so the real response is
    always a little under whatever this accepts.
    """
    encoded = len(json.dumps(payload, default=str).encode("utf-8"))
    while encoded > PLUGIN_OPTIONS_MAX_PAYLOAD_BYTES and payload["options"]:
        # Drop proportionally to the overshoot so this converges in a couple
        # of passes instead of one option at a time.
        per_option = max(1, encoded // len(payload["options"]))
        drop = max(1, min(len(payload["options"]), (encoded - PLUGIN_OPTIONS_MAX_PAYLOAD_BYTES) // per_option + 1))
        del payload["options"][-drop:]
        payload["has_more"] = True
        encoded = len(json.dumps(payload, default=str).encode("utf-8"))
    return payload
