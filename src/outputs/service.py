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
   never coerced to a Vestaboard shape;
6. an LED board measured in pixels gets its text size written down
   (``output_config.font``): the one asked for when its model offers it,
   else the model's new-board default (``layoutOptions.font.default``; a
   Pixoo 64 is Large, 5x7, 8 × 10). Its grid is sized in that face.

Raises domain errors (:mod:`src.outputs.errors`); the router maps them.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from src.devices import BUILTIN_OUTPUT_IDS
from src.led.matrix import layout_policy_for_model, model_with_led_font

from .board_profile import FONT_CONFIG_KEY, board_profile, offers_font_choice
from .errors import (
    BuiltinOutputError,
    InvalidOutputConfigError,
    OutputNotInstalledError,
    UndeclaredDeviceModelError,
)
from .geometry import resolve_content_grid
from .output_config import mask_output_config, masked_secret_paths, validate_output_config
from .registry import OutputDefinition, output_registry

logger = logging.getLogger(__name__)


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


def new_board_font(
    model: Mapping[str, Any], definition: OutputDefinition, requested: Any, schema: Mapping[str, Any]
) -> str | None:
    """The face a new board on *model* is created in, or ``None`` when the
    board has no choice to record: not an LED board measured in pixels, an
    output whose own character set fixes the face (plan D17), or a settings
    schema that admits no ``font`` key."""
    manifest = definition.output_manifest
    if not offers_font_choice(model) or (manifest is not None and manifest.character_set is not None):
        return None
    properties = schema.get("properties") if isinstance(schema.get("properties"), Mapping) else {}
    if schema.get("additionalProperties") is False and FONT_CONFIG_KEY not in properties:
        return None
    policy = layout_policy_for_model(model)["font"]
    if requested is not None and requested not in policy["allowed"]:
        logger.warning(
            # The value itself is not logged: it comes from output_config, which can hold secrets.
            "New %s board: its text size is not one %s offers (%s); creating it in %s",
            definition.id,
            model.get("id"),
            ", ".join(policy["allowed"]),
            policy["default"],
        )
        return policy["default"]
    return requested if requested is not None else policy["default"]


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
    font = new_board_font(model, definition, output_config.get(FONT_CONFIG_KEY), definition.settings_schema)
    if font is not None:
        model = model_with_led_font(model, font)
    rows, cols = resolve_content_grid(model, manifest.character_set, geometry)
    config = _checked_config(
        {k: v for k, v in output_config.items() if k != FONT_CONFIG_KEY or font is None},
        definition.settings_schema,
        device_model,
    )
    if font is not None:
        config[FONT_CONFIG_KEY] = font
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
