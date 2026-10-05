"""A test-only output plugin: it records every frame core hands it.

Not a product plugin (it lives under tests/fixtures/, never plugins/). It
proves the output-plugin contract end to end: the loader loads the class,
core builds one instance per board, and the board's runtime drives it.

Per-board behaviour comes from the board's ``output_config``:

- ``host`` — the device identity (``device_key``), so two boards on one host
  share a send floor;
- ``animation`` / ``min_interval_ms`` — narrow the manifest's capabilities;
- ``wait_for_cancel`` — ``write`` blocks until core cancels it (or 5 s).
"""

from __future__ import annotations

import dataclasses
import threading

from src.plugins import OutputPluginBase, WriteResult

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

    def write(self, frame, *, native, cancel):
        self.write_started.set()
        if self.config.get("wait_for_cancel") and cancel.wait(5.0):
            self.cancelled_writes += 1
            return WriteResult(True, False)
        self.writes.append([row[:] for row in frame])
        self.natives.append(native)
        return WriteResult(True, True)

    def write_sequence(self, frames, *, cancel):
        self.sequences.append(list(frames))
        return WriteResult(True, True)

    def read_current(self):
        return self.writes[-1] if self.writes else None
