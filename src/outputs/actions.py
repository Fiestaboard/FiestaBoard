"""Board settings actions and the outputs listing (plan D13).

A board's settings screen is rendered from its output's declaration — a
``settings_schema`` for ``output_config`` and a list of **actions** (test,
discover, identify, detect size, or the output's own, such as Vestaboard's
"enable Local API"). This module runs them, through two doors:

- **saved board** — ``POST /boards/{board_id}/actions/{action}``
  (:func:`run_saved_action`): the board's stored settings, with any edited
  ``output_config`` the body carries merged in. Every ``"***"`` in it is
  restored from the stored board by the same rule saving uses
  (:func:`src.settings.service.restore_masked_board_secrets`), so a test run
  from the settings page never tests a literal ``***``.
- **draft** — ``POST /outputs/{output_id}/actions/{action}``
  (:func:`run_draft_action`): settings typed before a board exists (the
  wizard's scan / test / enable-Local-API; a tile identified before it is
  saved). Nothing is stored, so a ``"***"`` is refused.

An action must be **declared** by the output; its ``input`` is checked
against the declared ``input_schema`` (hidden fields not validated). A
built-in output answers through its ``dispatch`` hook; an output plugin
through :meth:`~src.outputs.plugin_base.OutputPluginBase.run_action` on a
throwaway instance built from the settings — never the board's live one —
closed afterwards. Whatever the action answers becomes the closed
:class:`~src.outputs.models.ActionResult` envelope. **Secret result fields
are never logged**: this module logs the action, the output and the status,
nothing the action returned.

:func:`list_outputs` is ``GET /outputs``: every installed output with what
the "add a board" cards and the settings screen render from.

Raises domain errors; ``routes.py`` maps them.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from .errors import BoardNotFoundError, InvalidActionInputError, InvalidOutputConfigError, OutputNotInstalledError
from .hooks import (
    ActionCall,
    ActionField,
    ActionOutcome,
    OutputActionError,
    OutputActionSpec,
    UnknownOutputAction,
)
from .output_config import masked_secret_paths, validate_output_config
from .plugin_registration import OutputPluginsDisabledError, output_plugins_enabled
from .registry import FIESTAPANEL, VESTABOARD, OutputDefinition, output_registry, resolve_output_id

logger = logging.getLogger(__name__)


def _settings_service():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _definition(output_id: str) -> OutputDefinition:
    definition = output_registry().get(output_id)
    if definition is None:
        raise OutputNotInstalledError(output_id)
    if definition.beta_gated and not output_plugins_enabled():
        raise OutputPluginsDisabledError(output_id)
    return definition


def _spec(definition: OutputDefinition, action: str) -> OutputActionSpec:
    spec = next((a for a in definition.actions if a.id == action), None)
    if spec is None:
        raise UnknownOutputAction(definition.id, action)
    return spec


def _checked_input(spec: OutputActionSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    if spec.input_schema is None:
        if inputs:
            raise InvalidActionInputError(f"Action '{spec.id}' takes no input")
        return {}
    errors = [e.replace("output_config", "input", 1) for e in validate_output_config(inputs, spec.input_schema)]
    if errors:
        raise InvalidActionInputError("; ".join(errors))
    return inputs


# --- running an action ---------------------------------------------------------------------------


def _normalise(raw: Any) -> ActionOutcome:
    if raw is None:
        return ActionOutcome()
    if isinstance(raw, ActionOutcome):
        return raw
    if isinstance(raw, Mapping):
        fields = {
            name: value if isinstance(value, ActionField) else ActionField(**value)
            for name, value in (raw.get("fields") or {}).items()
        }
        devices = raw.get("devices")
        return ActionOutcome(
            status=raw.get("status", "ok"),
            message=raw.get("message", ""),
            guidance=tuple(raw.get("guidance") or ()),
            fields=fields,
            geometry=raw.get("geometry"),
            devices=tuple(devices) if devices is not None else None,
        )
    raise TypeError(f"an action answered {type(raw).__name__}, not an ActionOutcome")


def _run_on_plugin_instance(board: Mapping[str, Any], action: str, inputs: Mapping[str, Any]) -> Any:
    from .factory import draft_driver

    driver = draft_driver(dict(board))
    try:
        return driver.plugin.run_action(action, inputs)
    finally:
        driver.close()


async def _dispatch_plugin(definition: OutputDefinition, call: ActionCall) -> ActionOutcome:
    if call.action == "discover":
        raw = call.inputs.get("timeout", 4.0)
        timeout = min(max(float(raw), 1.0), 15.0) if isinstance(raw, (int, float)) else 4.0
        hook = definition.hooks.discover
        devices = await asyncio.to_thread(hook, timeout) if hook is not None else []
        return ActionOutcome(message=f"Found {len(devices)} device(s).", devices=tuple(devices))
    return _normalise(await asyncio.to_thread(_run_on_plugin_instance, call.board, call.action, call.inputs))


def _with_fills(spec: OutputActionSpec, outcome: ActionOutcome) -> dict[str, Any] | None:
    if not outcome.fields:
        return None
    out = {}
    for name, value in outcome.fields.items():
        declared = spec.result_fields.get(name)
        out[name] = {
            "value": value.value,
            # Declared secret wins: a plugin that forgets the flag on a
            # declared credential still never has it shown or logged.
            "secret": value.secret or bool(declared and declared.secret),
            "fills": declared.fills if declared else None,
        }
    return out


async def _run(definition: OutputDefinition, spec: OutputActionSpec, call: ActionCall) -> dict[str, Any]:
    try:
        if definition.plugin:
            outcome = await _dispatch_plugin(definition, call)
        elif definition.hooks.dispatch is not None:
            outcome = await definition.hooks.dispatch(call)
        else:  # pragma: no cover - every built-in declares a dispatcher
            raise UnknownOutputAction(definition.id, call.action)
    except (OutputActionError, UnknownOutputAction, OutputPluginsDisabledError):
        raise
    except NotImplementedError:
        logger.warning("Output %s declares action %s but does not implement it", definition.id, call.action)
        outcome = ActionOutcome(status="error", message=f"{definition.name} does not implement '{spec.label}'.")
    except Exception as exc:
        # The exception type only: its message may carry what the plugin was handling.
        logger.error("Output %s action %s failed: %s", definition.id, call.action, type(exc).__name__)
        outcome = ActionOutcome(status="error", message=f"'{spec.label}' failed unexpectedly.")
    logger.info(
        "Output %s action %s on %s: %s",
        definition.id,
        call.action,
        call.board_id or "a draft",
        outcome.status,
    )
    return {
        "status": outcome.status,
        "message": outcome.message,
        "guidance": list(outcome.guidance),
        "fields": _with_fills(spec, outcome),
        "geometry": dict(outcome.geometry) if outcome.geometry is not None else None,
        "devices": [dict(d) for d in outcome.devices] if outcome.devices is not None else None,
    }


# --- the two doors ---------------------------------------------------------------------------------


def _draft_board(definition: OutputDefinition, config: dict[str, Any], device_model: str | None) -> dict:
    if definition.id == VESTABOARD:
        return {**config, "output": VESTABOARD}
    if definition.id == FIESTAPANEL:
        return {**config, "output": FIESTAPANEL, "api_mode": "virtual"}
    manifest = definition.output_manifest
    model = device_model or (manifest.device_model_ids[0] if manifest is not None else None)
    return {"output": definition.id, "output_config": config, "device_model": model, "device_type": "panel"}


async def run_draft_action(
    output_id: str,
    action: str,
    *,
    output_config: dict[str, Any],
    inputs: dict[str, Any],
    device_model: str | None = None,
) -> dict[str, Any]:
    """Run *action* of output *output_id* on draft settings (no board yet).

    Raises:
        OutputNotInstalledError, OutputPluginsDisabledError, UnknownOutputAction,
        InvalidOutputConfigError (a masked secret), InvalidActionInputError,
        OutputActionError (refused before the device was contacted).
    """
    definition = _definition(output_id)
    spec = _spec(definition, action)
    schema = definition.settings_schema if definition.plugin else None
    masked = masked_secret_paths(output_config, schema or {}) if schema else _flat_masked(output_config)
    if masked:
        raise InvalidOutputConfigError(f"A draft has no stored secret to restore: enter {', '.join(masked)}")
    if device_model is not None and definition.plugin and device_model not in definition.offered_device_models:
        raise InvalidOutputConfigError(f"Output '{output_id}' declares no device model '{device_model}'")
    call = ActionCall(
        action=action,
        board=_draft_board(definition, dict(output_config), device_model),
        board_id=None,
        inputs=_checked_input(spec, dict(inputs)),
    )
    return await _run(definition, spec, call)


def _flat_masked(config: Mapping[str, Any]) -> list[str]:
    """Masked credentials in a built-in board's flat settings."""
    from src.outputs.vestaboard.connection import TILE_SENSITIVE_FIELDS
    from src.settings.service import BOARD_SENSITIVE_FIELDS

    found = [key for key in sorted(BOARD_SENSITIVE_FIELDS) if config.get(key) == "***"]
    for i, tile in enumerate(config.get("tiles") or []):
        if isinstance(tile, Mapping):
            found += [f"tiles[{i}].{key}" for key in sorted(TILE_SENSITIVE_FIELDS) if tile.get(key) == "***"]
    return found


def _saved_board(board_id: str, output_config: dict[str, Any] | None) -> dict[str, Any]:
    from src.settings.service import restore_masked_board_secrets

    stored = next((b for b in _settings_service().get_board_settings().boards if b.get("id") == board_id), None)
    if stored is None:
        raise BoardNotFoundError(board_id)
    from src.settings.board_shape import board_view

    output_id = resolve_output_id(stored)
    if output_config is None:
        board = dict(stored)
    else:
        config = dict(output_config)
        if output_id == VESTABOARD:
            # Settings v4: a Vestaboard's output_config IS its connection;
            # an edit names only the fields it changes.
            stored_config = stored.get("output_config")
            config = {**(stored_config if isinstance(stored_config, dict) else {}), **config}
        incoming = {**stored, "output_config": config}
        try:
            board = restore_masked_board_secrets(incoming, stored)
        except ValueError as exc:
            raise InvalidOutputConfigError(str(exc)) from exc
    # The first-party actions read a board's connection in the flat shape.
    return board_view(board) if output_id in (VESTABOARD, FIESTAPANEL) else board


async def run_saved_action(
    board_id: str, action: str, *, inputs: dict[str, Any], output_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run *action* on saved board *board_id*, optionally with edited settings.

    Raises:
        BoardNotFoundError, OutputNotInstalledError, OutputPluginsDisabledError,
        UnknownOutputAction, InvalidOutputConfigError, InvalidActionInputError,
        OutputActionError.
    """
    board = _saved_board(board_id, output_config)
    definition = _definition(resolve_output_id(board))
    spec = _spec(definition, action)
    call = ActionCall(action=action, board=board, board_id=board_id, inputs=_checked_input(spec, dict(inputs)))
    return await _run(definition, spec, call)


# --- GET /outputs -----------------------------------------------------------------------------------


def _model_label(model_id: str, manifest: Any) -> str:
    from src.fiestaui import builtin_device_models

    if manifest is not None:
        for model in manifest.device_models:
            if isinstance(model, Mapping) and model.get("id") == model_id:
                return str(model.get("label") or model_id)
    found = builtin_device_models().get(model_id)
    return str(found.get("label") or model_id) if found else model_id


def _describe_action(spec: OutputActionSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "label": spec.label,
        "description": spec.description,
        "builtin": spec.builtin,
        "input_schema": dict(spec.input_schema) if spec.input_schema is not None else None,
        "result_fields": {
            name: {"secret": declared.secret, "fills": declared.fills} for name, declared in spec.result_fields.items()
        },
        "visible_when": dict(spec.visible_when) if spec.visible_when is not None else None,
        "auto_apply": spec.auto_apply,
    }


def describe_output(definition: OutputDefinition) -> dict[str, Any]:
    caps = definition.capabilities
    manifest = definition.output_manifest
    return {
        "id": definition.id,
        "name": definition.name,
        "description": definition.description,
        "icon": definition.icon,
        "builtin": not definition.plugin,
        "beta_gated": definition.beta_gated,
        "available": not definition.beta_gated or output_plugins_enabled(),
        "output_api": manifest.output_api if manifest is not None else None,
        "capabilities": {
            "technology": caps.technology,
            "delivery": caps.delivery,
            "animation": caps.animation,
            "native_transitions": sorted(caps.native_transitions),
            "charset": caps.charset,
        },
        "device_models": [
            {"id": model_id, "label": _model_label(model_id, manifest)} for model_id in definition.offered_device_models
        ],
        "settings_schema": dict(definition.settings_schema),
        "actions": [_describe_action(spec) for spec in definition.actions],
    }


def list_outputs() -> list[dict[str, Any]]:
    """Every installed output: the built-ins first, then plugins by name."""
    registry = output_registry()
    definitions = [registry.get(output_id) for output_id in registry.ids()]
    ordered = sorted(
        (d for d in definitions if d is not None),
        key=lambda d: (d.plugin, d.id != VESTABOARD, d.name.lower()),
    )
    return [describe_output(d) for d in ordered]
