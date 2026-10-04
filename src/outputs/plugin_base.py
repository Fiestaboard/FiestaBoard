"""The output-plugin contract: what a third-party device driver implements.

An output plugin (``plugin_type: "output"`` in its manifest) is a **pipe**
to one device (plan D3). Core keeps the policy — the send lock, latest-wins
preemption, the send floor, frame dedupe, the last-frame store and
transition driving all live on the board's
:class:`~src.outputs.runtime.OutputRuntime` — and the plugin moves frames:

.. code-block:: python

    from src.plugins import OutputPluginBase, WriteResult

    class AcmeSign(OutputPluginBase):
        def device_key(self) -> str:
            return f"acme:{self.config['host']}"

        def write(self, frame, *, native, cancel) -> WriteResult:
            post(self.config["host"], frame)          # honour `cancel` in waits
            return WriteResult(success=True, was_sent=True)

**Per-board instances** (plan D2). Unlike a data plugin, the loader never
constructs an output plugin: it loads the *class* and the manifest. Core
builds one instance per board — ``cls(board_id, output_config)`` — calls
:meth:`open` before the first write, and :meth:`close` when the board is
removed or its connection settings change (a new instance replaces it).

**Frames.** Today every output receives a :data:`CellFrame`: rows of
FiestaBoard character codes 0–71 (the split-flap projection). Rich cells —
per-cell glyph, foreground and background, projected by core from the
output's character set (plan D15) — arrive as an additive frame type; a
plugin will opt in through its manifest, so a plugin written against this
contract keeps receiving the grid it understands.

**Capabilities.** :meth:`capabilities` defaults to what the manifest's
``output`` block declares; override it to narrow per board (a cloud
connection that animates no native transition, say).
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from src.send_outcome import FrameRegion, WriteResult

from .hooks import ConnectionCheck
from .transitions import NativeTransition

if TYPE_CHECKING:
    from .output_manifest import OutputManifest
    from .registry import OutputCapabilities

__all__ = [
    "CancelToken",
    "CellFrame",
    "ConnectionCheck",
    "DiagnosticCheck",
    "FrameRegion",
    "NativeTransition",
    "OutputPluginBase",
    "TimedFrame",
    "WriteResult",
]

#: One frame: rows of FiestaBoard character codes (0–71), board-shaped.
CellFrame = list[list[int]]


class TimedFrame(NamedTuple):
    """One frame of a ``sequence`` upload and how long it shows."""

    frame: CellFrame
    duration_ms: int


class CancelToken:
    """The run's cancel signal, read-only for the plugin.

    Set when a newer frame preempts the write in flight. A plugin waits on
    it instead of sleeping (backoffs, per-frame pacing inside one sequence,
    multi-request uploads) and stops early when it fires.
    """

    def __init__(self, event: threading.Event | None = None) -> None:
        self._event = event if event is not None else threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, seconds: float) -> bool:
        """Sleep up to *seconds*; True as soon as the write is cancelled."""
        return self._event.wait(seconds)


@dataclass(frozen=True)
class DiagnosticCheck:
    """One line of an output's own diagnostics."""

    name: str
    ok: bool
    detail: str = ""


class OutputPluginBase(ABC):
    """Base class for output plugins. One instance drives one board.

    Args:
        board_id: The saved board this instance drives (``None`` for a draft
            probe of unsaved settings).
        config: The board's ``output_config``, shaped by the manifest's
            ``output.settings_schema``. Secrets arrive unmasked.
    """

    #: The plugin id, matching ``manifest.json``. Set by the loader on the
    #: class it loads; a plugin may also set it itself.
    plugin_id: ClassVar[str] = ""

    def __init__(self, board_id: str | None, config: dict[str, Any]) -> None:
        self.board_id = board_id
        self.config = dict(config or {})
        self._output_manifest: OutputManifest | None = None

    # --- identity and capabilities ---------------------------------------------

    def bind_manifest(self, manifest: OutputManifest) -> None:
        """Core hands the instance its parsed ``output`` block. Not for plugins to call."""
        self._output_manifest = manifest

    def capabilities(self) -> OutputCapabilities:
        """What this board's device can do. Defaults to the manifest's declaration."""
        if self._output_manifest is None:
            raise RuntimeError(f"{type(self).__name__}: no manifest bound; override capabilities()")
        return self._output_manifest.capabilities

    def device_key(self) -> str:
        """Identity of the physical device, for core state that must outlive
        this instance (the send floor). Override with something stable and
        credential-free — host and port, or a hash of a token — so two boards
        on one device share its floor. The default is the board."""
        return f"{self.plugin_id or type(self).__name__}:{self.board_id or f'draft-{id(self):x}'}"

    # --- lifetime ----------------------------------------------------------------

    def open(self) -> None:  # noqa: B027 - optional hook
        """Called once before the first write (connect, warm up)."""

    def close(self) -> None:  # noqa: B027 - optional hook
        """Called once when core is done with this instance."""

    # --- writes ------------------------------------------------------------------

    @abstractmethod
    def write(self, frame: CellFrame, *, native: NativeTransition | None, cancel: CancelToken) -> WriteResult:
        """Show *frame* on the device.

        Args:
            frame: The whole board, as character codes.
            native: A device-native transition to animate the change with,
                only ever one the plugin declared in ``native_transitions``.
            cancel: Set when a newer frame preempts this one.

        Returns:
            ``WriteResult(success, was_sent)``; ``partial`` and
            ``failed_regions`` when only part of the board updated. Core
            fills ``throttled``/``floor_seconds`` itself.
        """

    def write_sequence(self, frames: list[TimedFrame], *, cancel: CancelToken) -> WriteResult:
        """Upload a whole timed sequence in one go (``animation: sequence``).

        Core calls it only for outputs whose device model declares sequence
        delivery; the last frame is always the target. Core's floor spaces
        sequences; pacing inside one upload is the plugin's.
        """
        raise NotImplementedError(f"{type(self).__name__} declares no sequence upload")

    # --- reads and probes ----------------------------------------------------------

    def read_current(self) -> CellFrame | None:
        """What the device shows, when ``read_back.supported``; else ``None``."""
        return None

    def check_connection(self) -> ConnectionCheck:
        """Probe the device once: success, or a failure class with guidance."""
        return ConnectionCheck(success=True, message="No connection check for this output.")

    @classmethod
    def discover(cls, timeout: float) -> list[dict]:
        """Devices found on the network, each a dict with at least ``ip`` and
        ``port``. Default: none."""
        return []

    def identify(self) -> None:  # noqa: B027 - optional hook
        """Make the physical device show which one it is (flash, blink)."""

    def diagnostics(self) -> list[DiagnosticCheck]:
        """The output's own checks for the diagnostics page. Default: none."""
        return []
