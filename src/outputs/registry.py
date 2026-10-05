"""The output registry: every kind of device FiestaBoard can drive, by id.

A saved board names the **output** that drives it. Two are first-party and
always registered — output plugins in their own repositories, carried by
the image's output seed and loaded from it by :mod:`src.outputs.first_party`
the first time the registry is asked for:

- ``vestaboard`` — a Vestaboard on the Local API, the RW Cloud API, the
  note-array Cloud API, or a local note array's per-tile fan-out.
- ``fiestapanel`` — a FiestaPanel TV: an in-memory board that viewers pull
  frames from.

Third-party output **plugins** register beside them as the plugin loader
loads them (:mod:`src.outputs.plugin_registration`); a plugin can never take
a first-party output's id (their entries are ``plugin=False``).

Each entry carries the output's **capabilities** — what core decides by,
without building a driver: ``technology``, ``delivery``, ``animation`` and
``native_transitions`` (plan D3; the vocabulary mirrors FiestaUI's
``DeviceModel``). They describe the *output*: the most it can offer in any
configuration. A driver narrows them for its own connection (a cloud
Vestaboard animates no native transition), and the driver's answer is the
one core uses at write time. Device models and character sets arrive with
output plugins; nothing here invents them.

Each entry also carries the output's **hooks** (:mod:`src.outputs.hooks`):
what core asks the output instead of knowing its device — ``discover`` and
``diagnostics`` — and its plugin class, which answers everything about a
board's settings (actions, status, ``output_config``). The ``vestaboard``
hooks are its plugin's (``Fiestaboard/fiestaboard-output--vestaboard``);
``fiestapanel`` declares none.

Which output a board uses is **stored** since settings v4 (plan D8): the
v3 -> v4 migration wrote it for every existing board by the same precedence
rule this module applies to any dict that does not name one (a draft, a
legacy flat write), :func:`resolve_output_id`:

1. an explicit ``output`` key wins;
2. ``api_mode == "virtual"`` is a FiestaPanel (this covers legacy virtual
   note-array panels, which predate the ``panel`` device type);
3. everything else is a Vestaboard.

An explicit id the registry does not know builds **no** driver: the board
stays down with the reason recorded. It is never coerced to a Vestaboard —
a board that is not a Vestaboard must never silently become one.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from .hooks import (
    OutputActionSpec,
    OutputDiagnostics,
    OutputHooks,
    ReadBack,
    call_discover,
    lan_hint,
)
from .transitions import Animation

if TYPE_CHECKING:
    from .driver import OutputDriver

logger = logging.getLogger(__name__)

#: What a device is made of (FiestaUI ``DeviceModel.technology``, plus
#: ``screen`` for a display that draws whatever its viewer renders).
Technology = Literal["split_flap", "led_matrix", "screen"]

#: Who moves a frame: core writes it to the device (``push``), or the
#: device's viewer fetches it from core's last-frame store (``pull``).
Delivery = Literal["push", "pull"]

VESTABOARD = "vestaboard"
FIESTAPANEL = "fiestapanel"
#: The outputs core itself loads, from the seed (:mod:`src.outputs.first_party`).
FIRST_PARTY_OUTPUTS: tuple[str, ...] = (VESTABOARD, FIESTAPANEL)


class UnknownOutputError(ValueError):
    """A board names an output this install does not have."""

    def __init__(self, output_id: str) -> None:
        super().__init__(f"Board output '{output_id}' is not installed")
        self.output_id = output_id


@dataclass(frozen=True)
class OutputCapabilities:
    """What core may assume about every board an output drives."""

    technology: Technology
    delivery: Delivery
    animation: Animation
    native_transitions: frozenset[str]
    # What output plugins add (src/outputs/output_manifest.py); the built-ins
    # leave them at their defaults, which is what their drivers report.
    #: The device's send floor in milliseconds (0 = unfloored).
    min_interval_ms: int = 0
    #: Whether and how cheaply core may read the device back; None = never.
    read_back: ReadBack | None = None
    #: FiestaUI DeviceModel ids the output declares (first = its default).
    device_models: tuple[str, ...] = ()
    #: The character set the output draws (a FiestaUI id), when declared.
    charset: str | None = None
    #: The frame budget of a ``sequence`` upload, when the model declares one.
    max_frames: int | None = None
    #: How long core waits for one write, when the output lowers the default
    #: (src/outputs/breaker.py); None = the default. Output plugins only.
    write_timeout_ms: int | None = None


@dataclass(frozen=True)
class OutputDefinition:
    """One registered output.

    ``build`` turns a saved (or draft) board dict into its driver, or
    ``None`` when the board has no usable connection. Only the runtime
    factory (:mod:`src.outputs.factory`) calls it. ``hooks`` are the
    output-level questions core asks (:class:`~src.outputs.hooks.OutputHooks`).
    """

    id: str
    name: str
    capabilities: OutputCapabilities
    build: Callable[[dict], OutputDriver | None]
    hooks: OutputHooks = field(default_factory=OutputHooks)
    #: True for an output plugin (src/outputs/plugin_registration.py); the
    #: first-party outputs are False and can never be replaced or removed.
    plugin: bool = False
    #: JSON Schema of each board's ``output_config`` (output plugins only).
    settings_schema: Mapping = field(default_factory=dict)
    #: The parsed manifest ``output`` block (an ``OutputManifest``: device
    #: models, character set), for output plugins; None for the built-ins.
    output_manifest: Any = None
    #: True for an output plugin usable only behind the output-plugins beta.
    beta_gated: bool = False
    #: One line for the "add a board" cards (the plugin manifest's description).
    description: str = ""
    #: A Lucide icon name for the same cards.
    icon: str | None = None
    #: The board settings screen's actions (plan D13): a plugin's manifest
    #: ``output.actions``; the built-ins' are declared below.
    actions: tuple[OutputActionSpec, ...] = ()
    #: Device models to offer when adding a board: the plugin's declared
    #: models (``capabilities.device_models``), or the built-ins' own below.
    offered_device_models: tuple[str, ...] = ()
    #: The output's ``OutputPluginBase`` subclass: what core asks about a
    #: board's settings (``handle_action``, ``board_status``, the
    #: ``output_config`` hooks; :mod:`src.outputs.config_hooks`). None only
    #: for a test's stand-in entry.
    plugin_class: Any = None


class OutputRegistry:
    """Outputs by id. Registering an id twice is refused."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._outputs: dict[str, OutputDefinition] = {}

    def register(self, definition: OutputDefinition) -> None:
        with self._lock:
            if definition.id in self._outputs:
                raise ValueError(f"Output '{definition.id}' is already registered")
            self._outputs[definition.id] = definition

    def put_plugin(self, definition: OutputDefinition) -> None:
        """Register an output plugin, replacing an earlier load of the same plugin.

        Refused for an id a built-in holds: a plugin never stands in for a
        Vestaboard or a FiestaPanel.
        """
        with self._lock:
            existing = self._outputs.get(definition.id)
            if existing is not None and not existing.plugin:
                raise ValueError(f"Output '{definition.id}' is built in; a plugin cannot replace it")
            self._outputs[definition.id] = definition

    def remove_plugin(self, output_id: str) -> None:
        """Forget an output plugin (unloaded or uninstalled). Built-ins stay."""
        with self._lock:
            existing = self._outputs.get(output_id)
            if existing is not None and existing.plugin:
                del self._outputs[output_id]

    def get(self, output_id: str | None) -> OutputDefinition | None:
        """The output registered under *output_id*, or ``None``."""
        if not output_id:
            return None
        with self._lock:
            return self._outputs.get(output_id)

    def ids(self) -> list[str]:
        with self._lock:
            return sorted(self._outputs)


def resolve_output_id(board: Mapping) -> str:
    """The output id that drives *board* — the precedence rule above.

    Returns an explicit id as given, known or not: whether it is installed
    is the caller's question (:func:`definition_for`).
    """
    explicit = board.get("output")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if (board.get("api_mode") or "").lower() == "virtual":
        return FIESTAPANEL
    return VESTABOARD


def definition_for(board: Mapping) -> OutputDefinition:
    """The registered output for *board*.

    Raises:
        UnknownOutputError: the board names an output that is not registered.
    """
    output_id = resolve_output_id(board)
    definition = output_registry().get(output_id)
    if definition is None:
        logger.error("Board %s names unknown output %r - no driver built", board.get("id") or "(draft)", output_id)
        raise UnknownOutputError(output_id)
    return definition


def capabilities_of(output_id: str | None) -> OutputCapabilities | None:
    """The capabilities of a registered output, or ``None`` when unknown."""
    definition = output_registry().get(output_id)
    return definition.capabilities if definition is not None else None


def output_name_for(board: Mapping) -> str:
    """The display name of the output that drives *board* (``"Vestaboard"``,
    ``"FiestaPanel"``), or its bare id when that output is not installed."""
    output_id = resolve_output_id(board)
    definition = output_registry().get(output_id)
    return definition.name if definition is not None else output_id


def discover_devices(output_id: str, timeout: float, hint: str | None = None) -> list[dict]:
    """Run *output_id*'s ``discover`` hook; ``[]`` when it declares none.
    *hint* (the browser's private IPv4 address; anything else is dropped)
    reaches a hook that takes one (:func:`~src.outputs.hooks.call_discover`).

    Raises:
        UnknownOutputError: *output_id* is not registered.
    """
    definition = output_registry().get(output_id)
    if definition is None:
        raise UnknownOutputError(output_id)
    hook = definition.hooks.discover
    return call_discover(hook, timeout, lan_hint(hint)) if hook is not None else []


def diagnostics_for(board: Mapping) -> OutputDiagnostics | None:
    """The diagnostics hook of the output that drives *board*, or ``None``
    when that output declares none (or is not installed)."""
    definition = output_registry().get(resolve_output_id(board))
    return definition.hooks.diagnostics if definition is not None else None


# --- the first-party outputs ----------------------------------------------------------
#
# Vestaboard and FiestaPanel are output plugins loaded from the output seed,
# registered on first use by src/outputs/first_party.py:
# loading them imports the plugin author API, which imports this module, so
# they cannot be registered while it is still being imported.

_registry = OutputRegistry()
# The process registry the first-party outputs are loaded into — the
# original object, even if a test has swapped ``_registry`` for a fake.
_first_party_home = _registry
_first_party_lock = threading.RLock()
_first_party_state = "unloaded"


def _load_first_party() -> None:
    global _first_party_state
    with _first_party_lock:
        if _first_party_state != "unloaded":
            # Loaded — or being loaded by this very thread (the RLock let it
            # in): the registry as it stands.
            return
        _first_party_state = "loading"
        try:
            from .first_party import register_first_party_outputs

            register_first_party_outputs(_first_party_home)
        finally:
            _first_party_state = "loaded"


def output_registry() -> OutputRegistry:
    """The process-wide registry, the first-party outputs registered."""
    if _first_party_state != "loaded":
        _load_first_party()
    return _registry
