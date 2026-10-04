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
            self.http.post(f"http://{self.config['host']}/frame", json=frame)
            return WriteResult(success=True, was_sent=True)

**Device traffic goes through** ``self.http`` (:class:`~src.outputs.http.OutputHttp`),
never ``requests`` directly. It is where core's safety reaches the plugin:
``FIESTABOARD_OUTPUTS_ALLOW_HOSTS`` (a fenced host is refused before a
socket opens), default ``(connect, read)`` timeouts, no redirects, and the
run's cancel token. ``setup=True`` marks a request that is not the board
write itself (a reset, a brightness command). The conformance suite fails a
plugin whose writes or probes open a connection of their own.

**Per-board instances** (plan D2). Unlike a data plugin, the loader never
constructs an output plugin: it loads the *class* and the manifest. Core
builds one instance per board — ``cls(board_id, output_config)`` — calls
:meth:`open` before the first write, and :meth:`close` when the board is
removed or its connection settings change (a new instance replaces it).

**Frames.** :meth:`~OutputPluginBase.write` receives a :data:`CellFrame`:
rows of FiestaBoard character codes 0–71 (the split-flap projection).

**Rich cells** (plan D15/D17) are the additive frame type:
:data:`RichCellFrame`, FiestaUI's ``BoardToken[][]`` — per cell a character,
a colour tile (numeric code, ``"63"``) or an icon (its canonical name), plus
``color`` / ``background`` — projected by core from the board's character
set (:mod:`src.outputs.cells`), so every glyph has already passed the set's
fallback. An output whose character set is rich (colour spans, block spans
or icons, as the LED sets are) opts in by overriding :meth:`write_cells`:

.. code-block:: python

    def write_cells(self, cells, *, native, cancel) -> WriteResult:
        draw(self.config["host"], cells)   # cells[r][c].color, .icon, …

Core then sends every frame it has rich cells for through
:meth:`write_cells` and dedupes colour-aware (a recolour is a new frame);
frames that only ever were codes (a blank board, a transition's
intermediate frames) still arrive through :meth:`write`. A plugin that does
not override it keeps receiving exactly the 0–71 grid it understands.

**LED transitions** (plan D15). An output that overrides
:meth:`~OutputPluginBase.write_transition` receives every change of what
its board shows as the before and after rich frames plus the board's
resolved LED transition (:func:`src.led.resolve_led_transition` for its
device model: the flip FiestaUI previews), and renders it itself::

    def write_transition(self, before, after, transition, *, cancel):
        options = LedLayoutOptions(charset=self.character_set)
        spec = led_spec_for_model(self.device_model)
        planned = plan_transition(
            layout_message(before, spec, options), layout_message(after, spec, options), transition.spec
        )
        upload([f.pixels for f in transition_frames(planned)], cancel)

A plugin that implements only :meth:`write_sequence` keeps receiving a
transition plugin's frames exactly as before.

**What core resolved for the board.** :attr:`~OutputPluginBase.device_model`
(the FiestaUI DeviceModel), :attr:`~OutputPluginBase.character_set`
(materialised) and :attr:`~OutputPluginBase.board_geometry` (rows, cols).

**Capabilities.** :meth:`capabilities` defaults to what the manifest's
``output`` block declares; override it to narrow per board (a cloud
connection that animates no native transition, say).
"""

from __future__ import annotations

import copy
import threading
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from src.markup import BoardToken
from src.send_outcome import FrameRegion, WriteResult

from .hooks import ConnectionCheck
from .http import OutputHttp
from .transitions import NativeTransition

if TYPE_CHECKING:
    from src.led.transition_registry import ResolvedLedTransition

    from .output_manifest import OutputManifest
    from .registry import OutputCapabilities

__all__ = [
    "CancelToken",
    "CellFrame",
    "ConnectionCheck",
    "DiagnosticCheck",
    "FrameRegion",
    "NativeTransition",
    "OutputHttp",
    "OutputPluginBase",
    "RichCellFrame",
    "TimedFrame",
    "WriteResult",
]

#: One frame: rows of FiestaBoard character codes (0–71), board-shaped.
CellFrame = list[list[int]]

#: One rich frame: rows of FiestaUI ``BoardToken``s, board-shaped (see
#: :mod:`src.outputs.cells`).
RichCellFrame = list[list[BoardToken]]


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

    # What core resolved for the board (bind_board); class-level defaults so a
    # subclass that skips super().__init__ still reads "unknown".
    _output_manifest: OutputManifest | None = None
    _board_model: Mapping[str, Any] | None = None
    _board_charset: Mapping[str, Any] | None = None
    _board_geometry: tuple[int, int] | None = None

    def __init__(self, board_id: str | None, config: dict[str, Any]) -> None:
        self.board_id = board_id
        self.config = dict(config or {})
        self._output_manifest = None
        self._http: OutputHttp | None = None

    # --- talking to the device ---------------------------------------------------

    @property
    def http(self) -> OutputHttp:
        """This instance's device HTTP client: THE way a plugin talks to its
        device (host fence, timeouts, no redirects, the run's cancel token).
        See :mod:`src.outputs.http`."""
        helper = getattr(self, "_http", None)
        if helper is None:
            helper = self._http = OutputHttp()
        return helper

    # --- what core resolved for the board --------------------------------------------

    def bind_board(
        self,
        *,
        device_model: Mapping[str, Any] | None = None,
        character_set: Mapping[str, Any] | None = None,
        geometry: tuple[int, int] | None = None,
    ) -> None:
        """Core hands the instance what it resolved for the board. Not for plugins to call."""
        self._board_model = device_model
        self._board_charset = character_set
        self._board_geometry = geometry

    def _model(self) -> Mapping[str, Any] | None:
        if self._board_model is not None:
            return self._board_model
        manifest = self._output_manifest
        return manifest.model(0) if manifest is not None and manifest.device_models else None

    @property
    def device_model(self) -> dict[str, Any] | None:
        """The board's FiestaUI DeviceModel (a copy): the model the board was
        created as, else the plugin's default (first) model; ``None`` before
        core bound a manifest."""
        model = self._model()
        return copy.deepcopy(dict(model)) if model is not None else None

    @property
    def character_set(self) -> dict[str, Any] | None:
        """The board's character set, materialised (a copy): the plugin's
        declared set, else its model's (plan D17); ``None`` when unknown."""
        charset = self._board_charset
        if charset is None:
            from .board_profile import model_character_set

            manifest = self._output_manifest
            model = self._model()
            declared = manifest.character_set if manifest is not None else None
            charset = declared if declared is not None else (model_character_set(model) if model else None)
        return copy.deepcopy(dict(charset)) if charset is not None else None

    @property
    def board_geometry(self) -> tuple[int, int] | None:
        """The board's content grid, ``(rows, cols)`` in characters; ``None``
        when unknown (no model, or one sized per board that core has not bound)."""
        if self._board_geometry is not None:
            return self._board_geometry
        model = self._model()
        if model is None:
            return None
        from .geometry import GeometryError, model_cell_grid

        manifest = self._output_manifest
        try:
            return model_cell_grid(model, manifest.character_set if manifest is not None else None)
        except (GeometryError, KeyError):
            return None

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

    def write_cells(self, cells: RichCellFrame, *, native: NativeTransition | None, cancel: CancelToken) -> WriteResult:
        """Show the rich frame *cells* on the device.

        Called instead of :meth:`write` only for an output whose board's
        character set is rich, and only when the plugin overrides it (the
        opt-in). Every glyph has passed the set's fallback, so each cell is
        one the set can draw. The default draws the 0–71 projection
        through :meth:`write`.
        """
        return self.write([[cell.flap_code for cell in row] for row in cells], native=native, cancel=cancel)

    def write_transition(
        self,
        before: RichCellFrame,
        after: RichCellFrame,
        transition: ResolvedLedTransition,
        *,
        cancel: CancelToken,
    ) -> WriteResult:
        """Animate the board from *before* to *after* (plan D15).

        The opt-in: core calls it, instead of :meth:`write_cells` /
        :meth:`write`, for every change of what the board shows once it
        knows what the board showed before — only for a plugin that
        overrides it. *transition* is the board's resolved LED transition
        (:func:`src.led.resolve_led_transition` for :attr:`device_model`:
        the explicit choice the device can run, else its model's default),
        with ``spec`` already fitted to the device (cadence, frame budget).
        Render it with :func:`src.led.plan_transition` /
        :func:`src.led.transition_frames` and land on *after*. A resolved
        ``"none"`` never reaches here: core snaps through :meth:`write_cells`.

        One write: one floor slot, *after* recorded as shown on success.
        """
        raise NotImplementedError(f"{type(self).__name__} renders no LED transition")

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
