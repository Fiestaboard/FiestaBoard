"""Rules that apply only when the caller is a phone (``control`` scope, H21d).

The scope table (``src/auth/scopes.py``) decides which routes a phone reaches.
A few of those routes then answer a phone differently from a browser, because
a phone must never be able to read a stored secret or send one somewhere new:

* **Key re-entry.** Changing where an AI provider's key is sent (its
  ``base_url`` or ``protocol``) while the key comes back as the mask ``"***"``
  is refused with ``400 key_required``: the key has to be typed again. Masked
  header values are treated the same way.
* **Plugins and displays.** The same rule for an installed plugin's settings
  and a display's connection: see :func:`plugin_config_needs_key` and
  ``src/auth/key_reentry.py``.
* **Masked headers.** A phone reads every AI provider header value as ``"***"``
  (custom headers often carry credentials), and an echoed mask keeps the
  stored value as long as the endpoint is unchanged.
* **Redacted backups.** A phone's ``GET /backup/export`` has every secret-looking
  value replaced by ``"***"`` and says so (``"redacted": true``).
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from .scopes import CONTROL

MASK = "***"
KEY_REQUIRED = "key_required"

#: Provider fields that decide where the stored key (or sign-in token) is sent.
_ENDPOINT_FIELDS = ("base_url", "protocol", "sign_in")

#: Key names whose values a phone's backup never carries, on top of the hub's own
#: ``SENSITIVE_FIELDS`` and each display output's schema-declared secrets.
_SECRET_KEY = re.compile(
    r"(api_?key|_key$|^key$|token|secret|passw|credential|authoriz|^auth$|auth_?(code|header|key)"
    r"|cookie|private_?key|signature$|^session(_?id|_?key)?$|^pin$)",
    re.I,
)


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
    from src.ai.protocols import DEFAULT_PROTOCOL, PROTOCOLS

    values = []
    for field in _ENDPOINT_FIELDS:
        value = provider.get(field)
        if field == "protocol" and value is not None and not isinstance(value, str):
            raise ValueError("A provider's protocol must be a string.")
        if field == "protocol" and (not value or value not in PROTOCOLS):
            # The generator treats a missing or unknown protocol as the default.
            value = DEFAULT_PROTOCOL
        if isinstance(value, str):
            values.append(value.strip().rstrip("/").lower())
        else:
            values.append(json.dumps(value, sort_keys=True, default=str))
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
    request must then be refused), else None. Raises ``ValueError`` for a
    provider whose endpoint fields are malformed (a ``400``). For providers whose endpoint is
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


# -- Installed plugins ---------------------------------------------------------------


def plugin_config_needs_key(plugin_id: str, config: Any, *, merge: bool) -> bool:
    """True when saving *config* for plugin *plugin_id* would send a stored secret to a new endpoint.

    The same rule as a display's (``src/auth/key_reentry.py``): changing the
    plugin's address, protocol or sign-in fields while its key comes back
    masked, or is left out of a merged update, needs the key typed again.
    *merge* is True for ``configure_plugin``, which merges into the stored
    config (so an omitted key is kept); the REST route replaces it. Secrets
    supplied by environment variables count as stored ones.
    """
    if not isinstance(config, dict):
        return False
    from src.config_manager import get_config_manager, unmask_sensitive_values

    from .key_reentry import moves_a_secret

    manager = get_config_manager()
    stored = manager.get_plugin_config(plugin_id, include_env_overrides=False) or {}
    live = manager.get_plugin_config(plugin_id) or {}
    if not live:
        return False
    env_only = {key: value for key, value in live.items() if stored.get(key) != value}
    saved = unmask_sensitive_values({**stored, **config} if merge else config, stored)
    # The masked view every plugin read answers with (PluginService.mask_config).
    masked = manager._mask_sensitive(live)
    # Judged twice: as the plugin runs now (environment values on top) and as
    # saved (what it runs with once an environment variable is removed).
    return moves_a_secret(live, {**saved, **env_only}, masked, config) or moves_a_secret(live, saved, masked, config)


PLUGIN_KEY_DETAIL = "Enter the plugin's key again: its address or sign-in settings changed."


# -- Backups ------------------------------------------------------------------------


def _is_secret_key(key: str) -> bool:
    from src.config_manager import SENSITIVE_FIELDS

    return key in SENSITIVE_FIELDS or bool(_SECRET_KEY.search(key))


def redact(value: Any, key: str = "", *, inside_secret: bool = False) -> Any:
    """*value* with every secret-looking entry replaced by the mask.

    Scalars are masked, structures keep their shape: under a secret-looking key
    (or ``headers``) every non-empty string leaf is masked, and elsewhere each
    entry is judged by its own key. Numbers and booleans are never secrets.
    """
    secret = inside_secret or key == "headers" or (bool(key) and _is_secret_key(key))
    if isinstance(value, dict):
        return {name: redact(item, str(name), inside_secret=secret) for name, item in value.items()}
    if isinstance(value, list):
        return [redact(item, "", inside_secret=secret) for item in value]
    if secret and isinstance(value, str) and value:
        return MASK
    return value


def _mask_display_configs(data: dict[str, Any]) -> None:
    """Mask each saved display's ``output_config`` by its output's own secret schema, in place.

    The browser's board view masks these the same way (``BoardSettings._mask_board``),
    whatever the secret field is called. When an output cannot say, every string in
    that config is masked (fail closed).
    """
    settings = data.get("settings")
    board_block = settings.get("board") if isinstance(settings, dict) else None
    boards = board_block.get("boards") if isinstance(board_block, dict) else None
    if not isinstance(boards, list):
        return
    from src.outputs.config_hooks import mask_config
    from src.outputs.registry import resolve_output_id

    for board in boards:
        if not isinstance(board, dict) or not isinstance(board.get("output_config"), dict):
            continue
        try:
            board["output_config"] = mask_config(resolve_output_id(board), board["output_config"])
        except Exception:
            board["output_config"] = redact(board["output_config"], inside_secret=True)


def redact_backup(backup: dict[str, Any]) -> dict[str, Any]:
    """A phone's copy of a backup document: secrets masked, marked ``redacted``."""
    document = dict(backup)
    data = copy.deepcopy(backup.get("data") or {})
    if isinstance(data, dict):
        _mask_display_configs(data)
    document["data"] = redact(data)
    document["redacted"] = True
    document["redacted_note"] = (
        "Exported from a phone: passwords, keys and tokens are replaced by ***. "
        "Restoring this file keeps *** in their place, so enter them again afterwards."
    )
    return document
