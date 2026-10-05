"""A test-only output plugin: it records every frame core hands it.

Not a product plugin (it lives under tests/fixtures/, never plugins/). It
proves the output-plugin contract end to end: the loader loads the class,
core builds one instance per board, and the board's runtime drives it. Core
CI also runs the :class:`~src.outputs.conformance.OutputConformanceSuite`
against it (``tests/test_output_conformance.py``).

Per-board behaviour comes from the board's ``output_config``:

- ``host`` — the device identity (``device_key``), so two boards on one host
  share a send floor;
- ``animation`` / ``min_interval_ms`` — narrow the manifest's capabilities;
- ``wait_for_cancel`` — ``write`` blocks until core cancels it (or 5 s);
- ``panels`` — with a transport attached, each panel is one request (a
  vertical slice of the board), so one failed panel is a partial write;
- ``setup_first`` — each write first sends a setup request (a brightness
  command, say) whose failure it tolerates, marked ``setup=True`` so core's
  accounting does not count it as part of the board write.

Every device request goes through ``self.http`` (core's helper: the host
fence, timeouts, the cancel token), as a real output plugin's must.
``transport`` says whether a device is attached: ``None`` (the default)
records in memory only and sends nothing; the conformance suite attaches its
fake transport and routes ``self.http`` to it.
"""

from __future__ import annotations

import contextlib
import dataclasses
import threading

from src.plugins import FrameRegion, OutputPluginBase, WriteResult

#: Every instance ever built, in order (tests clear it).
INSTANCES: list[RecordingOutput] = []


class RecordingOutput(OutputPluginBase):
    def __init__(self, board_id, config):
        super().__init__(board_id, config)
        self.writes: list = []
        self.sequences: list = []
        self.natives: list = []
        self.cancelled_writes = 0
        self.opened = False
        self.closed = False
        self.write_started = threading.Event()
        self.transport = None
        INSTANCES.append(self)

    def capabilities(self):
        base = super().capabilities()
        return dataclasses.replace(
            base,
            animation=self.config.get("animation", base.animation),
            min_interval_ms=int(self.config.get("min_interval_ms", base.min_interval_ms)),
        )

    def device_key(self) -> str:
        return f"recording:{self.config.get('host', '')}"

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def _slices(self, frame):
        """(panel id, region) per request: one per panel, else the whole board."""
        rows, cols = len(frame), len(frame[0]) if frame else 0
        panels = self.config.get("panels") or []
        if not panels:
            return [("board", FrameRegion(0, 0, rows, cols))]
        width = max(1, cols // len(panels))
        regions = []
        for index, panel in enumerate(panels):
            col = index * width
            span = cols - col if index == len(panels) - 1 else width
            regions.append((panel.get("id", str(index)), FrameRegion(0, col, rows, span)))
        return regions

    def _request(self, payload, *, setup: bool = False):
        """One device request: a JSON POST to the sign, through core's helper."""
        return self.http.post(f"http://{self.config.get('host', '')}/frame", json=payload, setup=setup)

    def _setup(self) -> None:
        # A setting that did not take is retried next write; the frame still goes.
        with contextlib.suppress(OSError):
            self._request({"setup": "brightness"}, setup=True)

    def _send(self, frame, cancel) -> WriteResult:
        if self.config.get("setup_first") and not cancel.cancelled:
            self._setup()
        landed, failed = [], []
        for panel_id, region in self._slices(frame):
            if cancel.cancelled:
                break
            payload = {"panel": panel_id, "frame": [row[region.col : region.col + region.cols] for row in frame]}
            try:
                self._request(payload)
            except OSError:
                failed.append(region)
            else:
                landed.append(region)
        if failed and landed:
            return WriteResult(False, True, partial=True, failed_regions=tuple(failed))
        if failed:
            return WriteResult(False, False)
        return WriteResult(True, bool(landed))

    def write(self, frame, *, native, cancel):
        self.write_started.set()
        if self.config.get("wait_for_cancel") and cancel.wait(5.0):
            self.cancelled_writes += 1
            return WriteResult(True, False)
        if self.transport is not None:
            result = self._send(frame, cancel)
            if not result.success:
                return result
        self.writes.append([row[:] for row in frame])
        self.natives.append(native)
        return WriteResult(True, True)

    def write_sequence(self, frames, *, cancel):
        self.sequences.append(list(frames))
        if self.transport is None:
            return WriteResult(True, True)
        for timed in frames:
            if cancel.cancelled:
                return WriteResult(True, False)
            result = self._send(timed.frame, cancel)
            if not result.success:
                return result
        return WriteResult(True, True)

    def read_current(self):
        return self.writes[-1] if self.writes else None

    def check_connection(self):
        if self.transport is None:
            return super().check_connection()
        from src.outputs.hooks import ConnectionCheck

        try:
            self._request({"probe": True})
        except OSError as exc:
            return ConnectionCheck(success=False, message=f"Recording sign unreachable: {exc}")
        return ConnectionCheck(success=True, message="Recording sign reachable.")
