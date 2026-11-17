"""Rules that apply only when the caller is a phone (``control`` scope, H21d).

The scope table (``src/auth/scopes.py``) decides which routes a phone reaches.
A few of those routes then answer a phone differently from a browser, because
a phone must never be able to read a stored secret or send one somewhere new:

* **Key re-entry.** Changing where an AI provider's key is sent (its
  ``base_url`` or ``protocol``) while the key comes back as the mask ``"***"``
  is refused with ``400 key_required``: the key has to be typed again. Masked
  header values are treated the same way.
* **Masked headers.** A phone reads every AI provider header value as ``"***"``
  (custom headers often carry credentials), and an echoed mask keeps the
  stored value as long as the endpoint is unchanged.
* **Redacted backups.** A phone's ``GET /backup/export`` has every secret-looking
  value replaced by ``"***"`` and says so (``"redacted": true``).
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .scopes import CONTROL

MASK = "***"
KEY_REQUIRED = "key_required"

#: Provider fields that decide where the stored key is sent.
_ENDPOINT_FIELDS = ("base_url", "protocol")

#: Keys whose values a phone's backup never carries. Broader than the browser's
#: SENSITIVE_FIELDS on purpose: over-masking a redacted export loses nothing.
_SECRET_KEY = re.compile(r"(key|token|secret|passw|credential|auth|cookie|session|private|signature)", re.I)


def is_phone(request: Any) -> bool:
    """True when the middleware resolved a phone (``fb_mob_``) credential for *request*.

    *request* is anything with an ASGI ``scope`` mapping (a Starlette request).
    """
    return getattr(request, "scope", {}).get("auth_scope") == CONTROL


def session_is_elevated(session_id: str | None) -> bool:
    """Whether the phone session *session_id* is stepped up right now (H21s)."""
    from .service import get_auth_service
    from .step_up import is_elevated

    return is_elevated(get_auth_service(), session_id)


def key_required_body(detail: str) -> dict[str, str]:
    """The ``400`` body that asks for a key to be typed again."""
    return {"error": KEY_REQUIRED, "code": KEY_REQUIRED, "detail": detail}


# -- AI providers ------------------------------------------------------------------


def _endpoint(provider: dict[str, Any]) -> tuple[str, ...]:
    values = []
    for field in _ENDPOINT_FIELDS:
        value = provider.get(field)
        values.append(value.strip().rstrip("/").lower() if isinstance(value, str) else repr(value))
    return tuple(values)


def _headers(provider: dict[str, Any]) -> dict[str, Any]:
    headers = provider.get("headers")
    return headers if isinstance(headers, dict) else {}


def mask_provider_headers(block: dict[str, Any]) -> dict[str, Any]:
    """*block* (a masked AI providers response) with every header value masked too."""
    block = copy.deepcopy(block)
    for provider in block.get("providers") or []:
        if isinstance(provider, dict) and isinstance(provider.get("headers"), dict):
            provider["headers"] = {name: (MASK if value else value) for name, value in provider["headers"].items()}
    return block


def prepare_provider_update(providers: list[Any], stored: list[Any]) -> str | None:
    """Apply the phone rules to an incoming ``providers`` list, in place.

    Returns the id of the first provider that needs its key typed again (the
    request must then be refused), else None. For providers whose endpoint is
    unchanged, masked header values are restored from the stored provider.
    """
    stored_by_id = {p.get("id"): p for p in stored if isinstance(p, dict) and p.get("id")}
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        before = stored_by_id.get(provider.get("id"))
        if before is None:
            # A new provider: a mask here is stored literally (the config manager
            # restores keys by id only), so nothing stored can leak.
            continue
        old_headers = _headers(before)
        masked_headers = [name for name, value in _headers(provider).items() if value == MASK]
        if _endpoint(provider) != _endpoint(before):
            key = provider.get("api_key")
            if (before.get("api_key") and (not key or key == MASK)) or masked_headers:
                return str(provider.get("id"))
            continue
        if masked_headers:
            provider["headers"] = {
                name: (old_headers.get(name, value) if value == MASK else value)
                for name, value in _headers(provider).items()
            }
    return None


def draft_needs_key(draft: dict[str, Any]) -> bool:
    """A phone's unsaved provider draft may be tested only with its own key typed in.

    Any mask (key or header) would be resolved to a stored secret and sent to
    the draft's endpoint, so it is refused.
    """
    if draft.get("api_key") in (None, "", MASK):
        return True
    return any(value == MASK for value in _headers(draft).values())


# -- Backups ------------------------------------------------------------------------


def redact(value: Any, key: str = "") -> Any:
    """*value* with every secret-looking entry replaced by the mask.

    A key that looks secret masks whatever it holds (a nested object included);
    ``headers`` objects are masked value by value.
    """
    if key and _SECRET_KEY.search(key) and value not in (None, "", [], {}):
        if isinstance(value, bool | int | float):
            return value
        return MASK
    if isinstance(value, dict):
        if key == "headers":
            return {name: (MASK if item else item) for name, item in value.items()}
        return {name: redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [redact(item, key if key == "headers" else "") for item in value]
    return value


def redact_backup(backup: dict[str, Any]) -> dict[str, Any]:
    """A phone's copy of a backup document: secrets masked, marked ``redacted``."""
    document = dict(backup)
    document["data"] = redact(backup.get("data") or {})
    document["redacted"] = True
    document["redacted_note"] = (
        "Exported from a phone: passwords, keys and tokens are replaced by ***. "
        "Restoring this file keeps *** in their place, so enter them again afterwards."
    )
    return document


