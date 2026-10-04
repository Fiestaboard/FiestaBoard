"""A board's ``output_config``: secrets masked on the way out, restored on the way in.

An output plugin's board settings are described by its manifest's
``output.settings_schema``. A property is **secret** when it says so —
``"secret": true`` — or is a ``"ui:widget": "password"`` field, at any depth
(nested ``properties``, array ``items``). Secrets never leave the process:

- :func:`mask_output_config` replaces every set secret with ``"***"`` for
  the API view of a board.
- :func:`unmask_output_config` restores each ``"***"`` the client echoes
  back from the stored config. Inside an array, an element is matched to its
  stored counterpart by its ``id``/``name``/``key`` (the same evidence rule
  as plugin settings, ``src/config_manager.py``); an element that cannot be
  matched keeps ``"***"``, and :func:`masked_secret_paths` lets the caller
  refuse the save rather than store three asterisks as a credential.

When the board's output is **not installed** there is no schema to say what
is secret, so the whole ``output_config`` is withheld (masked as ``"***"``)
and an echoed ``"***"`` keeps the stored config untouched: unknown is
treated as secret, never shown.

Since settings v4 every board carries an ``output_config``. These rules are
an output *plugin's*; a Vestaboard's (the first-party output core still
interprets, its tiles matched by endpoint) are
:mod:`src.outputs.vestaboard.connection`'s, and a FiestaPanel's is empty.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MASKED = "***"
_IDENTITY_FIELDS = ("id", "name", "key")


def _is_secret(prop: Mapping[str, Any]) -> bool:
    return prop.get("secret") is True or prop.get("ui:widget") == "password"


def _properties(schema: Any) -> Mapping[str, Any]:
    props = schema.get("properties") if isinstance(schema, Mapping) else None
    return props if isinstance(props, Mapping) else {}


def _items(schema: Any) -> Any:
    return schema.get("items") if isinstance(schema, Mapping) else None


def mask_output_config(config: Any, schema: Mapping[str, Any] | None) -> Any:
    """*config* with every set secret replaced by ``"***"``; a copy.

    ``schema=None`` (the output is not installed): the whole config is ``"***"``.
    """
    if schema is None:
        return MASKED if config else config
    return _mask(config, schema)


def _mask(value: Any, schema: Any) -> Any:
    if isinstance(value, dict):
        props = _properties(schema)
        out = {}
        for key, item in value.items():
            prop = props.get(key)
            if isinstance(prop, Mapping) and _is_secret(prop):
                out[key] = MASKED if item else item
            else:
                out[key] = _mask(item, prop)
        return out
    if isinstance(value, list):
        return [_mask(item, _items(schema)) for item in value]
    return value


def unmask_output_config(incoming: Any, stored: Any, schema: Mapping[str, Any] | None) -> Any:
    """*incoming* with every echoed ``"***"`` secret restored from *stored*; a copy.

    ``schema=None`` (the output is not installed): an echoed ``"***"`` for
    the whole config keeps *stored*.
    """
    if schema is None:
        return stored if incoming == MASKED else incoming
    return _unmask(incoming, stored, schema)


_UNMATCHED = object()


def _match(item: Any, stored_list: list) -> Any:
    if not isinstance(item, dict):
        return _UNMATCHED
    for field in _IDENTITY_FIELDS:
        if field in item:
            hits = [s for s in stored_list if isinstance(s, dict) and s.get(field) == item[field]]
            return hits[0] if len(hits) == 1 else _UNMATCHED
    return _UNMATCHED


def _unmask(value: Any, stored: Any, schema: Any) -> Any:
    if isinstance(value, dict):
        props = _properties(schema)
        stored_dict = stored if isinstance(stored, dict) else {}
        out = {}
        for key, item in value.items():
            prop = props.get(key)
            if isinstance(prop, Mapping) and _is_secret(prop) and item == MASKED:
                out[key] = MASKED if stored is _UNMATCHED else stored_dict.get(key, "")
            else:
                out[key] = _unmask(item, _UNMATCHED if stored is _UNMATCHED else stored_dict.get(key), prop)
        return out
    if isinstance(value, list):
        stored_list = stored if isinstance(stored, list) else []
        return [
            _unmask(item, _UNMATCHED if stored is _UNMATCHED else _match(item, stored_list), _items(schema))
            for item in value
        ]
    return value


def masked_secret_paths(config: Any, schema: Mapping[str, Any] | None, path: str = "") -> list[str]:
    """Paths of secrets still reading ``"***"`` after :func:`unmask_output_config`."""
    found: list[str] = []
    if schema is None:
        return [path or "output_config"] if config == MASKED else []
    if isinstance(config, dict):
        props = _properties(schema)
        for key, item in config.items():
            prop = props.get(key)
            here = f"{path}.{key}" if path else key
            if isinstance(prop, Mapping) and _is_secret(prop) and item == MASKED:
                found.append(here)
            else:
                found.extend(masked_secret_paths(item, prop if isinstance(prop, Mapping) else {}, here))
    elif isinstance(config, list):
        for i, item in enumerate(config):
            items = _items(schema)
            found.extend(masked_secret_paths(item, items if isinstance(items, Mapping) else {}, f"{path}[{i}]"))
    return found


def board_context(board: Mapping[str, Any]) -> dict[str, Any]:
    """The board facts ``ui:visible_when`` reads by their ``@`` names."""
    return {"device_type": board.get("device_type"), "device_model": board.get("device_model")}


def validate_output_config(
    config: Any, schema: Mapping[str, Any], context: Mapping[str, Any] | None = None
) -> list[str]:
    """Errors for *config* against the output's ``settings_schema`` (empty = valid).

    Fields hidden by ``ui:visible_when`` are not validated
    (:func:`src.plugins.settings_ui.strip_hidden`): the user cannot see them.
    *context* is the board's ``@`` facts (:func:`board_context`).
    """
    from jsonschema import Draft7Validator

    from src.plugins.settings_ui import strip_hidden

    visible, visible_schema = strip_hidden(config, schema, context)
    errors = sorted(Draft7Validator(visible_schema).iter_errors(visible), key=lambda e: [str(p) for p in e.path])
    return [f"output_config{''.join(f'.{p}' for p in e.path)}: {e.message}" for e in errors]
