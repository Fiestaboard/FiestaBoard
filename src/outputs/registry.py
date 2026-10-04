"""The output registry: every kind of device FiestaBoard can drive, by id.

A saved board names the **output** that drives it. Two are built in and
registered here, in-tree, until output plugins exist (plan Phase 2):

- ``vestaboard`` — a Vestaboard on the Local API, the RW Cloud API, the
  note-array Cloud API, or a local note array's per-tile fan-out.
- ``fiestapanel`` — a FiestaPanel TV: an in-memory board that viewers pull
  frames from.

Each entry carries the output's **capabilities** — what core decides by,
without building a driver: ``technology``, ``delivery``, ``animation`` and
``native_transitions`` (plan D3; the vocabulary mirrors FiestaUI's
``DeviceModel``). They describe the *output*: the most it can offer in any
configuration. A driver narrows them for its own connection (a cloud
Vestaboard animates no native transition), and the driver's answer is the
one core uses at write time. Device models and character sets arrive with
output plugins; nothing here invents them.

Each entry also carries the output's **hooks** (:mod:`src.outputs.hooks`):
what core asks the output instead of knowing its device — ``discover``,
``diagnostics`` and named custom ``actions``. The ``vestaboard`` hooks live in
:mod:`src.outputs.vestaboard`; ``fiestapanel`` declares none.

Which output a board uses is **derived at load** — no settings field is
written for an existing board (the v4 settings migration persists it later,
plan D8). One precedence rule, :func:`resolve_output_id`:

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
from typing import TYPE_CHECKING, Literal

from .hooks import OutputDiagnostics, OutputHooks, UnknownOutputAction
from .transitions import NATIVE_STRATEGIES, Animation

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


def discover_devices(output_id: str, timeout: float) -> list[dict]:
    """Run *output_id*'s ``discover`` hook; ``[]`` when it declares none.

    Raises:
        UnknownOutputError: *output_id* is not registered.
    """
    definition = output_registry().get(output_id)
    if definition is None:
        raise UnknownOutputError(output_id)
    hook = definition.hooks.discover
    return hook(timeout) if hook is not None else []


def diagnostics_for(board: Mapping) -> OutputDiagnostics | None:
    """The diagnostics hook of the output that drives *board*, or ``None``
    when that output declares none (or is not installed)."""
    definition = output_registry().get(resolve_output_id(board))
    return definition.hooks.diagnostics if definition is not None else None


def output_action(output_id: str, action: str) -> Callable[..., object]:
    """The custom action *action* of output *output_id*.

    Raises:
        UnknownOutputError: *output_id* is not registered.
        UnknownOutputAction: the output has no action by that name.
    """
    definition = output_registry().get(output_id)
    if definition is None:
        raise UnknownOutputError(output_id)
    fn = definition.hooks.actions.get(action)
    if fn is None:
        raise UnknownOutputAction(output_id, action)
    return fn


# --- the built-ins ---------------------------------------------------------------
#
# Builders and hooks import their modules lazily: the client modules import
# this package, and the Vestaboard hooks pull in the HTTP and host-guard
# stacks, which nothing needs until a hook actually runs.


def _build_vestaboard(board: dict) -> OutputDriver | None:
    from src.board_client import build_vestaboard_driver

    return build_vestaboard_driver(board)


def _vestaboard_hooks() -> OutputHooks:
    def discover(timeout: float) -> list[dict]:
        from .vestaboard.discovery import discover as _discover

        return _discover(timeout)

    def run_diagnostics(board: Mapping) -> dict:
        from .vestaboard.diagnostics import diagnose

        return diagnose(board)

    def advise(section: Mapping) -> list[dict]:
        from .vestaboard.diagnostics import advise as _advise

        return _advise(section)

    async def enable_local_api(request: object) -> dict:
        from .vestaboard.local_api import exchange_enablement_token

        return await exchange_enablement_token(request)

    from .vestaboard import ALL_CLEAR_SUMMARY

    return OutputHooks(
        discover=discover,
        diagnostics=OutputDiagnostics(run=run_diagnostics, advise=advise, all_clear=ALL_CLEAR_SUMMARY),
        actions={"enable_local_api": enable_local_api},
    )


def _build_fiestapanel(board: dict) -> OutputDriver | None:
    from src.virtual_board_client import build_fiestapanel_driver

    return build_fiestapanel_driver(board)


def _builtin_registry() -> OutputRegistry:
    registry = OutputRegistry()
    registry.register(
        OutputDefinition(
            id=VESTABOARD,
            name="Vestaboard",
            capabilities=OutputCapabilities(
                technology="split_flap",
                delivery="push",
                animation="stream",
                # The Local API animates every native strategy; the cloud
                # APIs declare none (the driver narrows per connection).
                native_transitions=NATIVE_STRATEGIES,
            ),
            build=_build_vestaboard,
            hooks=_vestaboard_hooks(),
        )
    )
    registry.register(
        OutputDefinition(
            id=FIESTAPANEL,
            name="FiestaPanel",
            capabilities=OutputCapabilities(
                technology="screen",
                delivery="pull",
                # Frames are stored one at a time; the viewer animates the
                # change itself, so no native strategy is declared.
                animation="stream",
                native_transitions=frozenset(),
            ),
            build=_build_fiestapanel,
        )
    )
    return registry


_registry = _builtin_registry()


def output_registry() -> OutputRegistry:
    """The process-wide registry, built-ins registered."""
    return _registry
