"""Host-side execution loop for transition plugins.

A :class:`TransitionRunner` is constructed once with a resolver callable
that maps a plugin id to a loaded
:class:`~src.plugins.base.TransitionPluginBase` instance.  At runtime the
:class:`~src.board_client.BoardClient` invokes :meth:`TransitionRunner.run`
with the target grid and a cancellation event.  The runner:

1. Resolves the plugin and reads its ``transition_settings`` caps.
2. Determines the "from" grid (current board state or a blank fallback).
3. Iterates the plugin's :meth:`generate_frames`, sending each frame via
   ``board_client.send_characters(..., force=True)`` so the cache cannot
   silently drop intentional repeats.
4. Sleeps the requested ``delay_ms`` (clamped to ``min_interval_ms``) on
   the cancel event so cancellation lands cleanly between frames.
5. Aborts when caps are exceeded or the event is set.
6. Always sends ``to_grid`` once the generator is exhausted (or aborted)
   so the board lands on the exact target.

The runner is intentionally synchronous -- it runs on the caller's thread
holding the board's send lock.  Long transitions therefore block the
caller; this is by design so rotation / triggers / manual sends serialize
naturally.  Callers that need fire-and-forget should spawn a thread.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Any

from src.devices import BoardContext, classify_dimensions
from src.plugins.base import TransitionPluginBase

logger = logging.getLogger(__name__)


TransitionResolver = Callable[[str], TransitionPluginBase | None]


@dataclass
class TransitionRunResult:
    """Outcome of a single :meth:`TransitionRunner.run` invocation.

    Attributes:
        completed: True if the plugin's generator exhausted normally.
            False if cancelled or capped early.
        frames_sent: Total frames pushed to the board (excludes the final
            ``to_grid`` snap if no plugin frames ran).
        elapsed_seconds: Wall-clock duration of the run.
        cancelled: True if the cancel event tripped during execution.
        capped: True if a max_frames / max_runtime cap aborted the run.
        reason: Short human-readable reason string for logs.
        last_send_monotonic: ``time.monotonic()`` timestamp of the last
            frame actually sent, or *None* if no frames were sent.  Lets
            the caller pace the final snap past a throttled client's
            minimum send interval.
    """

    completed: bool
    frames_sent: int
    elapsed_seconds: float
    cancelled: bool = False
    capped: bool = False
    reason: str = ""
    last_send_monotonic: float | None = None


class TransitionRunner:
    """Drives a transition plugin's frame generator against a board client.

    The runner is stateless across runs; a single instance can safely
    service many concurrent boards as long as each call uses its own
    ``board_client`` and ``cancel_event``.
    """

    def __init__(self, resolver: TransitionResolver):
        """Construct a runner.

        Args:
            resolver: Callable that returns the loaded
                :class:`TransitionPluginBase` instance for a plugin id, or
                *None* if the plugin is unknown / disabled.
        """
        self._resolver = resolver

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        plugin_id: str,
        to_grid: list[list[int]],
        board_client: Any,
        cancel_event: Event | None = None,
        device_type: str | None = None,
        from_grid: list[list[int]] | None = None,
        config: dict | None = None,
    ) -> tuple[bool, bool]:
        """Run *plugin_id*'s transition toward *to_grid*.

        Args:
            plugin_id: Transition plugin id to invoke.
            to_grid: Target grid the transition should end on.
            board_client: Object with ``send_characters(grid, strategy=None,
                force=False)`` and optional ``read_current_message()``.
            cancel_event: Threading event that, when set, asks the runner
                to wind down at the next delay boundary.
            device_type: Optional ``"flagship"`` / ``"note"`` hint used to
                resolve dimensions.  Defaults to the grid's shape.
            from_grid: Optional explicit starting grid.  When *None* the
                runner reads from ``board_client._last_characters`` (the
                cache populated by previous sends), falling back to
                ``read_current_message()`` and finally a blank grid.
            config: Optional plugin config override.  When *None* the
                runner uses the plugin's currently bound ``config`` dict.

        Returns:
            ``(success, was_sent)`` matching ``send_characters``'s contract.
            ``success`` is True unless every send failed; ``was_sent`` is
            True if at least one frame (including the final snap) reached
            the board.
        """
        plugin = self._resolver(plugin_id)
        if plugin is None:
            logger.warning(
                "TransitionRunner: plugin %r not found; snapping to target",
                plugin_id,
            )
            return board_client.send_characters(to_grid, strategy=None, force=True)

        device = self._resolve_device(to_grid, device_type)
        from_grid_resolved = self._resolve_from_grid(board_client, to_grid, from_grid)
        config_resolved = dict(config) if config is not None else dict(plugin.config or {})
        caps = plugin.transition_settings

        result = self._drive_generator(
            plugin=plugin,
            from_grid=from_grid_resolved,
            to_grid=to_grid,
            device=device,
            config=config_resolved,
            board_client=board_client,
            cancel_event=cancel_event,
            caps=caps,
        )

        # Snap to to_grid unless we were cancelled.  On cancellation the
        # caller that interrupted us has its own target; sending our
        # to_grid here would flash the wrong content on the board before
        # the new transition begins.  Capped / errored runs still snap so
        # the board lands somewhere coherent.
        if result.cancelled:
            logger.info(
                "TransitionRunner: plugin=%s frames=%d elapsed=%.2fs %s (skipping final snap)",
                plugin_id,
                result.frames_sent,
                result.elapsed_seconds,
                result.reason,
            )
            return (True, bool(result.frames_sent))

        # Pace the final snap past a throttled client's minimum send
        # interval (cloud note arrays silently skip sends inside their
        # window — the snap must actually land or the board is left stuck
        # on an intermediate frame).  Waits on the cancel event so a
        # concurrent render can still preempt the snap.
        client_min_ms = int(getattr(board_client, "min_send_interval_ms", 0) or 0)
        if client_min_ms and result.last_send_monotonic is not None:
            remaining = (client_min_ms / 1000.0) - (time.monotonic() - result.last_send_monotonic)
            if remaining > 0:
                if cancel_event is not None:
                    if cancel_event.wait(remaining):
                        logger.info(
                            "TransitionRunner: plugin=%s cancelled while pacing final snap",
                            plugin_id,
                        )
                        return (True, bool(result.frames_sent))
                else:
                    time.sleep(remaining)

        snap_success, snap_sent = board_client.send_characters(to_grid, strategy=None, force=True)

        logger.info(
            "TransitionRunner: plugin=%s frames=%d elapsed=%.2fs %s",
            plugin_id,
            result.frames_sent,
            result.elapsed_seconds,
            result.reason,
        )

        was_sent = bool(result.frames_sent) or snap_sent
        return (snap_success, was_sent)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_device(
        self,
        to_grid: list[list[int]],
        device_type: str | None,
    ) -> BoardContext:
        """Build a :class:`BoardContext` for the grid being rendered.

        Dimensions always come from the grid itself (that is what the plugin
        must produce frames for — including W×H note arrays); *device_type*
        and :func:`classify_dimensions` only inform the type label.  The
        runner never uses this for validation, only as a hint to the plugin.
        """
        rows = len(to_grid)
        cols = len(to_grid[0]) if rows else 0
        resolved_type = device_type or classify_dimensions(rows, cols).get("device_type") or "flagship"
        return BoardContext(device_type=resolved_type, rows=rows, cols=cols)

    def _resolve_from_grid(
        self,
        board_client: Any,
        to_grid: list[list[int]],
        explicit: list[list[int]] | None,
    ) -> list[list[int]]:
        """Pick a starting grid for the transition.

        Priority: explicit override → cached ``_last_characters`` → blank
        grid sized like ``to_grid``.  We deliberately do *not* fall back to
        a live ``read_current_message()`` call: that's a network round-trip
        under the send lock, and historically it returns text rather than
        a grid (so the result is rejected anyway).  A blank from-grid is a
        safe default — the runner's final snap (or the next non-cancelled
        run) lands the board on the correct target regardless.
        """
        if explicit is not None:
            return explicit

        cached = getattr(board_client, "_last_characters", None)
        if isinstance(cached, list) and cached:
            return [list(row) for row in cached]

        rows = len(to_grid)
        cols = len(to_grid[0]) if rows else 0
        return [[0] * cols for _ in range(rows)]

    def _drive_generator(
        self,
        plugin: TransitionPluginBase,
        from_grid: list[list[int]],
        to_grid: list[list[int]],
        device: BoardContext,
        config: dict,
        board_client: Any,
        cancel_event: Event | None,
        caps: dict,
    ) -> TransitionRunResult:
        """Iterate the plugin's frame generator and send frames.

        Encapsulates cap enforcement, cancellation checks, and per-frame
        error handling.  Returns a structured result; the caller is
        responsible for the final snap-to-target send.
        """
        min_interval_ms = int(caps.get("min_interval_ms", 50))
        max_frames = int(caps.get("max_frames", 500))
        max_runtime_s = int(caps.get("max_runtime_seconds", 120))
        respect_cancel = bool(caps.get("interruptible", True))
        # Throttled clients (cloud note arrays) silently skip sends inside
        # their minimum interval; pace frames so each one actually lands.
        client_min_ms = int(getattr(board_client, "min_send_interval_ms", 0) or 0)

        frames_sent = 0
        last_send: float | None = None
        started = time.monotonic()
        reason = "completed"
        cancelled = False
        capped = False

        try:
            generator = plugin.generate_frames(from_grid, to_grid, device, config)
        except Exception as exc:
            logger.exception(
                "TransitionRunner: generate_frames raised for %s: %s",
                plugin.plugin_id,
                exc,
            )
            return TransitionRunResult(
                completed=False,
                frames_sent=0,
                elapsed_seconds=time.monotonic() - started,
                reason=f"generator error: {exc}",
            )

        # Generators are lazy: errors fire when ``next()`` is called, not
        # when the function is invoked.  Pull frames with manual ``next``
        # so we can catch and log per-iteration crashes.
        while True:
            try:
                frame = next(generator)
            except StopIteration:
                break
            except Exception as exc:
                logger.exception(
                    "TransitionRunner: plugin %s raised during iteration: %s",
                    plugin.plugin_id,
                    exc,
                )
                reason = f"iteration error: {exc}"
                break

            # Cap checks happen *before* sending so a runaway generator
            # can't burn one extra send.
            if frames_sent >= max_frames:
                capped = True
                reason = f"max_frames cap ({max_frames}) reached"
                break
            elapsed = time.monotonic() - started
            if elapsed >= max_runtime_s:
                capped = True
                reason = f"max_runtime_seconds cap ({max_runtime_s}s) reached"
                break
            if respect_cancel and cancel_event is not None and cancel_event.is_set():
                cancelled = True
                reason = "cancelled by concurrent send"
                break

            grid, delay_ms = self._unpack_frame(frame)
            if grid is None:
                reason = "plugin yielded malformed frame"
                break

            try:
                board_client.send_characters(grid, strategy=None, force=True)
            except Exception as exc:  # pragma: no cover - logged + continue
                logger.warning(
                    "TransitionRunner: send_characters raised mid-transition: %s",
                    exc,
                )
                reason = f"send error: {exc}"
                break

            frames_sent += 1
            last_send = time.monotonic()

            # Sleep on the cancel event so wakeups are immediate.
            effective_delay_ms = max(int(delay_ms or 0), min_interval_ms, client_min_ms)
            if respect_cancel and cancel_event is not None:
                if cancel_event.wait(effective_delay_ms / 1000.0):
                    cancelled = True
                    reason = "cancelled by concurrent send"
                    break
            elif effective_delay_ms:
                time.sleep(effective_delay_ms / 1000.0)

        return TransitionRunResult(
            completed=not (cancelled or capped),
            frames_sent=frames_sent,
            elapsed_seconds=time.monotonic() - started,
            cancelled=cancelled,
            capped=capped,
            reason=reason,
            last_send_monotonic=last_send,
        )

    @staticmethod
    def _unpack_frame(
        frame: Any,
    ) -> tuple[list[list[int]] | None, int]:
        """Coerce a plugin's yielded value into ``(grid, delay_ms)``.

        Accepts ``(grid, delay)`` tuples and bare grids (treated as zero
        delay).  Returns ``(None, 0)`` on shapes we can't make sense of so
        the caller aborts the run with a logged reason.
        """
        if isinstance(frame, tuple) and len(frame) == 2:
            grid, delay = frame
            try:
                delay_int = int(delay)
            except (TypeError, ValueError):
                delay_int = 0
            if isinstance(grid, list) and grid and isinstance(grid[0], list):
                return grid, delay_int
            return None, 0
        if isinstance(frame, list) and frame and isinstance(frame[0], list):
            return frame, 0
        return None, 0
