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
against the declared ``input_schema`` (hidden fields not validated). One
input is generic: ``hint_host`` (:data:`~src.outputs.hooks.HINT_HOST`), the
private IPv4 address the user opened FiestaBoard at, which the web UI sends
with every scan. Any action accepts it; ``discover`` receives it (a
non-private value is refused), an action that declares it receives it as its
schema checks it, and any other action never sees it. Every
output answers through its plugin class's
:meth:`~src.outputs.plugin_base.OutputPluginBase.handle_action`, the
first-party ones included (core holds no device's actions, Phase 4 P4e),
with an :class:`~src.outputs.hooks.ActionContext`: the instances an action
uses are core's to build — a throwaway one from the settings (closed when
the action returns), or the board's live one under its send lock — and the
whole action runs on the bounded board-send pool, off the event loop.
Whatever the action answers becomes the closed
:class:`~src.outputs.models.ActionResult` envelope. **Secret result fields
are never logged**: this module logs the action, the output and the status,
nothing the action returned.

:func:`execute_action` is the same run without the envelope, for the legacy
routes that predate it (``/config/board/test``, ``/config/board/enable-local-api``,
``/settings/board/{id}/identify``, ``/settings/board/{id}/detect-size``):
they answer the outcome's ``detail`` in their own recorded shapes.

:func:`list_outputs` is ``GET /outputs``: every installed output with what
the "add a board" cards and the settings screen render from.

Raises domain errors; ``routes.py`` maps them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from src.output_allowlist import flush_refusal_summary

from .errors import BoardNotFoundError, InvalidActionInputError, InvalidOutputConfigError, OutputNotInstalledError
from .hooks import (
    HINT_HOST,
    ActionContext,
    ActionField,
    ActionOutcome,
    OutputActionError,
    OutputActionSpec,
    UnknownOutputAction,
    lan_hint,
)
from .output_config import validate_output_config
from .registry import FIESTAPANEL, VESTABOARD, OutputDefinition, output_registry, resolve_output_id

logger = logging.getLogger(__name__)


def _settings_service():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _definition(output_id: str) -> OutputDefinition:
    definition = output_registry().get(output_id)
    if definition is None:
        raise OutputNotInstalledError(output_id)
    return definition


def _spec(definition: OutputDefinition, action: str) -> OutputActionSpec:
    spec = next((a for a in definition.actions if a.id == action), None)
    if spec is None:
        raise UnknownOutputAction(definition.id, action)
    return spec


def _declares(spec: OutputActionSpec, name: str) -> bool:
    properties = spec.input_schema.get("properties") if spec.input_schema is not None else None
    return isinstance(properties, Mapping) and name in properties


def _checked_input(spec: OutputActionSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    # The network hint (HINT_HOST) is a generic input every action accepts:
    # the web UI sends it with every scan, for every output. An action that
    # declares it gets it as its schema checks it; ``discover`` gets it as a
    # private IPv4 address; any other action never sees it.
    hint = inputs.pop(HINT_HOST, None)
    if _declares(spec, HINT_HOST):
        if hint is not None:
            inputs[HINT_HOST] = hint
        hint = None
    elif hint not in (None, ""):
        hint = lan_hint(hint)
        if hint is None:
            raise InvalidActionInputError(f"{HINT_HOST} must be a private IPv4 address")
    else:
        hint = None
    if spec.input_schema is None:
        if inputs:
            raise InvalidActionInputError(f"Action '{spec.id}' takes no input")
        inputs = {}
    else:
        errors = [e.replace("output_config", "input", 1) for e in validate_output_config(inputs, spec.input_schema)]
        if errors:
            raise InvalidActionInputError("; ".join(errors))
    if hint is not None and spec.id == "discover":
        inputs[HINT_HOST] = hint
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
            detail=raw.get("detail") or {},
        )
    raise TypeError(f"an action answered {type(raw).__name__}, not an ActionOutcome")


def _default_live_driver(board_id: str) -> Any:
    from src.display_runtime import live_driver

    return live_driver(board_id)


def _default_invalidate(board_id: str) -> None:
    from src.display_runtime import peek_service

    service = peek_service()
    if service is not None:
        service.invalidate_board_content(board_id)


class _Lent:
    """What core lends one action run (:class:`ActionContext`): the
    throwaway instances it builds (closed afterwards) and the live board."""

    def __init__(
        self,
        definition: OutputDefinition,
        board: Mapping[str, Any],
        board_id: str | None,
        live_driver: Callable[[str], Any],
        invalidate: Callable[[str], None],
    ) -> None:
        self.definition = definition
        self.board = board
        self.board_id = board_id
        self._live_driver = live_driver
        self._invalidate = invalidate
        self._drivers: list[Any] = []

    def _draft(self, board: Mapping[str, Any]) -> Any:
        from .factory import draft_driver

        driver = draft_driver(dict(board))
        if driver is not None:
            self._drivers.append(driver)
        return driver

    def instance(self, config: Mapping[str, Any] | None) -> Any:
        """A throwaway plugin instance from the board's settings, or from *config*."""
        if config is None:
            board = self.board
        else:
            board = {"output": self.definition.id, "output_config": dict(config)}
        driver = self._draft(board)
        return getattr(driver, "plugin", None) if driver is not None else None

    def live_driver(self) -> Any:
        return self._live_driver(self.board_id) if self.board_id is not None else None

    def with_live(self, fn: Any) -> Any:
        driver = self.live_driver()
        run = getattr(driver, "run_with_plugin", None)
        if run is None:
            raise OutputActionError(503, f"Board client not initialized: {self.board_id}")
        return run(fn)

    def reader(self) -> Any:
        driver = self.live_driver() or self._draft(self.board)
        return driver.read_current_message if driver is not None else None

    def invalidate(self) -> None:
        if self.board_id is not None:
            self._invalidate(self.board_id)

    def close(self) -> None:
        for driver in self._drivers:
            try:
                driver.close()
            except Exception:  # pragma: no cover - a close failure is the plugin's to log
                logger.debug("Closing an action's throwaway driver failed", exc_info=True)


def _as_refusal(exc: BaseException) -> OutputActionError | None:
    """A refusal raised with a status and a detail (the board-host guards
    raise the web framework's own) as an :class:`OutputActionError`."""
    status, detail = getattr(exc, "status_code", None), getattr(exc, "detail", None)
    if isinstance(status, int) and 400 <= status < 600 and isinstance(detail, str):
        return OutputActionError(status, detail)
    return None


def _execute_sync(
    definition: OutputDefinition,
    action: str,
    board: Mapping[str, Any],
    board_id: str | None,
    inputs: dict[str, Any],
    live_driver: Callable[[str], Any],
    invalidate: Callable[[str], None],
) -> ActionOutcome:
    lent = _Lent(definition, board, board_id, live_driver, invalidate)
    ctx = ActionContext(
        action=action,
        board=board,
        board_id=board_id,
        inputs=inputs,
        instance=lent.instance,
        with_live=lent.with_live,
        reader=lent.reader,
        invalidate=lent.invalidate,
    )
    try:
        return _normalise(definition.plugin_class.handle_action(ctx))
    except OutputActionError:
        raise
    except Exception as exc:
        refusal = _as_refusal(exc)
        if refusal is not None:
            raise refusal from exc
        raise
    finally:
        lent.close()


async def execute_action(
    definition: OutputDefinition,
    action: str,
    *,
    board: Mapping[str, Any],
    board_id: str | None,
    inputs: Mapping[str, Any],
    live_driver: Callable[[str], Any] | None = None,
    invalidate: Callable[[str], None] | None = None,
) -> ActionOutcome:
    """Run *action* of *definition*'s output on *board*; the outcome, unenveloped.

    The legacy routes' door (and :func:`_run`'s). Runs on the bounded
    board-send pool. *live_driver* finds a saved board's live driver and
    *invalidate* makes core re-send its content: the caller's seams, else
    :func:`src.display_runtime.live_driver` and the display service's
    ``invalidate_board_content``.

    Raises:
        OutputActionError: refused before (or instead of) contacting the
            device — the 4xx/503 to answer.
        Exception: anything else the output raised (the caller decides).
    """
    from src.board_send_executor import run_board_send

    if definition.plugin_class is None:  # pragma: no cover - a test's stand-in entry
        raise UnknownOutputAction(definition.id, action)
    return await run_board_send(
        _execute_sync,
        definition,
        action,
        board,
        board_id,
        dict(inputs),
        live_driver or _default_live_driver,
        invalidate or _default_invalidate,
    )


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


async def _run(
    definition: OutputDefinition,
    spec: OutputActionSpec,
    *,
    board: Mapping[str, Any],
    board_id: str | None,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        outcome = await execute_action(definition, spec.id, board=board, board_id=board_id, inputs=inputs)
    except (OutputActionError, UnknownOutputAction):
        raise
    except NotImplementedError:
        logger.warning("Output %s declares action %s but does not implement it", definition.id, spec.id)
        outcome = ActionOutcome(status="error", message=f"{definition.name} does not implement '{spec.label}'.")
    except Exception as exc:
        # The exception type only: its message may carry what the plugin was handling.
        logger.error("Output %s action %s failed: %s", definition.id, spec.id, type(exc).__name__)
        outcome = ActionOutcome(status="error", message=f"'{spec.label}' failed unexpectedly.")
    # A scan refused host by host by FIESTABOARD_OUTPUTS_ALLOW_HOSTS: its count, once.
    flush_refusal_summary()
    logger.info(
        "Output %s action %s on %s: %s",
        definition.id,
        spec.id,
        board_id or "a draft",
        outcome.status,
    )
    return {
        "status": outcome.status,
        "message": outcome.message,
        "guidance": list(outcome.guidance),
        "fields": _with_fills(spec, outcome),
        "geometry": dict(outcome.geometry) if outcome.geometry is not None else None,
        "devices": [_device_view(d) for d in outcome.devices] if outcome.devices is not None else None,
    }


#: What :class:`~src.outputs.models.DiscoveredDevice` names itself.
_DEVICE_KEYS = frozenset({"ip", "port", "hostname", "source", "label", "fields"})


def _device_view(device: Mapping[str, Any]) -> dict[str, Any]:
    """A found device as the API answers it: the core keys, and every other
    scalar the output reported under ``fields`` (what picking it fills)."""
    view = {key: value for key, value in device.items() if key in _DEVICE_KEYS and key != "fields"}
    extra = {**{k: v for k, v in device.items() if k not in _DEVICE_KEYS}, **dict(device.get("fields") or {})}
    view["fields"] = {str(k): v for k, v in extra.items() if isinstance(v, (str, int, float, bool))}
    return view


# --- the two doors ---------------------------------------------------------------------------------


def draft_board(definition: OutputDefinition, config: dict[str, Any], device_model: str | None = None) -> dict:
    """The board an action on draft settings runs on: no id, the settings
    as its ``output_config``. A first-party draft's own facts
    (``device_type``, ``notes_wide`` …) ride in its settings, as they
    always did."""
    if definition.id == VESTABOARD:
        return {**config, "output": VESTABOARD, "output_config": config}
    if definition.id == FIESTAPANEL:
        return {**config, "output": FIESTAPANEL, "api_mode": "virtual", "output_config": {}}
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
        OutputNotInstalledError, UnknownOutputAction,
        InvalidOutputConfigError (a masked secret), InvalidActionInputError,
        OutputActionError (refused before the device was contacted).
    """
    from .config_hooks import masked_config_paths

    definition = _definition(output_id)
    spec = _spec(definition, action)
    masked = masked_config_paths(output_id, output_config)
    if masked:
        raise InvalidOutputConfigError(f"A draft has no stored secret to restore: enter {', '.join(masked)}")
    if device_model is not None and definition.plugin and device_model not in definition.offered_device_models:
        raise InvalidOutputConfigError(f"Output '{output_id}' declares no device model '{device_model}'")
    board = draft_board(definition, dict(output_config), device_model)
    return await _run(definition, spec, board=board, board_id=None, inputs=_checked_input(spec, dict(inputs)))


def saved_board(board_id: str, output_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Saved board *board_id* as an action runs on it: the stored board,
    with an edited ``output_config`` merged in and every ``"***"`` restored.

    Raises:
        BoardNotFoundError, InvalidOutputConfigError.
    """
    from src.settings.service import restore_masked_board_secrets

    stored = next((b for b in _settings_service().get_board_settings().boards if b.get("id") == board_id), None)
    if stored is None:
        raise BoardNotFoundError(board_id)
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
    from src.devices import BoardInstance

    # The settings-v4 shape whatever was stored: the output reads its
    # output_config, normalised the way the board is saved.
    return BoardInstance.from_dict(board).to_dict()


async def run_saved_action(
    board_id: str, action: str, *, inputs: dict[str, Any], output_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run *action* on saved board *board_id*, optionally with edited settings.

    Raises:
        BoardNotFoundError, OutputNotInstalledError,
        UnknownOutputAction, InvalidOutputConfigError, InvalidActionInputError,
        OutputActionError.
    """
    board = saved_board(board_id, output_config)
    definition = _definition(resolve_output_id(board))
    spec = _spec(definition, action)
    return await _run(definition, spec, board=board, board_id=board_id, inputs=_checked_input(spec, dict(inputs)))


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
        # Deprecated wire fields (until v11): display plugins need no opt-in
        # since settings v7, so nothing is gated and everything is available.
        "beta_gated": False,
        "available": True,
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
