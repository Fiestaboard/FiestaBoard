"""Core per-board send policy, owned by the platform rather than the driver.

One :class:`OutputRuntime` exists per board. The display engine's
``BoardRuntime`` creates it and binds it to the board's client, which then
takes its send lock and cancel token from here instead of owning them.

It holds the **send lock**, the **cancel token**, the board's
:class:`~src.outputs.frames.FrameCache` (frame dedupe and the last-frame
store), **external-write detection** over it, and the door to the **send
floor** (:mod:`src.outputs.floor`), which is keyed by device rather than by
runtime so it outlives any one client. It also **drives transitions**
(:meth:`OutputRuntime.render`): native ones are forwarded to a driver that
declares them, ``plugin:<id>`` ones are run frame by frame by the board's
transition runner under the run's cancel token (:mod:`src.outputs.transitions`).

The contract, unchanged from when it lived in the old clients' ``TransitionRenderMixin``:

- **Preemption before the lock.** :meth:`run` signals the in-flight run's
  token *before* it waits on the lock, so a running transition winds down
  between frames instead of being waited out. :meth:`preempt` does the same
  without running anything; the engine calls it when it enqueues a newer
  frame, so a transition learns about it at once rather than when the
  board's worker dequeues the job.
- **A fresh token per run.** Each run installs a new ``Event`` under the
  lock. A signal meant for the previous run can never pre-cancel the next
  one, and the preempted run keeps its own reference to the old, signalled
  token, so its cancellation is never lost.
- **Re-entrant lock.** ``render()`` holds the lock around
  ``send_characters()``, which takes it again.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from src.send_outcome import SendOutcome

from .floor import Admission, send_floors
from .frames import FrameCache, Grid
from .registry import Delivery, capabilities_of
from .transitions import TRANSITION_PLUGIN_PREFIX, NativeTransition, transition_plugins_enabled

if TYPE_CHECKING:
    from .cells import RichCellFrame
    from .driver import OutputDriver

logger = logging.getLogger(__name__)


class _FrameSink:
    """What a transition runner sends through: the driver's plain send.

    Records each frame's throttle verdict as it lands, so the run's outcome is
    its *own* — a run preempted before its first frame reports what it did
    (nothing), never the previous call's flag. The runner paces frames by the
    driver's declared floor, read here.
    """

    def __init__(self, driver: OutputDriver, target: Grid | None = None, cells: RichCellFrame | None = None) -> None:
        self._driver = driver
        self._target = target
        self._cells = cells
        self.throttled = False
        self.retry_after: int | None = None

    @property
    def min_send_interval_ms(self) -> int:
        return int(self._driver.min_send_interval_ms or 0)

    def send_characters(self, characters: Grid, strategy: Any | None = None, force: bool = False) -> Any:
        # The run lands on its target: that frame carries the target's rich
        # cells, so a rich output ends on the coloured frame (plan D15).
        rich = {"cells": self._cells} if self._cells is not None and characters == self._target else {}
        result = self._driver.send_characters(characters, strategy=strategy, force=force, **rich)
        self.throttled = bool(self._driver.last_send_throttled)
        self.retry_after = self._driver.last_send_retry_after if self.throttled else None
        return result


def _floor_seconds(driver: OutputDriver) -> int | None:
    """The driver's declared floor in whole seconds, or ``None`` when unfloored."""
    floor_ms = int(driver.min_send_interval_ms or 0)
    return max(1, math.ceil(floor_ms / 1000)) if floor_ms > 0 else None


class OutputRuntime:
    """One board's send lock, cancel token, frame cache and write detector.

    Args:
        board_id: The board this runtime serves, for logs and identity.
            ``None`` for a client built outside the engine (a throwaway
            client in an API route), which gets a private runtime of its own.
        frames: The frame cache to start from; a fresh one by default.
        output_id: The board's output id, which answers :attr:`delivery`.
    """

    def __init__(
        self,
        board_id: str | None = None,
        *,
        frames: FrameCache | None = None,
        output_id: str | None = None,
    ) -> None:
        self.board_id = board_id
        # The registered output that drives this board (src/outputs/registry.py),
        # or None for a runtime built outside the engine (a draft driver's).
        self.output_id = output_id
        self._send_lock = threading.RLock()
        self._cancel = threading.Event()
        self._frames = frames if frames is not None else FrameCache()
        # Generation of the dedupe cache the previous read-back mismatched
        # against, or None. See observe_read().
        self._external_suspect: int | None = None
        # The TransitionRunner that drives "plugin:<id>" transitions on this
        # board, attached by the service layer. None: such a request snaps
        # to the target (logged).
        self.transition_runner: Any | None = None
        # Thread id of the run holding the send lock, so write() can tell a
        # run's own frames from a write arriving from elsewhere. Only ever
        # equal to a reader's own id if that reader set it, so the unlocked
        # read in write() is race-free.
        self._run_owner: int | None = None

    # --- frames ------------------------------------------------------------------

    @property
    def frames(self) -> FrameCache:
        """What the board shows (dedupe cache) and what was last sent (store)."""
        return self._frames

    def adopt_frames(self, frames: FrameCache) -> None:
        """Take over a driver's frame cache when the driver is bound here.

        The cache follows the driver exactly as it did when it was the
        driver's own attribute: binding a fresh client starts clean, and
        whatever the client recorded before the bind (a startup read-back)
        carries over.
        """
        self._frames = frames

    def displayed_frame(self, rows: int, cols: int) -> Grid | None:
        """What a pull viewer is served: the last frame sent, if it still has
        the board's shape (*rows* x *cols*); ``None`` otherwise. See
        :meth:`FrameCache.last_frame_shaped`."""
        return self._frames.last_frame_shaped(rows, cols)

    def displayed_cells(self, rows: int, cols: int) -> RichCellFrame | None:
        """The rich cells of :meth:`displayed_frame`, when that write carried
        them (an output that takes rich cells); ``None`` otherwise."""
        return self._frames.last_cells_shaped(rows, cols)

    def release_frames(self) -> None:
        """Drop the board's stored frames (panel deleted, or re-fit to a new grid)."""
        self._frames.clear()

    @property
    def delivery(self) -> Delivery | None:
        """The board's output's delivery (``"push"`` | ``"pull"``), from the
        output registry; ``None`` when the output is unknown.

        Callers that gate on it must fail closed: only a literal ``"pull"``
        means "no device is written".
        """
        capabilities = capabilities_of(self.output_id)
        return capabilities.delivery if capabilities is not None else None

    @property
    def last_frame(self) -> Grid | None:
        """The grid last sent to this board (survives a dedupe-cache clear)."""
        return self._frames.last_frame

    @property
    def last_sent_at(self) -> float | None:
        """When :attr:`last_frame` was sent, in epoch seconds."""
        return self._frames.last_sent_at

    # --- the send floor ----------------------------------------------------------

    def admit_send(
        self,
        device_key: str,
        floor_seconds: float,
        clock: Callable[[], float],
        is_unchanged: Callable[[], bool],
    ) -> Admission:
        """Floor, then dedupe, atomically; reserves the device's slot on "send".

        The floor is the device's (``device_key``), so it holds across client
        rebuilds and throwaway clients for the same board.
        """
        return send_floors().admit(device_key, floor_seconds, clock, is_unchanged)

    def release_send(self, admission: Admission) -> None:
        """The write failed: give the reserved slot back."""
        send_floors().release(admission)

    def hold_send(self, admission: Admission, floor_seconds: float, seconds: float) -> None:
        """The device asked to wait *seconds* (HTTP 429): keep it closed that long."""
        send_floors().hold(admission, floor_seconds, seconds)

    # --- external-write detection (#1946) ----------------------------------------

    @property
    def external_write_suspected(self) -> bool:
        """True after one read-back mismatched and no send has happened since."""
        return self._external_suspect is not None

    def observe_read(self, read: Callable[[], Grid | None]) -> tuple[Grid | None, bool]:
        """Read the board back and judge whether someone else wrote it.

        Returns ``(characters, external_write)``. ``characters`` is whatever
        *read* returned; ``external_write`` is True only on the **second**
        consecutive mismatch against the same, unchanged dedupe cache. One
        mismatch can be FiestaBoard's own send still propagating — the cloud
        read API lags a POST by seconds, and the cache is written only after
        the POST returns — while a genuine external write persists to the
        next poll. The cache's generation is read on both sides of the read,
        so any send (or cache sync or clear) in between restarts the cycle.

        A matching read never reports anything: it only proves the board
        shows FiestaBoard's last write, which may itself be out-of-band.
        """
        _, baseline = self._frames.snapshot()
        characters = read()
        if not characters:
            return characters, False
        current, generation = self._frames.snapshot()
        if current is None or generation != baseline:
            # No cache to judge against, or a send raced the read — whatever
            # was read proves nothing about external writers.
            self._external_suspect = None
            return characters, False
        if characters == current:
            self._external_suspect = None
            return characters, False
        if self._external_suspect == generation:
            # Second consecutive mismatch with no send in between.
            self._external_suspect = None
            return characters, True
        self._external_suspect = generation
        return characters, False

    @property
    def send_lock(self) -> threading.RLock:
        """The per-board lock serializing every device write."""
        return self._send_lock

    @property
    def cancel_event(self) -> threading.Event:
        """The current run's cancel token; send-retry backoffs wait on it."""
        return self._cancel

    @cancel_event.setter
    def cancel_event(self, event: threading.Event) -> None:
        # Replaces the current token. Only tests inject one directly; runs
        # install theirs through run().
        self._cancel = event

    def preempt(self) -> None:
        """Signal the current run to wind down. Never blocks."""
        self._cancel.set()

    @contextmanager
    def run(self) -> Iterator[threading.Event]:
        """Preempt the run in flight, take the lock, and yield a fresh token.

        The token is the one this run's transition runner watches; it is set
        when a later run (or :meth:`preempt`) supersedes this one.
        """
        self.preempt()
        with self._send_lock:
            token = threading.Event()
            self._cancel = token
            outer_owner = self._run_owner
            self._run_owner = threading.get_ident()
            try:
                yield token
            finally:
                self._run_owner = outer_owner

    @contextmanager
    def write(self) -> Iterator[threading.Event]:
        """Enter one device write: a run of its own, unless already inside one.

        A driver's plain ``send_characters`` enters here, so a direct write —
        a debug blank, an MQTT message, an identify flash — is a runtime
        write like any engine send: it preempts the in-flight transition and
        takes the send lock. A frame the run itself sends (a transition's
        frames, the snap, ``render()``'s own write) is already inside the run
        on this thread and only re-enters the lock; preempting there would
        cancel the very transition sending it.
        """
        if self._run_owner == threading.get_ident():
            with self._send_lock:
                yield self._cancel
        else:
            with self.run() as token:
                yield token

    # --- transitions ---------------------------------------------------------------

    def render(
        self,
        driver: OutputDriver,
        characters: Grid,
        *,
        strategy: str | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
        device_type: str | None = None,
        transition_config: dict | None = None,
        with_outcome: bool = False,
        plugins_enabled: Callable[[], bool] | None = None,
        on_run_start: Callable[[], None] | None = None,
        cells: RichCellFrame | None = None,
    ) -> Any:
        """Write *characters* to *driver*, driving the requested transition.

        One run (:meth:`run`): the in-flight run is preempted, the send lock
        held, and a fresh cancel token installed for the whole write.

        - No ``plugin:`` prefix: a :class:`NativeTransition`. Forwarded when
          the driver declares the strategy; dropped (a plain write) when the
          driver declares no native transitions; an unknown name is handed to
          the driver, which refuses it as it always has.
        - ``plugin:<id>``: when the beta flag is on, a runner is attached and
          the driver can animate, the runner drives the plugin's frames
          through the driver's plain send and lands on *characters*.
          Otherwise the write snaps to *characters*.

        Args:
            driver: The board's driver (bound to this runtime).
            plugins_enabled: The beta-flag check; the core one by default.
                Drivers pass their own patchable seam.
            on_run_start: Called under the lock once the run starts, before
                any write (the driver resets its last-call verdict).
            cells: The rich cells of *characters*, for an output that takes
                them (:mod:`src.outputs.cells`). They go with the write that
                lands on *characters*; a transition's intermediate frames
                stay 0–71 grids. Never forwarded when ``None``, so every
                other driver sees the call shape it always did.

        Returns:
            The driver's ``(success, was_sent)`` pair, or a
            :class:`~src.send_outcome.SendOutcome` when ``with_outcome``.
        """
        is_plugin = isinstance(strategy, str) and strategy.startswith(TRANSITION_PLUGIN_PREFIX)
        with self.run() as token:
            if on_run_start is not None:
                on_run_start()
            # Forward the keyword only when asked for, so every pre-existing
            # caller (and every test double asserting the call) sees exactly
            # the send_characters call shape it always did.
            outcome_kw: dict[str, Any] = {"with_outcome": True} if with_outcome else {}
            if cells is not None:
                outcome_kw["cells"] = cells

            if not is_plugin:
                native = self._native_for(driver, NativeTransition.of(strategy, step_interval_ms, step_size))
                return driver.send_characters(
                    characters,
                    strategy=native.strategy if native else None,
                    step_interval_ms=native.step_interval_ms if native else None,
                    step_size=native.step_size if native else None,
                    force=force,
                    **outcome_kw,
                )

            plugin_id = strategy[len(TRANSITION_PLUGIN_PREFIX) :].strip()
            if not plugin_id:
                logger.warning("render: empty transition plugin id in strategy %r; sending as-is", strategy)
                return driver.send_characters(characters, strategy=None, force=force, **outcome_kw)

            # Defense in depth: if the operator toggled the beta flag off after
            # pages were saved with a plugin: strategy, plugin code must not
            # run anyway -- the API surface is gated, and so is execution.
            if not (plugins_enabled or transition_plugins_enabled)():
                logger.warning(
                    "render: transition_plugins beta is off; plugin:%s ignored, snapping to target", plugin_id
                )
                return driver.send_characters(characters, strategy=None, force=force, **outcome_kw)

            runner = self.transition_runner
            if runner is None:
                logger.warning(
                    "render: no transition runner attached; plugin:%s ignored, snapping to target grid", plugin_id
                )
                return driver.send_characters(characters, strategy=None, force=force, **outcome_kw)

            if driver.animation == "none":
                logger.info("render: board %s cannot animate; plugin:%s snaps to target", self.board_id, plugin_id)
                return driver.send_characters(characters, strategy=None, force=force, **outcome_kw)

            # The animation starts from what the board is known to show — this
            # runtime's dedupe cache — read under the send lock, so no send can
            # move it between here and the runner's first frame.
            cached = self._frames.characters
            from_grid = cached if isinstance(cached, list) and cached else None

            # "sequence": the device takes the whole transition as one upload
            # (output plugins declare it; see plugin_driver.write_sequence).
            write_sequence = getattr(driver, "write_sequence", None)
            if driver.animation == "sequence" and write_sequence is not None:
                return self._render_sequence(
                    driver,
                    write_sequence,
                    runner,
                    plugin_id,
                    characters,
                    token,
                    device_type=device_type,
                    from_grid=from_grid,
                    config=transition_config,
                    with_outcome=with_outcome,
                )

            # "stream" (and a "sequence" driver with no upload): frames go
            # one write at a time.
            sink = _FrameSink(driver, characters, cells)
            success, was_sent = runner.run(
                plugin_id=plugin_id,
                to_grid=characters,
                board_client=sink,
                cancel_event=token,
                device_type=device_type,
                from_grid=from_grid,
                config=transition_config,
            )
            if not with_outcome:
                return (success, was_sent)
            # Still under the send lock: the verdict is this run's own frames'.
            return SendOutcome(
                success,
                was_sent,
                throttled=sink.throttled,
                retry_after_seconds=sink.retry_after if sink.throttled else None,
                floor_seconds=_floor_seconds(driver),
            )

    def _render_sequence(
        self,
        driver: OutputDriver,
        write_sequence: Callable[..., Any],
        runner: Any,
        plugin_id: str,
        characters: Grid,
        token: threading.Event,
        *,
        device_type: str | None,
        from_grid: Grid | None,
        config: dict | None,
        with_outcome: bool,
    ) -> Any:
        """A frame-driven transition as ONE timed upload to a sequence device."""
        from .plugin_base import TimedFrame

        collected = runner.collect_frames(
            plugin_id=plugin_id,
            to_grid=characters,
            cancel_event=token,
            device_type=device_type,
            from_grid=from_grid,
            config=config,
        )
        if collected is None:
            # Preempted while collecting: the newer frame has its own target.
            result = SendOutcome(True, False)
        else:
            frames = [TimedFrame(grid, duration) for grid, duration in collected]
            result = SendOutcome.of(write_sequence(frames, cancel=token))
        if not with_outcome:
            return (result.success, result.was_sent)
        return result._replace(floor_seconds=_floor_seconds(driver))

    @staticmethod
    def _native_for(driver: OutputDriver, native: NativeTransition | None) -> NativeTransition | None:
        """The native transition *driver* gets: as asked, or none at all."""
        if native is None or not native.is_known:
            # Nothing asked; or a name no device offers, which the driver
            # refuses (and logs) exactly as it always has.
            return native
        if native.supported_by(driver.native_transitions):
            return native
        logger.debug("%r is not supported by this board and is ignored", native)
        return None
