"""What core asks an output about a board's settings (plan D13, Phase 4 P4e).

Core keeps a board's identity, display and geometry; everything about its
``output_config`` is its output's. This module is where core asks — the
output's plugin class (:attr:`OutputDefinition.plugin_class
<src.outputs.registry.OutputDefinition.plugin_class>`), whose defaults
(:class:`~src.outputs.plugin_base.OutputPluginBase`) follow the manifest's
``settings_schema``:

- :func:`normalize_config` — the ``output_config`` a board stores;
- :func:`mask_config` / :func:`restore_config` / :func:`masked_config_paths`
  — its secrets as ``"***"`` in every API view, restored from an echo, and
  refused when they cannot be;
- :func:`board_status` — the board's connection summary
  (:class:`~src.outputs.hooks.OutputStatus`);
- :func:`legacy_flat_fields` — the settings-v3 flat fields every API view of
  a board still carries (plan D8 "Public API shapes unchanged"), as the
  Vestaboard's plugin declares them: it is the output whose settings predate
  ``output_config``.

An output that is **not installed** has no class to ask: its config is
withheld whole in an API view (``"***"``) and an echoed ``"***"`` keeps what
is stored — unknown is treated as secret — it is stored as given, and it has
no status.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .hooks import OutputStatus

_FIESTAPANEL = "fiestapanel"


def plugin_class_for(output_id: str | None) -> Any:
    """The plugin class of installed output *output_id*, or ``None``."""
    from .registry import output_registry

    definition = output_registry().get(output_id)
    return definition.plugin_class if definition is not None else None


def _schema(output_id: str | None) -> Mapping[str, Any] | None:
    from .registry import output_registry

    definition = output_registry().get(output_id)
    return definition.settings_schema if definition is not None else None


def normalize_config(output_id: str, config: Any, board: Mapping[str, Any]) -> dict[str, Any]:
    """The ``output_config`` board *board* stores for output *output_id*."""
    cls = plugin_class_for(output_id)
    if cls is None:
        return dict(config) if isinstance(config, Mapping) else {}
    return cls.normalize_config(config, board)


def mask_config(output_id: str, config: Any) -> Any:
    """*config* for an API view: every set secret ``"***"`` (withheld whole
    when the output is not installed)."""
    cls = plugin_class_for(output_id)
    if cls is None:
        from .output_config import mask_output_config

        return mask_output_config(config, None)
    return cls.mask_config(config, _schema(output_id))


def restore_config(output_id: str, incoming: Any, stored: Any) -> Any:
    """*incoming* with each echoed ``"***"`` restored from *stored*."""
    cls = plugin_class_for(output_id)
    if cls is None:
        from .output_config import unmask_output_config

        return unmask_output_config(incoming, stored, None)
    return cls.restore_config(incoming, stored, _schema(output_id))


def masked_config_paths(output_id: str, config: Any) -> list[str]:
    """The secrets in *config* still reading ``"***"``."""
    cls = plugin_class_for(output_id)
    if cls is None:
        from .output_config import masked_secret_paths

        return masked_secret_paths(config, None)
    return cls.masked_config_paths(config, _schema(output_id))


def board_status(board: Mapping[str, Any]) -> OutputStatus | None:
    """Board *board*'s connection summary, as its output reads its settings.

    A FiestaPanel draws in memory: always connected. ``None`` when the
    output has nothing to say (or is not installed).
    """
    from .registry import resolve_output_id

    output_id = resolve_output_id(board)
    if output_id == _FIESTAPANEL:
        return OutputStatus(configured=True)
    cls = plugin_class_for(output_id)
    if cls is None:
        return None
    config = board.get("output_config")
    config = config if isinstance(config, Mapping) else {}
    try:
        status = cls.board_status(config, board)
    except Exception:  # a plugin's summary must never break a settings read
        import logging

        logging.getLogger(__name__).exception("Output %s: board_status failed", output_id)
        return None
    if status is None:
        status = _status_from_schema(config, _schema(output_id))
    return status


def _is_set(value: Any) -> bool:
    return value not in (None, "", [], {})


def _status_from_schema(config: Mapping[str, Any], schema: Mapping[str, Any] | None) -> OutputStatus:
    """The status of an output with no ``board_status`` hook: configured when
    every setting its ``settings_schema`` requires is set (with no schema,
    when anything is), attempted when any setting is."""
    attempted = any(_is_set(value) for value in config.values())
    required = schema.get("required") if isinstance(schema, Mapping) else None
    if isinstance(required, list) and required:
        configured = all(_is_set(config.get(name)) for name in required)
    else:
        configured = attempted
    return OutputStatus(configured=configured, attempted=attempted)


def legacy_flat_fields() -> dict[str, Any]:
    """The settings-v3 flat fields of a board, with their defaults.

    Declared by the output whose settings predate ``output_config`` (the
    Vestaboard's plugin, ``legacy_flat_fields``). When it is not installed
    the fields are still answered, with no defaults beyond the empty ones.
    """
    from .registry import VESTABOARD

    cls = plugin_class_for(VESTABOARD)
    declared = getattr(cls, "legacy_flat_fields", None) if cls is not None else None
    if isinstance(declared, Mapping):
        return {k: (list(v) if isinstance(v, list) else v) for k, v in declared.items()}
    from src.devices import LEGACY_CONNECTION_FIELDS

    return {name: [] if name == "tiles" else None for name in LEGACY_CONNECTION_FIELDS}


def mask_flat_fields(flat: Mapping[str, Any]) -> dict[str, Any]:
    """The settings-v3 flat fields of an API view with their credentials
    ``"***"``: they are the Vestaboard's settings in their old place, so its
    rules mask them (every set value, when it is not installed)."""
    from .registry import VESTABOARD

    cls = plugin_class_for(VESTABOARD)
    if cls is None:
        return {key: ("***" if value else value) for key, value in flat.items()}
    return dict(cls.mask_config(dict(flat), _schema(VESTABOARD)))


def restore_flat_fields(flat: dict[str, Any], stored: Mapping[str, Any]) -> dict[str, Any]:
    """The settings-v3 flat fields of a legacy write with each echoed
    ``"***"`` restored from the stored board's, by the Vestaboard's rules
    (field by field when it is not installed)."""
    from .registry import VESTABOARD

    cls = plugin_class_for(VESTABOARD)
    if cls is None:
        return {key: (stored.get(key, value) if value == "***" else value) for key, value in flat.items()}
    return dict(cls.restore_config(flat, stored, _schema(VESTABOARD)))
