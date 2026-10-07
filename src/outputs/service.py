"""Creating a board for an output plugin (plan D5, Phase 2.5).

``POST /outputs/{output_id}/boards`` lands here. Vestaboards keep
``POST /settings/board/add`` and FiestaPanels ``POST /panels``; this creates
every other board, from what the output plugin declares:

1. the output must be an installed output **plugin** (a built-in id is sent
   to its own route);
2. the device model must be one the plugin declares;
3. the content grid comes from that model (:mod:`src.outputs.geometry`) and
   is **refused below the 3 × 15 Note floor here, before the board's geometry
   is resolved** — the stored ``panel`` grid then passes through
   ``clamp_grid`` untouched instead of being inflated;
4. ``output_config`` must fit the plugin's settings schema, with no masked
   ``"***"`` secret (a new board has nothing stored to restore);
5. the board is saved with an explicit ``output`` and ``output_config`` and
   its grid as a custom ``panel`` grid (``device_type: "panel"`` plus
   ``grid_rows``/``grid_cols``: plan D8, an LED board is a custom grid) —
   never coerced to a Vestaboard shape.

Raises domain errors (:mod:`src.outputs.errors`); the router maps them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.devices import BUILTIN_OUTPUT_IDS

from .board_profile import board_profile
from .errors import (
    BuiltinOutputError,
    InvalidOutputConfigError,
    OutputNotInstalledError,
    UndeclaredDeviceModelError,
)
from .geometry import resolve_content_grid
from .output_config import mask_output_config, masked_secret_paths, validate_output_config
from .registry import OutputDefinition, output_registry


def _settings_service():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _plugin_output(output_id: str) -> OutputDefinition:
    if output_id in BUILTIN_OUTPUT_IDS:
        raise BuiltinOutputError(output_id)
    definition = output_registry().get(output_id)
    if definition is None or not definition.plugin or definition.output_manifest is None:
        raise OutputNotInstalledError(output_id)
    return definition


def _checked_config(config: dict[str, Any], schema: Mapping[str, Any], device_model: str) -> dict[str, Any]:
    masked = masked_secret_paths(config, schema)
    if masked:
        raise InvalidOutputConfigError(f"A new board has no stored secret to restore: enter {', '.join(masked)}")
    errors = validate_output_config(config, schema, {"device_type": "panel", "device_model": device_model})
    if errors:
        raise InvalidOutputConfigError("; ".join(errors))
    return config


def describe_board(board: Mapping[str, Any]) -> dict[str, Any]:
    """A saved output-plugin board as the create route answers it."""
    definition = output_registry().get(board["output"])
    schema = dict(definition.settings_schema) if definition is not None else None
    profile = board_profile(board)
    return {
        "id": board["id"],
        "name": board["name"],
        "output": board["output"],
        "device_model": board["device_model"],
        "charset": profile.charset,
        "device_type": board["device_type"],
        "rows": board["grid_rows"],
        "cols": board["grid_cols"],
        "output_config": mask_output_config(board["output_config"], schema),
    }


def create_output_board(
    output_id: str,
    *,
    device_model: str,
    output_config: dict[str, Any],
    name: str | None = None,
    geometry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create and save a board driven by output plugin *output_id*.

    Returns the saved board dict (unmasked; :func:`describe_board` shows it).

    Raises:
        BuiltinOutputError, OutputNotInstalledError,
        UndeclaredDeviceModelError, BelowFloorError, GeometryError,
        InvalidOutputConfigError.
    """
    definition = _plugin_output(output_id)
    manifest = definition.output_manifest
    declared = manifest.device_model_ids
    if device_model not in declared:
        raise UndeclaredDeviceModelError(output_id, device_model, declared)
    model = manifest.model(declared.index(device_model))
    rows, cols = resolve_content_grid(model, manifest.character_set, geometry)
    config = _checked_config(dict(output_config), definition.settings_schema, device_model)
    settings = _settings_service().add_board(
        {
            "name": name or "",
            "output": output_id,
            "output_config": config,
            "device_model": device_model,
            "device_type": "panel",
            "grid_rows": rows,
            "grid_cols": cols,
        }
    )
    return settings.boards[-1]
