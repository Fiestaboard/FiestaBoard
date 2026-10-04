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
  runtime's :class:`~src.outputs.frames.FrameCache`.
- **Native transitions.** Forwarded as a
  :class:`~src.outputs.transitions.NativeTransition` only when the plugin
  declares the strategy (the runtime decides; the adapter carries it).
- **Sequences.** For ``animation: sequence`` outputs the runtime collects a
  transition's frames and hands them to :meth:`write_sequence` as one upload.

A plugin exception is a failed write (logged with the plugin id), never an
engine crash; the floor slot it reserved is given back.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.send_outcome import WriteResult

from .hooks import ConnectionCheck, ReadBack
from .plugin_base import CancelToken, OutputPluginBase, TimedFrame
from .runtime import OutputRuntime
from .transitions import NATIVE_STRATEGIES, NativeTransition, transition_plugins_enabled

if TYPE_CHECKING:
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

    def __init__(self, plugin: OutputPluginBase, *, clock: Callable[[], float] | None = None) -> None:
        self.plugin = plugin
        self.skip_unchanged = True
        self._clock = clock if clock is not None else time.monotonic
        self._output_runtime = OutputRuntime()
        self._last_send_throttled = False
        self._last_send_retry_after: int | None = None
        self._closed = False

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
        return self.plugin.plugin_id or type(self.plugin).__name__

    def device_key(self) -> str:
        return self.plugin.device_key()

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

    def _deliver(self, admission: Admission, final: list[list[int]], call: Callable[[CancelToken], Any]) -> WriteResult:
        """Run the plugin's write under the run's token; settle floor and frame cache."""
        cancel = CancelToken(self._output_runtime.cancel_event)
        try:
            result = WriteResult.of(call(cancel))
        except Exception:
            logger.exception("Output plugin %s: write failed", self.connection_label)
            self._output_runtime.release_send(admission)
            return WriteResult(False, False)
        if result.success and result.was_sent:
            self._frames.record_sent(final)
        elif not result.success and not result.partial:
            self._output_runtime.release_send(admission)
        return WriteResult(
            result.success, result.was_sent, partial=result.partial, failed_regions=result.failed_regions
        )

    def send_characters(
        self,
        characters: list[list[int]],
        strategy: Any | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
        *,
        with_outcome: bool = False,
    ) -> Any:
        """One frame to the plugin's :meth:`~OutputPluginBase.write`, under core's policy."""
        if strategy is not None and strategy not in NATIVE_STRATEGIES:
            logger.error("Invalid strategy: %s", strategy)
            return self._result(WriteResult(False, False), with_outcome)
        native = NativeTransition.of(strategy, step_interval_ms, step_size)
        if native is not None and not native.supported_by(self.native_transitions):
            native = None
        with self._output_runtime.write():
            frames = self._frames
            with frames.lock:
                admission = self._admit(lambda: self.skip_unchanged and not force and frames.matches(characters))
            if admission.verdict == "throttled":
                return self._result(
                    WriteResult(True, False, throttled=True, retry_after_seconds=admission.retry_after), with_outcome
                )
            if admission.verdict == "unchanged":
                return self._result(WriteResult(True, False), with_outcome)
            result = self._deliver(
                admission, characters, lambda cancel: self.plugin.write(characters, native=native, cancel=cancel)
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
            result = self._deliver(admission, final, lambda token: self.plugin.write_sequence(frames, cancel=token))
            return result._replace(floor_seconds=self._floor_seconds())

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
    ) -> Any:
        """Write one grid with its transition; the bound runtime drives it."""

        def reset() -> None:
            self._last_send_throttled = False
            self._last_send_retry_after = None

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
        )

    # --- reads and probes ------------------------------------------------------------------

    def read_current_message(self, sync_cache: bool = False) -> list[list[int]] | None:
        if not self.read_back.supported:
            return None
        try:
            characters = self.plugin.read_current()
        except Exception:
            logger.exception("Output plugin %s: read_current failed", self.connection_label)
            return None
        if sync_cache and characters:
            self._frames.record_read(characters)
        return characters

    def clear_cache(self) -> None:
        self._frames.forget()

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
            logger.exception("Output plugin %s: check_connection failed", self.connection_label)
            return ConnectionCheck(
                success=False, message="The output's connection check failed.", failure="unreachable", error=str(exc)
            )

    def test_connection(self) -> bool:
        return self.check_connection().success

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
