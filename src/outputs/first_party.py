"""The first-party outputs — Vestaboard and FiestaPanel — loaded as output plugins.

Phase 4 of the output-plugins program turns the two devices FiestaBoard was
built for into output plugins like any other. Their packages are staged
in-repo under ``first_party_outputs/<id>/`` (laid out as their own
repositories will be) and import FiestaBoard only through the author API.
This module loads each one through the output-plugin path — its manifest
validated by :func:`src.plugins.manifest.load_manifest` (``$ref`` device
models included), its ``OutputPluginBase`` subclass imported — and puts it
in the output registry under its id, ``vestaboard`` / ``fiestapanel``.

They differ from a third-party output plugin in four ways, each on purpose:

- **Never beta-gated**, and **never replaced**: the registry entry is
  ``plugin=False``, so an installed plugin cannot take the id (until the
  seed takes over their delivery, P4b).
- **Their boards predate** ``output_config``: each instance is built from
  the board by the plugin's own ``config_from_board`` (today's flat fields;
  ``None`` → no usable connection, no driver). Settings v4 (P4c) moves the
  fields; nothing on disk changes here.
- **They behave exactly as before** (``tests/golden/wire``): the driver runs
  their writes inline with no budget or breaker (``first_party=True``) and
  their requests are the ``requests`` module calls they always were
  (:meth:`OutputHttp.for_first_party <src.outputs.http.OutputHttp.for_first_party>`).
- **They present as they always have**: ``GET /outputs`` shows no
  ``output_api``, no settings schema (their settings screens are still the
  hand-coded ones until P4d) and FiestaPanel's ``vestaboard_panel`` model;
  board-settings actions still run through core's legacy dispatchers, which
  call into the plugin for every device conversation.
"""

from __future__ import annotations

import importlib
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .hooks import ActionCall, ActionOutcome, OutputDiagnostics, OutputHooks
from .plugin_base import OutputPluginBase
from .registry import FIESTAPANEL, VESTABOARD, OutputDefinition, OutputRegistry

if TYPE_CHECKING:
    from src.plugins.manifest import PluginManifest

    from .driver import OutputDriver

logger = logging.getLogger(__name__)

#: The importable package the staged first-party outputs live in.
FIRST_PARTY_PACKAGE = "first_party_outputs"
#: Its directory, at the repo root.
FIRST_PARTY_DIR = Path(__file__).resolve().parents[2] / FIRST_PARTY_PACKAGE
#: The first-party outputs, in the order they are registered.
FIRST_PARTY_OUTPUTS: tuple[str, ...] = (VESTABOARD, FIESTAPANEL)

#: Device models the "add a board" cards offer for an output, where that
#: still differs from its manifest (until settings v4 / P4d).
_LEGACY_OFFERED_MODELS: dict[str, tuple[str, ...]] = {FIESTAPANEL: ("vestaboard_panel",)}


class FirstPartyOutputError(RuntimeError):
    """A staged first-party output package could not be loaded."""


@dataclass(frozen=True)
class FirstPartyOutput:
    """A loaded first-party output: its plugin class and parsed manifest."""

    plugin_class: type[OutputPluginBase]
    manifest: PluginManifest


def _import_package(output_id: str) -> Any:
    name = f"{FIRST_PARTY_PACKAGE}.{output_id}"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name not in (FIRST_PARTY_PACKAGE, name):
            raise
    # Run from somewhere the repo root is not on the path (a script): add it.
    root = str(FIRST_PARTY_DIR.parent)
    if root not in sys.path:
        sys.path.append(root)
    return importlib.import_module(name)


def load_first_party(output_id: str) -> FirstPartyOutput:
    """Load the staged package of first-party output *output_id*.

    Raises:
        FirstPartyOutputError: its manifest does not validate, is not an
            output plugin of that id, or the package exports no single
            ``OutputPluginBase`` subclass.
    """
    from src.plugins.manifest import load_manifest

    manifest, errors = load_manifest(FIRST_PARTY_DIR / output_id / "manifest.json")
    if errors or manifest is None:
        raise FirstPartyOutputError(f"{output_id}: manifest.json is invalid: {'; '.join(errors)}")
    if manifest.id != output_id or manifest.plugin_type != "output" or manifest.output is None:
        raise FirstPartyOutputError(f"{output_id}: manifest.json is not the '{output_id}' output plugin")
    module = _import_package(output_id)
    classes = [
        value
        for value in vars(module).values()
        if isinstance(value, type) and issubclass(value, OutputPluginBase) and value is not OutputPluginBase
    ]
    if len(classes) != 1:
        raise FirstPartyOutputError(f"{output_id}: the package must export one OutputPluginBase subclass")
    plugin_class = classes[0]
    if not plugin_class.plugin_id:
        plugin_class.plugin_id = manifest.id
    return FirstPartyOutput(plugin_class, manifest)


def _board_grid(board: dict) -> tuple[int, int] | None:
    rows, cols = board.get("grid_rows"), board.get("grid_cols")
    if isinstance(rows, int) and isinstance(cols, int) and rows > 0 and cols > 0:
        return rows, cols
    return None


def _builder(loaded: FirstPartyOutput) -> Callable[[dict], OutputDriver | None]:
    plugin_class, output_manifest = loaded.plugin_class, loaded.manifest.output

    def build(board: dict) -> OutputDriver | None:
        from .board_profile import board_character_set
        from .http import OutputHttp
        from .plugin_driver import OutputPluginDriver

        config = plugin_class.config_from_board(board)
        if config is None:
            return None
        instance = plugin_class(board.get("id"), config)
        # Core's choice, not the plugin's: the requests these outputs always made.
        instance._http = OutputHttp.for_first_party()
        instance.bind_manifest(output_manifest)
        # Only an output whose markup follows its set needs the set resolved
        # (a FiestaPanel's would read the panel store for its render style).
        character_set = board_character_set(board) if plugin_class.markup_follows_charset else None
        instance.bind_board(character_set=character_set, geometry=_board_grid(board))
        instance.open()
        return OutputPluginDriver(instance, character_set=character_set, first_party=True)

    return build


async def _vestaboard_dispatch(call: ActionCall) -> ActionOutcome:
    from .vestaboard.actions import dispatch

    return await dispatch(call)


async def _fiestapanel_dispatch(call: ActionCall) -> ActionOutcome:
    """A FiestaPanel draws in memory: there is no connection to fail."""
    return ActionOutcome(message="FiestaPanel boards render in FiestaBoard itself; there is nothing to connect to.")


#: Core's board-settings action runners for the first-party outputs (their
#: settings screens are still core's own until P4d).
_DISPATCH = {VESTABOARD: _vestaboard_dispatch, FIESTAPANEL: _fiestapanel_dispatch}


def _hooks(output_id: str, plugin_class: type[OutputPluginBase]) -> OutputHooks:
    discover = None
    if getattr(plugin_class.discover, "__func__", None) is not OutputPluginBase.discover.__func__:
        discover = plugin_class.discover
    diagnostics = None
    if hasattr(plugin_class, "diagnose_board"):
        diagnostics = OutputDiagnostics(
            run=plugin_class.diagnose_board,
            advise=plugin_class.diagnostics_advice,
            all_clear=plugin_class.DIAGNOSTICS_ALL_CLEAR,
        )
    actions = plugin_class.hook_actions() if hasattr(plugin_class, "hook_actions") else {}
    return OutputHooks(discover=discover, diagnostics=diagnostics, actions=actions, dispatch=_DISPATCH.get(output_id))


def first_party_definition(output_id: str) -> OutputDefinition:
    """The registry entry of first-party output *output_id*."""
    loaded = load_first_party(output_id)
    manifest = loaded.manifest
    output_manifest = manifest.output
    assert output_manifest is not None
    return OutputDefinition(
        id=manifest.id,
        name=manifest.name,
        capabilities=loaded.plugin_class.declared_capabilities(output_manifest),
        build=_builder(loaded),
        hooks=_hooks(output_id, loaded.plugin_class),
        description=manifest.description,
        icon=manifest.icon,
        actions=output_manifest.actions,
        offered_device_models=_LEGACY_OFFERED_MODELS.get(output_id, output_manifest.device_model_ids),
    )


def register_first_party_outputs(registry: OutputRegistry) -> None:
    """Register every first-party output. One that cannot load is logged and
    left out: its boards stay down with the reason recorded, never another
    output in its place."""
    for output_id in FIRST_PARTY_OUTPUTS:
        try:
            registry.register(first_party_definition(output_id))
        except Exception:
            logger.exception("First-party output %s could not be loaded; its boards cannot be driven", output_id)
