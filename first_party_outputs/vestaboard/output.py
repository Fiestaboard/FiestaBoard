"""The Vestaboard output: one instance drives one board.

Four ways to reach a Vestaboard (:mod:`.connection`):

- **Local API** — a Flagship or Note on the LAN; the only one that animates
  device-native transitions; unfloored; read back over the LAN.
- **RW Cloud API** — through Vestaboard's cloud; one message per 15 s.
- **Note-array Cloud API** — a note array through Vestaboard's cloud, with
  its token; one message per 15 s; no transitions.
- **Local tiles** — a note array on the Local API, one POST per Note
  (:mod:`.tiles`).

FiestaBoard core keeps the policy (send lock, preemption, the 15 s floor,
dedupe, the last-frame store, transitions); this class moves frames, with
every request through ``self.http``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import logging
import math
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import requests

from src.plugins import (
    ActionField,
    ActionOutcome,
    ConnectionCheck,
    DiagnosticCheck,
    OutputPluginBase,
    ReadBack,
    WriteResult,
)

from . import diagnostics as _diagnostics
from . import discovery as _discovery
from . import local_api as _local_api
from . import transport
from .connection import Connection, board_config, resolve
from .probe import probe
from .tiles import TileArray, local_payload, post_with_retry, transition_info
from .transport import (
    CLOUD_MIN_SEND_INTERVAL,
    CLOUD_REQUEST_TIMEOUT,
    LOCAL_REQUEST_TIMEOUT,
    NOTE_ARRAY_MIN_SEND_INTERVAL,
    NOTE_COLS,
    NOTE_ROWS,
    VALID_STRATEGIES,
    is_valid_character_grid,
    is_valid_note_array_grid,
    parse_read_message_payload,
    retry_after_seconds,
)

logger = logging.getLogger(__name__)

#: Reading a board back: a LAN call locally, a cloud call otherwise; how
#: often core's board-state poll does it by default.
LOCAL_READ_BACK = ReadBack(supported=True, cost="cheap", suggested_interval_s=30)
CLOUD_READ_BACK = ReadBack(supported=True, cost="network", suggested_interval_s=180)

#: The note-array presets a detected size is matched against (labels shown
#: by the size detector).
_NOTE_ARRAY_PRESETS = (
    ("2 side-by-side", 2, 1),
    ("4 side-by-side", 4, 1),
    ("2 stacked", 1, 2),
    ("4 stacked", 1, 4),
    ("2×2 grid", 2, 2),
)


def credential_digest(secret: str) -> str:
    """A short, stable, non-reversible id for a credential, for device keys
    (which appear in logs, where a key never may)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


def classify_grid(rows: int, cols: int) -> dict[str, Any] | None:
    """A read-back grid's size as a board shape (the ``detect-size`` shape),
    or ``None`` when no Vestaboard is that size."""
    if (rows, cols) == transport.FLAGSHIP:
        return {"device_type": "flagship", "rows": rows, "cols": cols}
    if (rows, cols) == transport.NOTE:
        return {"device_type": "note", "rows": rows, "cols": cols}
    if not is_valid_note_array_grid(rows, cols):
        return None
    wide, tall = cols // NOTE_COLS, rows // NOTE_ROWS
    preset = next((label for label, w, t in _NOTE_ARRAY_PRESETS if (w, t) == (wide, tall)), None)
    return {
        "device_type": "note_array",
        "rows": rows,
        "cols": cols,
        "notes_wide": wide,
        "notes_tall": tall,
        "matched_preset": preset,
    }


class VestaboardOutput(OutputPluginBase):
    """A Vestaboard Flagship, Note or Note array, local or cloud."""

    plugin_id = "vestaboard"

    #: The diagnostics summary when every check — FiestaBoard's and ours — passed.
    DIAGNOSTICS_ALL_CLEAR = _diagnostics.ALL_CLEAR_SUMMARY

    def __init__(self, board_id: str | None, config: dict[str, Any]) -> None:
        super().__init__(board_id, config)
        connection = resolve(self.config)
        if connection is None:
            raise ValueError("The Vestaboard connection is not configured")
        self.connection: Connection = connection
        self._array: TileArray | None = None
        mode = connection.mode
        if mode == "local":
            logger.info(
                f"Board client initialized with Local API at {connection.host}:{connection.port} (skip_unchanged=True)"
            )
        elif mode != "local_tiles":
            logger.info("Board client initialized with Cloud API (skip_unchanged=True)")

    # --- settings and capabilities ---------------------------------------------------

    @classmethod
    def config_from_board(cls, board: Mapping[str, Any]) -> dict[str, Any] | None:
        """A saved board's flat Vestaboard fields (settings v3); ``None`` when
        they make no usable connection."""
        config = board_config(board)
        return config if resolve(config) is not None else None

    @classmethod
    def declared_capabilities(cls, manifest: Any) -> Any:
        """A split-flap pushed over HTTP. Core streams a transition plugin's
        frames to it one write at a time (the FiestaUI models' "none" is the
        hardware's own cascade); the Local API animates every native strategy
        and the cloud APIs none — :meth:`capabilities` narrows per board."""
        return dataclasses.replace(
            manifest.capabilities,
            technology="split_flap",
            delivery="push",
            animation="stream",
            native_transitions=frozenset(VALID_STRATEGIES),
            min_interval_ms=0,
            read_back=None,
            device_models=(),
            charset=None,
            max_frames=None,
            write_timeout_ms=None,
        )

    def capabilities(self) -> Any:
        if self._output_manifest is None:
            raise RuntimeError("VestaboardOutput: no manifest bound")
        declared = self.declared_capabilities(self._output_manifest)
        mode = self.connection.mode
        if mode == "cloud":
            floor_ms = int(CLOUD_MIN_SEND_INTERVAL * 1000)
            return dataclasses.replace(
                declared, native_transitions=frozenset(), min_interval_ms=floor_ms, read_back=CLOUD_READ_BACK
            )
        if mode == "note_array_cloud":
            floor_ms = int(NOTE_ARRAY_MIN_SEND_INTERVAL * 1000)
            return dataclasses.replace(
                declared, native_transitions=frozenset(), min_interval_ms=floor_ms, read_back=CLOUD_READ_BACK
            )
        return dataclasses.replace(declared, read_back=LOCAL_READ_BACK)

    def connection_label(self) -> str:
        """``"Cloud API"`` or ``"Local API"`` (MQTT ``board_api_mode``)."""
        return "Cloud API" if self.connection.use_cloud else "Local API"

    def device_key(self) -> str:
        """The device, for the send floor: a cloud board by a hash of its
        credential, a local one by its endpoint, a tile array by its tiles'."""
        connection = self.connection
        if connection.mode == "note_array_cloud":
            return f"vestaboard-note-array-cloud:{credential_digest(connection.key)}"
        if connection.mode == "cloud":
            return f"vestaboard-rw-cloud:{credential_digest(connection.key)}"
        if connection.mode == "local_tiles":
            return self.array.device_key()
        return f"vestaboard-local:{connection.host}:{connection.port}"

    # --- the wire ------------------------------------------------------------------------

    @property
    def array(self) -> TileArray:
        """A local note array's tiles (built on first use, on this instance's ``http``)."""
        if self._array is None:
            connection = self.connection
            self._array = TileArray(connection.tiles, connection.notes_wide, connection.notes_tall, self.http)
        return self._array

    @property
    def last_tile_results(self) -> dict[tuple[int, int], tuple[bool, bool]]:
        """Per-tile ``(success, was_sent)`` of a tile array's last write."""
        return self.array.last_tile_results if self.connection.mode == "local_tiles" else {}

    def _endpoint(self) -> tuple[str, dict[str, str], tuple[float, float]]:
        """``(url, headers, timeout)`` this board writes and reads."""
        connection = self.connection
        json_type = {"Content-Type": "application/json"}
        if connection.mode == "note_array_cloud":
            return (
                transport.CLOUD_NOTE_ARRAY_API_URL,
                {"X-Vestaboard-Token": connection.key, **json_type},
                CLOUD_REQUEST_TIMEOUT,
            )
        if connection.mode == "cloud":
            return (
                transport.CLOUD_API_URL,
                {"X-Vestaboard-Read-Write-Key": connection.key, **json_type},
                CLOUD_REQUEST_TIMEOUT,
            )
        url = f"http://{connection.host}:{connection.port}/local-api/message"
        return url, {"X-Vestaboard-Local-Api-Key": connection.key, **json_type}, LOCAL_REQUEST_TIMEOUT

    def accepts_frame(self, frame: Any) -> bool:
        if self.connection.mode == "local_tiles":
            return self.array.accepts(frame)
        if is_valid_character_grid(frame):
            return True
        num_rows = len(frame) if isinstance(frame, list) else 0
        num_cols = len(frame[0]) if num_rows > 0 and isinstance(frame[0], list) else 0
        logger.error(f"Invalid grid: {num_rows}x{num_cols} is not a supported device size.")
        return False

    def write(self, frame: Any, *, native: Any, cancel: Any) -> WriteResult:
        """POST one character grid: ``{"characters": ...}`` (Local API, with
        any native transition; note-array cloud) or the bare grid (RW cloud)."""
        if not self.accepts_frame(frame):
            return WriteResult(False, False)
        mode = self.connection.mode
        if mode == "local_tiles":
            return self.array.write(frame, native, self.forced)
        url, headers, timeout = self._endpoint()
        if mode == "note_array_cloud":
            if native is not None:
                logger.debug(
                    "Note-array board: transition params (strategy=%r, step_interval_ms=%r, step_size=%r) "
                    "are not supported and will be ignored.",
                    native.strategy,
                    native.step_interval_ms,
                    native.step_size,
                )
                native = None
            payload: Any = {"characters": frame}
        elif mode == "cloud":
            payload = frame
        else:
            payload = local_payload(frame, native)
        try:
            response = post_with_retry(self.http, url, headers, payload, timeout, cancel)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return self._send_failed(e)
        logger.info(f"Character array sent successfully to board{transition_info(native)}")
        return WriteResult(True, True)

    def _send_failed(self, exc: requests.exceptions.RequestException) -> WriteResult:
        """A write that raised. A cloud board answering HTTP 429 is the
        device's own floor: throttled, for the ``Retry-After`` it sent, else
        the declared floor — core keeps the slot closed that long."""
        response = getattr(exc, "response", None)
        if self.connection.use_cloud and response is not None and response.status_code == 429:
            floor = CLOUD_MIN_SEND_INTERVAL if self.connection.mode == "cloud" else NOTE_ARRAY_MIN_SEND_INTERVAL
            retry_after = retry_after_seconds(response, max(1, math.ceil(floor)))
            logger.warning("%s answered HTTP 429 (rate limited); holding sends for %ss", self.device_key(), retry_after)
            return WriteResult(True, False, throttled=True, retry_after_seconds=retry_after)
        logger.error(f"Failed to send character array to board: {exc}")
        if response is not None:
            logger.error(f"Response: {response.text}")
        return WriteResult(False, False)

    def read_current(self) -> list[list[int]] | None:
        """The grid the board shows (Flagship 6x22, Note 3x15, or a note
        array's rows x cols), or ``None`` if the read failed or it is empty."""
        if self.connection.mode == "local_tiles":
            return self.array.read()
        url, headers, timeout = self._endpoint()
        try:
            response = self.http.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return parse_read_message_payload(response.json())
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to read current message: {e}")
            return None

    def cache_synced(self, frame: Any) -> None:
        if self.connection.mode == "local_tiles":
            self.array.adopt_read()

    def cache_cleared(self) -> None:
        if self.connection.mode == "local_tiles":
            self.array.forget()
            logger.debug("Local note-array tile caches cleared (%d tiles)", len(self.array.links))

    # --- probes ------------------------------------------------------------------------

    def test_connection(self) -> bool:
        """True when the board answers a read (a tile array: any tile does)."""
        if self.connection.mode == "local_tiles":
            return self.array.any_reachable()
        try:
            return self.read_current() is not None
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def check_connection(self) -> ConnectionCheck:
        """Probe the board once over this board's own request path: one GET of
        the read endpoint, classified (:mod:`.probe`). ``POST
        /config/board/test`` runs it on a draft (local and RW Cloud
        credentials; the wizard never probes a note array)."""
        connection = self.connection
        if connection.mode == "local_tiles":
            if self.test_connection():
                return ConnectionCheck(success=True, message="Successfully connected to your board!")
            return ConnectionCheck(
                success=False,
                message="Could not connect to the board.",
                failure="unreachable",
                error="Connection error",
            )
        if connection.mode == "note_array_cloud":
            # A note array's token rides the RW Cloud probe, as it always has.
            url = transport.CLOUD_API_URL
            headers = {"X-Vestaboard-Read-Write-Key": connection.key, "Content-Type": "application/json"}
            return probe(self.http, url, headers, CLOUD_REQUEST_TIMEOUT, use_cloud=True)
        url, headers, timeout = self._endpoint()
        return probe(self.http, url, headers, timeout, use_cloud=connection.use_cloud)

    @property
    def identify_tiles(self) -> Any:
        """A tile array's per-tile identify flash (``None`` for any other board)."""
        return self.array.identify if self.connection.mode == "local_tiles" else None

    def identify(self) -> None:
        """Flash every configured tile's position on it (tile arrays only)."""
        if self.connection.mode == "local_tiles":
            self.array.identify(sorted(self.array.links))

    def detect_geometry(self) -> Mapping[str, Any] | None:
        """The board's size, from what it shows now (``None``: blank or unreadable)."""
        if self.connection.mode == "local_tiles":
            return None
        grid = self.read_current()
        if not grid:
            return None
        return classify_grid(len(grid), len(grid[0]))

    def diagnostics(self) -> list[DiagnosticCheck]:
        """This board's connection checks, one line each."""
        section = _diagnostics.diagnose(self.config)
        return [
            DiagnosticCheck(name=name, ok=bool(step.get("ok")), detail=str(step.get("error") or ""))
            for name, step in (section.get("steps") or {}).items()
        ]

    # --- output-level hooks FiestaBoard wires into its registry entry -----------------------

    @classmethod
    def discover(cls, timeout: float) -> list[dict]:
        """Vestaboards on this network: mDNS, then a subnet probe of port 7000."""
        return _discovery.discover(timeout)

    @classmethod
    def diagnose_board(cls, board: Mapping[str, Any]) -> dict:
        """A saved board's section of ``GET /debug/network-diagnostics``."""
        return _diagnostics.diagnose(board)

    @classmethod
    def diagnostics_advice(cls, section: Mapping[str, Any]) -> list[dict]:
        """Plain-English troubleshooting for a failed board section."""
        return _diagnostics.advise(section)

    @classmethod
    def hook_actions(cls) -> dict[str, Any]:
        """Output-level actions FiestaBoard's legacy routes run by name."""

        async def enable_local_api(request: Any) -> dict:
            return await _local_api.exchange_enablement_token(request)

        return {"enable_local_api": enable_local_api}

    # --- board settings actions ----------------------------------------------------------

    def action_enable_local_api(self, inputs: Mapping[str, Any]) -> ActionOutcome:
        """Exchange an enablement token for a Local API key (the key comes back secret)."""
        host = inputs.get("host") or self.connection.host or ""
        request = SimpleNamespace(host=host, enablement_token=inputs.get("enablement_token") or "")
        verdict = asyncio.run(_local_api.exchange_enablement_token(request))
        if not verdict.get("success"):
            guidance = (verdict["error"],) if verdict.get("error") else ()
            return ActionOutcome(status="error", message=verdict.get("message", ""), guidance=guidance)
        return ActionOutcome(
            message=verdict.get("message", ""),
            fields={"api_key": ActionField(value=verdict.get("api_key"), secret=True)},
        )
