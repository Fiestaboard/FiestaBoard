"""The adapter that lets core drive an output plugin like any other board.

:class:`OutputPluginDriver` wraps one :class:`~src.outputs.plugin_base.OutputPluginBase`
instance and satisfies the :class:`~src.outputs.driver.OutputDriver`
Protocol, so the board's :class:`~src.outputs.runtime.OutputRuntime` drives
it unchanged — the plugin is a pipe and every policy stays in core:

- **Lock and preemption.** Each write enters ``runtime.write()``: a direct
  write preempts the in-flight transition and takes the board's send lock;
  a transition's own frames re-enter it.
- **Cancel.** The run's token reaches the plugin as a
  :class:`~src.outputs.plugin_base.CancelToken`.
- **Floor.** Admission is core's (:mod:`src.outputs.floor`), keyed by the
  plugin's ``device_key()`` and spaced by its declared ``min_interval_ms``.
- **Dedupe and last-frame store.** An unchanged frame is acknowledged
  without calling the plugin; a frame that landed is recorded in the
  runtime's :class:`~src.outputs.frames.FrameCache`. For a plugin that
  takes rich cells (:attr:`OutputPluginDriver.takes_cells`) the frame's
  cells go to ``write_cells`` and the comparison is colour-aware.
- **Native transitions.** Forwarded as a
  :class:`~src.outputs.transitions.NativeTransition` only when the plugin
  declares the strategy (the runtime decides; the adapter carries it).
- **Sequences.** For ``animation: sequence`` outputs the runtime collects a
  transition's frames and hands them to :meth:`write_sequence` as one upload.
- **LED transitions.** A plugin that overrides ``write_transition``
  (:attr:`OutputPluginDriver.takes_transitions`) gets every change of what
  its board shows as before/after rich frames plus the board's resolved
  LED transition (:meth:`OutputPluginDriver.render`); the transition
  plugins and native strategies of split-flap boards do not apply to it.
- **The device helper.** Each write runs inside the plugin's
  ``http.cancel_scope``, so ``self.http`` refuses requests once the run is
  cancelled even when the plugin does not pass the token itself.

A plugin exception is a failed write (logged with the plugin id), never an
engine crash; the floor slot it reserved is given back. A write the device
refused for rate (``throttled`` in the plugin's result, an HTTP 429) keeps
the slot closed for the ``retry_after_seconds`` the device asked for.

**Third-party safety** (:mod:`src.outputs.breaker`). Each write runs under a
budget — 30 s by default, lowered by the manifest's ``write_timeout_ms`` —
after which core stops waiting, marks it failed and fires the run's cancel
token. Consecutive failed writes open the device's circuit breaker for a
cool-down, during which writes are refused without calling the plugin.
:attr:`OutputPluginDriver.last_write_error` says why the last write failed,
and the engine puts it in the board's send error.

**First-party outputs** (``first_party=True``: the Vestaboard and FiestaPanel
packages core seeds, :mod:`src.outputs.first_party`) are core's own code
under review, and their boards must behave exactly as they did before they
were plugins: their writes run inline on the caller's thread, with no
budget, no breaker and no ``last_write_error`` — the transport bounds itself
with its own timeouts, as it always did.
"""

from __future__ import annotations

import logging
import math
import threading
import time as _time_module
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.led.charsets import CharacterSet, has_extended_markup
from src.led.transition_registry import LED_TRANSITIONS, ResolvedLedTransition, resolve_led_transition
from src.send_outcome import WriteResult

from .breaker import DEFAULT_WRITE_TIMEOUT_MS, output_breakers
from .hooks import ConnectionCheck, ReadBack
from .plugin_base import CancelToken, OutputPluginBase, TimedFrame
from .runtime import OutputRuntime
from .transitions import NATIVE_STRATEGIES, NativeTransition, transition_plugins_enabled

if TYPE_CHECKING:
    from .cells import RichCellFrame
    from .floor import Admission
    from .frames import FrameCache
    from .registry import OutputCapabilities
    from .transitions import Animation

logger = logging.getLogger(__name__)

#: What a board reports when its output declares no read-back.
_NO_READ_BACK = ReadBack(supported=False, cost="cheap", suggested_interval_s=30)


def compress_sequence(frames: list[TimedFrame], max_frames: int | None) -> list[TimedFrame]:
    """*frames* within the device's frame budget: compressed, never cut.

    Evenly spaced frames are kept, first and last included, so the upload
    still starts where the transition starts and always lands on the target.
    """
    if not max_frames or len(frames) <= max_frames:
        return list(frames)
    if max_frames == 1:
        return [frames[-1]]
    last = len(frames) - 1
    picks = sorted({round(i * last / (max_frames - 1)) for i in range(max_frames)})
    return [frames[i] for i in picks]


class OutputPluginDriver:
    """One board's output-plugin instance, as core's :class:`OutputDriver`."""

    def __init__(
        self,
        plugin: OutputPluginBase,
        *,
        clock: Callable[[], float] | None = None,
        character_set: CharacterSet | None = None,
        first_party: bool = False,
    ) -> None:
        self.plugin = plugin
        #: The whole character set the board resolved to (plan D17), or None
        #: — always None for an output whose markup does not follow its set.
        self.character_set = character_set if type(plugin).markup_follows_charset else None
        self.skip_unchanged = True
        #: A first-party output: inline writes, no budget, no breaker.
        self.first_party = first_party
        # Read at construction from this module's clock, so a test can swap
        # ``src.outputs.plugin_driver._time_module`` for a fake one.
        self._clock = clock if clock is not None else _time_module.monotonic
        self._output_runtime = OutputRuntime()
        self._last_send_throttled = False
        self._last_send_retry_after: int | None = None
        self._closed = False
        #: Why the last write failed (raised, timed out, refused by the
        #: breaker, or reported failed); ``None`` after a write that landed.
        self.last_write_error: str | None = None

    # --- what core reads -------------------------------------------------------------

    @property
    def capabilities(self) -> OutputCapabilities:
        return self.plugin.capabilities()

    @property
    def use_cloud(self) -> bool:
        return self.read_back.cost == "network"

    @property
    def is_virtual(self) -> bool:
        return self.capabilities.delivery == "pull"

    @property
    def last_send_throttled(self) -> bool:
        return self._last_send_throttled

    @property
    def last_send_retry_after(self) -> int | None:
        return self._last_send_retry_after

    @property
    def min_send_interval_ms(self) -> int:
        return int(self.capabilities.min_interval_ms or 0)

    @property
    def native_transitions(self) -> frozenset[str]:
        return frozenset(self.capabilities.native_transitions)

    @property
    def animation(self) -> Animation:
        return self.capabilities.animation

    @property
    def read_back(self) -> ReadBack:
        return self.capabilities.read_back or _NO_READ_BACK

    @property
    def connection_label(self) -> str:
        return self.plugin.connection_label()

    def device_key(self) -> str:
        return self.plugin.device_key()

    @property
    def extended_markup(self) -> bool:
        """Whether this board's set is rich (colour/block spans or icons):
        its content is rendered and parsed with extended markup (plan D19)."""
        return has_extended_markup(self.character_set)

    @property
    def takes_cells(self) -> bool:
        """Whether rich frames reach the plugin: its set is rich and it
        overrides :meth:`~OutputPluginBase.write_cells` (the opt-in)."""
        return self.extended_markup and type(self.plugin).write_cells is not OutputPluginBase.write_cells

    @property
    def takes_transitions(self) -> bool:
        """Whether changes reach the plugin as LED transitions: it overrides
        :meth:`~OutputPluginBase.write_transition` (the opt-in) and its
        board has a device model to resolve the transition against."""
        if type(self.plugin).write_transition is OutputPluginBase.write_transition:
            return False
        model = self.plugin.device_model
        return model is not None and isinstance(model.get("animation"), dict)

    def resolve_transition(self, strategy: Any | None) -> ResolvedLedTransition:
        """The board's LED transition for a write asking for *strategy*.

        A strategy naming an LED transition (``"flip"``, ``"fade"``,
        ``"none"``... FiestaUI's menu ids) is the explicit choice; anything
        else — no strategy, a split-flap native one, a ``plugin:`` one —
        leaves the device model's default. :func:`resolve_led_transition`
        then fits it to the device (or falls back with a reason).
        """
        choice = strategy if isinstance(strategy, str) and strategy in LED_TRANSITIONS else None
        return resolve_led_transition(choice, self.plugin.device_model)

    @property
    def write_timeout_seconds(self) -> float:
        """How long core waits for one write: the output's budget, never
        above :data:`~src.outputs.breaker.DEFAULT_WRITE_TIMEOUT_MS`."""
        declared = self.capabilities.write_timeout_ms
        if not isinstance(declared, int) or isinstance(declared, bool) or declared <= 0:
            declared = DEFAULT_WRITE_TIMEOUT_MS
        return min(declared, DEFAULT_WRITE_TIMEOUT_MS) / 1000.0

    # --- binding -----------------------------------------------------------------------

    def set_output_runtime(self, runtime: OutputRuntime) -> None:
        runtime.adopt_frames(self._output_runtime.frames)
        if self._output_runtime.transition_runner is not None:
            runtime.transition_runner = self._output_runtime.transition_runner
        self._output_runtime = runtime

    def set_transition_runner(self, runner: Any | None) -> None:
        self._output_runtime.transition_runner = runner

    @property
    def _frames(self) -> FrameCache:
        return self._output_runtime.frames

    # --- writes --------------------------------------------------------------------------

    def _floor_seconds(self) -> int | None:
        floor_ms = self.min_send_interval_ms
        return max(1, math.ceil(floor_ms / 1000)) if floor_ms > 0 else None

    def _result(self, result: WriteResult, with_outcome: bool) -> Any:
        if not with_outcome:
            return (result.success, result.was_sent)
        return result._replace(floor_seconds=self._floor_seconds())

    def _admit(self, is_unchanged: Callable[[], bool]) -> Admission:
        self._last_send_throttled = False
        self._last_send_retry_after = None
        admission = self._output_runtime.admit_send(
            self.device_key(), self.min_send_interval_ms / 1000.0, self._clock, is_unchanged
        )
        if admission.verdict == "throttled":
            self._last_send_throttled = True
            self._last_send_retry_after = admission.retry_after
        return admission

    # --- third-party safety: breaker and timeout ------------------------------------

    def _breaker_key(self) -> str:
        return f"{self.connection_label}|{self.device_key()}"

    def _breaker_refusal(self, admission: Admission) -> WriteResult | None:
        """A failed result when the device's breaker is open, else ``None``.

        The refused write gives its floor slot back: nothing reached the device.
        """
        if self.first_party:
            return None
        breakers = output_breakers()
        streak = breakers.refusal(self._breaker_key(), self._clock())
        if streak is None:
            return None
        self._output_runtime.release_send(admission)
        self.last_write_error = (
            f"Output {self.connection_label} stopped after {streak.failures} failed writes in a row; "
            f"retrying in {breakers.cooldown_seconds:.0f}s. Last failure: {streak.last_failure}"
        )
        return WriteResult(False, False)

    def _write_failed(self, reason: str) -> None:
        if self.first_party:
            return
        self.last_write_error = f"Output {self.connection_label}: {reason}"
        output_breakers().record_failure(self._breaker_key(), reason, self._clock())

    def _run_bounded(self, call: Callable[[CancelToken], Any]) -> tuple[bool, Any]:
        """Run the plugin's call on a thread of its own and wait out its budget.

        Returns ``(True, result)`` when it finished (re-raising what it
        raised), ``(False, None)`` when the budget ran out: the run's cancel
        token is fired and nothing waits for the thread any longer.
        """
        cancel_event = self._output_runtime.cancel_event
        token = CancelToken(cancel_event)
        http = self.plugin.http
        if self.first_party:
            with http.cancel_scope(token):
                return True, call(token)
        box: dict[str, Any] = {}
        done = threading.Event()

        def run() -> None:
            try:
                with http.cancel_scope(token):
                    box["result"] = call(token)
            except BaseException as exc:  # handed back to the waiting caller
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=run, name=f"output-write-{self.connection_label}", daemon=True).start()
        if not done.wait(self.write_timeout_seconds):
            cancel_event.set()
            return False, None
        if "error" in box:
            raise box["error"]
        return True, box["result"]

    def _deliver(
        self,
        admission: Admission,
        final: list[list[int]],
        call: Callable[[CancelToken], Any],
        cells: RichCellFrame | None = None,
    ) -> WriteResult:
        """Run the plugin's write under the run's token and its budget; settle
        floor, frame cache and breaker."""
        try:
            finished, raw = self._run_bounded(call)
            result = WriteResult.of(raw) if finished else None
        except Exception as exc:
            if self.first_party:
                # Core's own code: an unanticipated error is the caller's, as
                # it always was (the engine reports it), not a quiet failure.
                raise
            logger.exception("Output plugin %s: write failed", self.connection_label)
            self._output_runtime.release_send(admission)
            self._write_failed(f"the write raised {type(exc).__name__}: {exc}")
            return WriteResult(False, False)
        if result is None:
            # The slot stays taken: the device may still be receiving the write.
            budget = self.write_timeout_seconds
            logger.error("Output plugin %s: write still running after %gs; cancelled", self.connection_label, budget)
            self._write_failed(f"the write did not finish within {budget:g}s; it was cancelled.")
            return WriteResult(False, False)
        if result.throttled:
            return self._device_throttled(admission, result.retry_after_seconds)
        if result.success:
            # Landed — or the device already showed it (a fan-out whose every
            # part was unchanged): either way it is what the board shows.
            self._frames.record_sent(final, cells=cells)
        elif not result.success and not result.partial:
            self._output_runtime.release_send(admission)
        if result.success:
            self.last_write_error = None
            output_breakers().record_success(self._breaker_key())
        elif not result.partial:
            # A partial write is a device that answered: it neither trips nor
            # resets the breaker.
            self._write_failed("the output reported the write failed.")
        return WriteResult(
            result.success, result.was_sent, partial=result.partial, failed_regions=result.failed_regions
        )

    def _device_throttled(self, admission: Admission, retry_after: int | None) -> WriteResult:
        """The device refused the write for rate: keep its floor slot closed
        for the *retry_after* seconds it asked for, and say so."""
        if retry_after is not None:
            self._output_runtime.hold_send(admission, self.min_send_interval_ms / 1000.0, retry_after)
        self._last_send_throttled = True
        self._last_send_retry_after = retry_after
        return WriteResult(True, False, throttled=True, retry_after_seconds=retry_after)

    def _call_plugin(self, call: Callable[[CancelToken], Any], force: bool) -> Callable[[CancelToken], Any]:
        """*call*, with the plugin's :attr:`~OutputPluginBase.forced` set for its duration."""

        def forced_call(token: CancelToken) -> Any:
            self.plugin.forced = force
            try:
                return call(token)
            finally:
                self.plugin.forced = False

        return forced_call

    def send_characters(
        self,
        characters: list[list[int]],
        strategy: Any | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
        *,
        with_outcome: bool = False,
        cells: RichCellFrame | None = None,
    ) -> Any:
        """One frame to the plugin's :meth:`~OutputPluginBase.write`, under core's policy.

        With rich *cells* and a plugin that :attr:`takes_cells`, the frame
        goes to :meth:`~OutputPluginBase.write_cells` instead and the dedupe
        is colour-aware; otherwise the cells are dropped here and nothing
        differs from a plain write.
        """
        if not self.plugin.accepts_frame(characters):
            return self._result(WriteResult(False, False), with_outcome)
        if strategy is not None and strategy not in NATIVE_STRATEGIES:
            logger.error("Invalid strategy: %s. Must be one of %s", strategy, sorted(NATIVE_STRATEGIES))
            return self._result(WriteResult(False, False), with_outcome)
        native = NativeTransition.of(strategy, step_interval_ms, step_size)
        if native is not None and not native.supported_by(self.native_transitions):
            native = None
        if cells is not None and not self.takes_cells:
            cells = None
        with self._output_runtime.write():
            frames = self._frames
            with frames.lock:
                admission = self._admit(
                    lambda: self.skip_unchanged and not force and frames.matches_frame(characters, cells)
                )
            if admission.verdict == "throttled":
                return self._result(
                    WriteResult(True, False, throttled=True, retry_after_seconds=admission.retry_after), with_outcome
                )
            if admission.verdict == "unchanged":
                return self._result(WriteResult(True, False), with_outcome)
            refused = self._breaker_refusal(admission)
            if refused is not None:
                return self._result(refused, with_outcome)
            if cells is not None:
                rich = cells
                result = self._deliver(
                    admission,
                    characters,
                    self._call_plugin(
                        lambda cancel: self.plugin.write_cells(rich, native=native, cancel=cancel), force
                    ),
                    cells=rich,
                )
            else:
                result = self._deliver(
                    admission,
                    characters,
                    self._call_plugin(
                        lambda cancel: self.plugin.write(characters, native=native, cancel=cancel), force
                    ),
                )
            return self._result(result, with_outcome)

    def write_sequence(self, frames: list[TimedFrame], *, cancel: threading.Event | None = None) -> WriteResult:
        """A whole transition to the plugin's :meth:`~OutputPluginBase.write_sequence`
        as one write: one floor slot, the last frame recorded as shown.

        *cancel* is the run's token; the runtime already installed it as the
        board's current one, which is what the plugin receives.
        """
        if not frames:
            return WriteResult(True, False)
        frames = compress_sequence(frames, self.capabilities.max_frames)
        final = frames[-1].frame
        with self._output_runtime.write():
            admission = self._admit(lambda: False)
            if admission.verdict == "throttled":
                return WriteResult(True, False, throttled=True, retry_after_seconds=admission.retry_after)
            refused = self._breaker_refusal(admission)
            if refused is not None:
                return refused._replace(floor_seconds=self._floor_seconds())
            result = self._deliver(admission, final, lambda token: self.plugin.write_sequence(frames, cancel=token))
            return result._replace(floor_seconds=self._floor_seconds())

    def _shown_cells(self, rows: int, cols: int) -> RichCellFrame | None:
        """What the board shows, as rich cells shaped *rows* x *cols*: the
        dedupe cache, else the last frame sent; ``None`` when unknown."""
        from .cells import cells_from_codes

        frames = self._frames
        with frames.lock:
            for codes, cells in ((frames.characters, frames.cells), (frames.last_frame, frames.last_cells)):
                if not codes:
                    continue
                shown = cells if cells is not None else cells_from_codes(codes)
                if len(shown) == rows and all(len(row) == cols for row in shown):
                    return shown
                return None
        return None

    def _render_transition(
        self,
        characters: list[list[int]],
        cells: RichCellFrame | None,
        strategy: Any | None,
        force: bool,
        with_outcome: bool,
    ) -> Any:
        """One change on a board whose plugin renders LED transitions.

        Snaps (a plain :meth:`send_characters`) when there is nothing to
        animate: no known previous frame, the same frame, or a resolved
        ``"none"``. Otherwise the plugin's ``write_transition`` gets the
        before/after rich frames and the resolved transition as one write.
        """
        from .cells import cells_equal, cells_from_codes

        after = cells if cells is not None else cells_from_codes(characters)
        cols = len(characters[0]) if characters else 0
        before = self._shown_cells(len(characters), cols)
        transition = self.resolve_transition(strategy)
        if before is None or transition.spec == "none" or cells_equal(before, after):
            rich: dict[str, Any] = {"cells": cells} if cells is not None else {}
            return self.send_characters(characters, force=force, with_outcome=with_outcome, **rich)
        kept = cells if cells is not None and self.takes_cells else None
        frames = self._frames
        with frames.lock:
            admission = self._admit(
                lambda: self.skip_unchanged and not force and frames.matches_frame(characters, kept)
            )
        if admission.verdict == "throttled":
            return self._result(
                WriteResult(True, False, throttled=True, retry_after_seconds=admission.retry_after), with_outcome
            )
        if admission.verdict == "unchanged":
            return self._result(WriteResult(True, False), with_outcome)
        refused = self._breaker_refusal(admission)
        if refused is not None:
            return self._result(refused, with_outcome)
        result = self._deliver(
            admission,
            characters,
            lambda cancel: self.plugin.write_transition(before, after, transition, cancel=cancel),
            cells=kept,
        )
        return self._result(result, with_outcome)

    def render(
        self,
        characters: list[list[int]],
        *,
        strategy: str | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
        device_type: str | None = None,
        transition_config: dict | None = None,
        with_outcome: bool = False,
        cells: RichCellFrame | None = None,
    ) -> Any:
        """Write one grid with its transition; the bound runtime drives it.

        *cells* are the grid's rich cells (:mod:`src.outputs.cells`), which
        land with the write that lands on *characters*. For a plugin that
        :attr:`takes_transitions`, the change is its LED transition instead
        (:meth:`resolve_transition`).
        """

        def reset() -> None:
            self._last_send_throttled = False
            self._last_send_retry_after = None

        if self.takes_transitions:
            with self._output_runtime.run():
                reset()
                return self._render_transition(characters, cells, strategy, force, with_outcome)

        rich: dict[str, Any] = {"cells": cells} if cells is not None else {}
        return self._output_runtime.render(
            self,
            characters,
            strategy=strategy,
            step_interval_ms=step_interval_ms,
            step_size=step_size,
            force=force,
            device_type=device_type,
            transition_config=transition_config,
            with_outcome=with_outcome,
            plugins_enabled=transition_plugins_enabled,
            on_run_start=reset,
            **rich,
        )

    # --- reads and probes ------------------------------------------------------------------

    def read_current_message(self, sync_cache: bool = False) -> list[list[int]] | None:
        if not self.read_back.supported:
            return None
        if self.capabilities.delivery == "pull":
            # A pull device shows what core stored for it: the last frame
            # sent, while it still has the board's shape.
            grid = self.plugin.board_geometry
            return self._output_runtime.displayed_frame(*grid) if grid is not None else None
        try:
            characters = self.plugin.read_current()
        except Exception:
            if self.first_party:
                raise
            logger.exception("Output plugin %s: read_current failed", self.connection_label)
            return None
        if sync_cache:
            if characters:
                self._frames.record_read(characters)
                logger.info("Cache synced with current board state")
            self.plugin.cache_synced(characters or None)
        return characters

    def clear_cache(self) -> None:
        self._frames.forget()
        self.plugin.cache_cleared()

    def run_with_plugin(self, fn: Callable[[OutputPluginBase], Any]) -> Any:
        """Run ``fn(plugin)`` on this board's live instance as one write of
        the board: it preempts the run in flight and holds the send lock, so
        it never interleaves with the engine's sends. A board-settings action
        that writes to the device it drives (an identify flash) goes through
        here (``ActionContext.with_live``)."""
        with self._output_runtime.write():
            return fn(self.plugin)

    def get_cache_status(self) -> dict:
        return {
            "has_cached_text": False,
            "has_cached_characters": self._frames.characters is not None,
            "skip_unchanged_enabled": self.skip_unchanged,
            "cached_text_preview": None,
        }

    def check_connection(self) -> ConnectionCheck:
        try:
            return self.plugin.check_connection()
        except Exception as exc:
            if self.first_party:
                # A first-party probe raises what is not a device verdict (an
                # unusable credential: ValueError) for its route to answer.
                raise
            logger.exception("Output plugin %s: check_connection failed", self.connection_label)
            return ConnectionCheck(
                success=False, message="The output's connection check failed.", failure="unreachable", error=str(exc)
            )

    def test_connection(self) -> bool:
        try:
            return bool(self.plugin.test_connection())
        except Exception:
            logger.exception("Output plugin %s: test_connection failed", self.connection_label)
            return False

    # --- lifetime ----------------------------------------------------------------------

    def close(self) -> None:
        """End the instance's lifetime: :meth:`OutputPluginBase.close`, once."""
        if self._closed:
            return
        self._closed = True
        try:
            self.plugin.close()
        except Exception:
            logger.exception("Output plugin %s: close failed", self.connection_label)
        try:
            self.plugin.http.close()
        except Exception:
            logger.exception("Output plugin %s: closing its HTTP session failed", self.connection_label)
