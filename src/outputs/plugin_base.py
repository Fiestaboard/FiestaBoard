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
:meth:`declared_capabilities` is the same question asked of the output as
a whole (the registry entry), before any board exists.

**Rate limits the device enforces.** A write the *device* refused for rate
(an HTTP 429) answers ``WriteResult(True, False, throttled=True,
retry_after_seconds=N)``: core keeps the board's floor slot closed for *N*
seconds and reports the send as throttled, exactly as its own floor would.
Core's floor itself is never the plugin's to keep.

**Boards that predate ``output_config``.** :meth:`config_from_board` turns
a saved board into the instance's config. The default reads the board's
``output_config``; the first-party outputs read the flat fields a board
saved before settings v4 (plan D8) and answer ``None`` for a board with no
usable connection, which builds no driver.

**Board settings** (plan D13). Core asks the plugin *class* about a board's
settings, so it never interprets an output's ``output_config`` itself. Every
hook has a default that suits an output whose settings follow its
manifest's ``settings_schema``:

- :meth:`handle_action` runs a declared settings action (test, discover,
  identify, detect size, or the output's own) with an
  :class:`~src.outputs.hooks.ActionContext`: core builds the instances (a
  throwaway one from the settings, or the board's live one under its send
  lock) and the plugin decides what the action does. The default runs
  ``discover`` on the class and anything else through :meth:`run_action`
  on a throwaway instance.
- :meth:`board_status` is the board's connection summary
  (:class:`~src.outputs.hooks.OutputStatus`): the board card's badge.
  Default: ``None`` — the output has nothing to say, no badge.
- :meth:`normalize_config`, :meth:`mask_config`, :meth:`restore_config`
  and :meth:`masked_config_paths` are how a board's ``output_config`` is
  stored, shown (secrets ``"***"``) and restored from an echo. The defaults
  follow the schema's ``secret`` fields (:mod:`src.outputs.output_config`).

**Fan-out outputs** (one frame split across several devices that each keep
their own dedupe, as a Vestaboard Note array on the Local API does) hear
about core's dedupe through three hooks: :attr:`forced` during a forced
re-send, :meth:`cache_synced` when core adopts a read-back as what the
board shows, and :meth:`cache_cleared` when core forgets it.
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

from .hooks import (
    HINT_HOST,
    ActionField,
    ActionOutcome,
    ConnectionCheck,
    OutputActionError,
    OutputStatus,
    call_discover,
    lan_hint,
)
from .http import OutputHttp
from .transitions import NativeTransition

if TYPE_CHECKING:
    from src.led.transition_registry import ResolvedLedTransition

    from .output_manifest import OutputManifest
    from .registry import OutputCapabilities

__all__ = [
    "ActionField",
    "ActionOutcome",
    "CancelToken",
    "CellFrame",
    "ConnectionCheck",
    "DiagnosticCheck",
    "FrameRegion",
    "NativeTransition",
    "OutputHttp",
    "OutputPluginBase",
    "OutputStatus",
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

    #: Whether a board's content follows its character set's markup: a rich
    #: set (colour spans, block spans, icons) renders with extended markup
    #: (plan D19). ``False`` keeps split-flap markup whatever the set — an
    #: output whose viewer draws the 0–71 grid itself (FiestaPanel).
    markup_follows_charset: ClassVar[bool] = True

    #: True while core runs a forced write (its dedupe bypassed): an output
    #: that keeps per-device dedupe of its own re-sends everything too. Set
    #: by core around each write; read it, never set it.
    forced: bool = False

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

    @classmethod
    def config_from_board(cls, board: Mapping[str, Any]) -> dict[str, Any] | None:
        """The config one instance is built with, from a saved (or draft) board.

        The default is the board's ``output_config``. An output whose boards
        were saved before ``output_config`` existed reads its legacy fields
        here. ``None`` means the board has no usable connection: core builds
        no driver and records the board as unconfigured.
        """
        return dict(board.get("output_config") or {})

    @classmethod
    def declared_capabilities(cls, manifest: OutputManifest) -> OutputCapabilities:
        """What the output may do on any board, for its registry entry.

        Defaults to the manifest's declaration (technology and animation from
        its first device model). Override when the output is more than its
        first model says — :meth:`capabilities` then narrows per board.
        """
        return manifest.capabilities

    def bind_manifest(self, manifest: OutputManifest) -> None:
        """Core hands the instance its parsed ``output`` block. Not for plugins to call."""
        self._output_manifest = manifest

    def capabilities(self) -> OutputCapabilities:
        """What this board's device can do. Defaults to the manifest's declaration."""
        if self._output_manifest is None:
            raise RuntimeError(f"{type(self).__name__}: no manifest bound; override capabilities()")
        return self._output_manifest.capabilities

    def connection_label(self) -> str:
        """How the board is connected, in words (MQTT ``board_api_mode``,
        core's log lines). Defaults to the plugin id."""
        return self.plugin_id or type(self).__name__

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

    def accepts_frame(self, frame: CellFrame) -> bool:
        """Whether *frame* has a shape this device takes.

        Core asks before it spends anything on the write (no preemption, no
        floor slot, no dedupe): a refused frame is a failed write. Log why.
        Default: every frame.
        """
        return True

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
            ``failed_regions`` when only part of the board updated;
            ``throttled`` (with ``retry_after_seconds``) only when the device
            itself refused the write for rate. Core fills ``floor_seconds``.
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

    def cache_synced(self, frame: CellFrame | None) -> None:  # noqa: B027 - optional hook
        """Core asked to adopt the read-back just made as what the board shows
        (a startup sync). *frame* is what :meth:`read_current` returned —
        ``None`` when it failed, so a fan-out adopts the parts that did read."""

    def cache_cleared(self) -> None:  # noqa: B027 - optional hook
        """Core forgot what the board shows; its next write goes through."""

    def check_connection(self) -> ConnectionCheck:
        """Probe the device once: success, or a failure class with guidance."""
        return ConnectionCheck(success=True, message="No connection check for this output.")

    def test_connection(self) -> bool:
        """Whether the device answers (the debug page's "connected").
        Defaults to :meth:`check_connection`'s verdict."""
        return self.check_connection().success

    @classmethod
    def discover(cls, timeout: float) -> list[dict]:
        """Devices found on the network, each a dict with at least ``ip`` and
        ``port``. Default: none.

        Declare it ``discover(cls, timeout, hint=None)`` to be handed the
        network hint: the private IPv4 address the user opened FiestaBoard
        at (:data:`~src.outputs.hooks.HINT_HOST`), ``None`` when the browser
        gave none. Search its network first — in Docker bridge mode this
        host's own address is a container network, not the LAN."""
        return []

    def identify(self) -> None:  # noqa: B027 - optional hook
        """Make the physical device show which one it is (flash, blink)."""

    def diagnostics(self) -> list[DiagnosticCheck]:
        """The output's own checks for the diagnostics page. Default: none."""
        return []

    def detect_geometry(self) -> Mapping[str, Any] | None:
        """The device's size, read from the device: ``{"device_type": "panel",
        "rows", "cols"}`` (the ``detect-size`` shape). ``None``: it cannot tell."""
        return None

    # --- board settings actions (plan D13) -------------------------------------------

    def run_action(self, action: str, inputs: Mapping[str, Any]) -> ActionOutcome | Mapping[str, Any] | None:
        """Run a board-settings action the manifest declares (``output.actions``).

        Core calls this on a throwaway instance built from the board's (or the
        draft's) ``output_config`` — never the board's live one — and closes it
        afterwards. The default maps ``test_connection`` → :meth:`check_connection`,
        ``identify`` → :meth:`identify`, ``detect_geometry`` →
        :meth:`detect_geometry`, and any other id to ``action_<id>(inputs)``.
        Override it to dispatch yourself.

        Return an :class:`ActionOutcome` (or a dict of its fields, or ``None``
        for a plain success). ``inputs`` were validated against the action's
        ``input_schema``. Mark credentials you hand back ``secret`` —
        ``ActionField(value, secret=True)`` — so core never logs them and the
        form stores them through its secret path.
        """
        if action == "test_connection":
            return ActionOutcome.from_check(self.check_connection())
        if action == "identify":
            self.identify()
            return ActionOutcome(message="Identify sent.")
        if action == "detect_geometry":
            found = self.detect_geometry()
            if found is None:
                return ActionOutcome(status="error", message="The device did not report its size.")
            return ActionOutcome(message="Size detected.", geometry=found)
        method = getattr(self, f"action_{action}", None)
        if method is None:
            raise NotImplementedError(f"{type(self).__name__} implements no action '{action}'")
        return method(dict(inputs))

    # --- board settings: what core asks the class (plan D13) ---------------------------

    #: The settings-v3 flat fields this output's ``output_config`` is
    #: projected to in every API view of a board, with their defaults. Only
    #: the Vestaboard's settings predate settings v4; ``None`` for every
    #: other output.
    legacy_flat_fields: ClassVar[Mapping[str, Any] | None] = None

    @classmethod
    def handle_action(cls, ctx: Any) -> ActionOutcome | Mapping[str, Any] | None:
        """Run the board-settings action ``ctx.action`` (one the manifest declares).

        *ctx* is an :class:`~src.outputs.hooks.ActionContext`. The default
        answers ``discover`` with :meth:`discover` (the ``timeout`` input,
        clamped to 1–15 s, and the ``hint_host`` input as ``hint`` when
        :meth:`discover` takes one) and every other action with :meth:`run_action` on
        a throwaway instance built from the board's settings. Override it
        when an action needs more: the board's live instance
        (``ctx.with_live``), another device's settings (``ctx.instance(config)``),
        a refusal before anything is contacted (raise
        :class:`~src.outputs.hooks.OutputActionError`).
        """
        if ctx.action == "discover":
            raw = ctx.inputs.get("timeout", 4.0)
            timeout = min(max(float(raw), 1.0), 15.0) if isinstance(raw, (int, float)) else 4.0
            devices = call_discover(cls.discover, timeout, lan_hint(ctx.inputs.get(HINT_HOST)))
            return ActionOutcome(message=f"Found {len(devices)} device(s).", devices=tuple(devices))
        instance = ctx.instance()
        if instance is None:
            raise OutputActionError(400, "Enter the board's connection details first.")
        return instance.run_action(ctx.action, ctx.inputs)

    @classmethod
    def board_status(cls, config: Mapping[str, Any] | None, board: Mapping[str, Any]) -> OutputStatus | None:
        """The board's connection summary from its settings — whatever the
        output knows without contacting the device (plan D13 ``status``).
        Default: ``None``, nothing to say."""
        return None

    @classmethod
    def normalize_config(cls, config: Mapping[str, Any] | None, board: Mapping[str, Any]) -> dict[str, Any]:
        """The ``output_config`` a board stores. Default: a copy, as given."""
        return dict(config) if isinstance(config, Mapping) else {}

    @classmethod
    def mask_config(cls, config: Any, schema: Mapping[str, Any] | None) -> Any:
        """*config* for an API view, every set secret ``"***"`` (a copy).
        Default: the schema's ``secret`` / password fields."""
        from .output_config import mask_output_config

        return mask_output_config(config, schema)

    @classmethod
    def restore_config(cls, incoming: Any, stored: Any, schema: Mapping[str, Any] | None) -> Any:
        """*incoming* with each echoed ``"***"`` restored from *stored*.
        Default: by the schema's secrets, array elements matched by
        ``id``/``name``/``key``."""
        from .output_config import unmask_output_config

        return unmask_output_config(incoming, stored, schema)

    @classmethod
    def masked_config_paths(cls, config: Any, schema: Mapping[str, Any] | None) -> list[str]:
        """The secrets still ``"***"`` in *config* (refused rather than
        stored as a credential). Default: by the schema's secrets."""
        from .output_config import masked_secret_paths

        return masked_secret_paths(config, schema)
