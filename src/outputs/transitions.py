"""Transitions, as core understands them.

A write can ask for a transition in one of two ways, and core — the board's
:class:`~src.outputs.runtime.OutputRuntime` — decides which happens:

- **Native**: the device animates itself (a Vestaboard on its Local API
  takes ``strategy`` / ``step_interval_ms`` / ``step_size`` in the payload).
  Expressed as a :class:`NativeTransition` and forwarded only to a driver
  that declares the strategy in ``native_transitions``. A driver that
  declares none (RW Cloud, note-array Cloud, a virtual board) gets a plain
  write — exactly as those drivers always ignored the parameters.
- **Frame-driven**: ``"plugin:<id>"`` asks a transition plugin to generate
  intermediate frames, which core sends one at a time through the driver's
  plain send (:class:`~src.transitions.TransitionRunner`), honoring the run's
  cancel token. Gated by the ``transition_plugins`` beta flag and by the
  driver's declared :data:`Animation` capability.

Animation capability (plan D3, mirrors FiestaUI ``DeviceModel.animation``):

- ``"stream"`` — the device takes frames one write at a time; core paces
  them. A local Vestaboard, a FiestaPanel.
- ``"sequence"`` — the device takes a whole timed sequence in one upload
  (``write_sequence``, e.g. a Divoom Pixoo). Not implemented yet: no driver
  declares it, and the runtime branches on it when one does.
- ``"none"`` — the device cannot show intermediate frames (a cloud Vestaboard:
  one message per 15 s); a frame-driven transition snaps straight to the
  target.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

#: Sentinel prefix on a strategy string that asks for a transition plugin
#: instead of a device-native strategy.
TRANSITION_PLUGIN_PREFIX = "plugin:"

#: Every native strategy name FiestaBoard knows — Vestaboard's built-ins, the
#: only native transitions any device offers today. A name outside this set is
#: not a transition request core can route; it is handed to the driver, which
#: refuses it (as every driver always has). A driver declares the subset it
#: animates in ``native_transitions``.
NATIVE_STRATEGIES: frozenset[str] = frozenset(
    {"column", "reverse-column", "edges-to-center", "row", "diagonal", "random"}
)

#: The same names in the order the menus (MQTT's transition select, the
#: settings' strategy list) offer them: the Vestaboard Local API's own order.
VALID_STRATEGIES: list[str] = ["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"]

#: How a device shows a frame-driven transition (see the module docstring).
Animation = Literal["stream", "sequence", "none"]


@dataclass(frozen=True)
class NativeTransition:
    """A device-native transition request: the device animates the change.

    Any field may be ``None`` (the device's default). A request with every
    field ``None`` is no request at all — :meth:`of` returns ``None`` for it.
    """

    strategy: str | None
    step_interval_ms: int | None = None
    step_size: int | None = None

    @classmethod
    def of(cls, strategy: str | None, step_interval_ms: int | None, step_size: int | None) -> NativeTransition | None:
        """The request a write's legacy keyword arguments make, or ``None``."""
        if strategy is None and step_interval_ms is None and step_size is None:
            return None
        return cls(strategy, step_interval_ms, step_size)

    @property
    def is_known(self) -> bool:
        """True unless it names a strategy no device offers."""
        return self.strategy is None or self.strategy in NATIVE_STRATEGIES

    def supported_by(self, native_transitions: frozenset[str]) -> bool:
        """True when a driver declaring *native_transitions* animates this.

        A request that names no strategy (step parameters alone) goes to any
        driver that has native transitions at all, as it always did.
        """
        if not native_transitions:
            return False
        return self.strategy is None or self.strategy in native_transitions


def driver_runs_strategy(driver, strategy: str) -> bool:
    """Whether *driver* runs *strategy* as a transition, by the rule its
    write path applies — the one predicate a page's override is judged by.

    - A driver that takes LED transitions (an output plugin's
      ``takes_transitions``) runs LED menu ids; anything else falls back to
      its model's default (``OutputPluginDriver.resolve_transition``).
    - ``plugin:<id>``: when the driver takes frames (``animation`` is not
      ``"none"``), as :meth:`OutputRuntime.render` requires.
    - A split-flap strategy: when the driver declares it
      (:meth:`NativeTransition.supported_by`, as the runtime forwards it).
    - Anything else (an LED id on a split-flap, a typo) is no transition.

    A driver that does not say (no ``native_transitions`` set, e.g. a test
    double) runs whatever it is asked, as before.
    """
    from src.led.transition_registry import is_led_transition_id

    natives = getattr(driver, "native_transitions", None)
    if not isinstance(natives, set | frozenset):
        return True
    if getattr(driver, "takes_transitions", False) is True:
        return strategy not in NATIVE_STRATEGIES and is_led_transition_id(strategy)
    if strategy.startswith(TRANSITION_PLUGIN_PREFIX):
        return getattr(driver, "animation", "none") != "none"
    if strategy in NATIVE_STRATEGIES:
        return NativeTransition.of(strategy, None, None).supported_by(natives)
    return False


def transition_plugins_enabled() -> bool:
    """Whether the ``transition_plugins`` beta flag is on.

    Imported lazily so the outputs package has no hard dependency on the
    settings layer. Failures read as *off*: if settings can't be reached,
    a snap to the target is safer than executing experimental code.
    """
    try:
        from src.settings.service import get_settings_service

        return bool(get_settings_service().get_plugin_settings().transition_plugins_enabled)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("render: could not read transition_plugins beta flag: %s", exc)
        return False
