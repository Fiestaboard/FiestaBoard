"""A note array on the Local API, driven tile by tile.

The board's frame is sliced into one 3×15 subgrid per Note, and each
physical Note receives its slice through its own Local API endpoint (host,
port, key) — moved from FiestaBoard core's ``src/note_array_local_client.py``.

Each tile keeps its own dedupe of the slice it last took, so a retry after a
partial failure re-POSTs only the tiles that failed; core keeps the whole
board's. A forced write (:attr:`~src.plugins.OutputPluginBase.forced`)
re-sends every tile. Tiles are POSTed on a small thread pool, in position
order.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from src.plugins import FrameRegion, OutputHttp, WriteResult, text_to_board_array

from .connection import Tile
from .transport import (
    LOCAL_REQUEST_TIMEOUT,
    NOTE_COLS,
    NOTE_ROWS,
    SEND_MAX_ATTEMPTS,
    SEND_RETRY_BACKOFF_SECONDS,
    is_retryable_send_error,
    parse_read_message_payload,
)

logger = logging.getLogger(__name__)

#: Cap on concurrent tile requests: an 8×8 array must not open 64 sockets at once.
MAX_TILE_WORKERS = 8

Grid = list[list[int]]
Pos = tuple[int, int]


def slice_grid(grid: Grid, notes_wide: int, notes_tall: int) -> dict[Pos, Grid]:
    """The whole board's grid as one 3×15 subgrid per Note, keyed (row, col)."""
    return {
        (tr, tc): [grid[tr * NOTE_ROWS + i][tc * NOTE_COLS : (tc + 1) * NOTE_COLS] for i in range(NOTE_ROWS)]
        for tr in range(notes_tall)
        for tc in range(notes_wide)
    }


def stitch_grid(subgrids: dict[Pos, Grid], notes_wide: int, notes_tall: int, fill: int = 0) -> Grid:
    """The inverse of :func:`slice_grid`; a missing or malformed slice stays *fill*."""
    grid = [[fill] * (notes_wide * NOTE_COLS) for _ in range(notes_tall * NOTE_ROWS)]
    for (tr, tc), sub in subgrids.items():
        if tr < 0 or tr >= notes_tall or tc < 0 or tc >= notes_wide:
            continue
        if not isinstance(sub, list) or len(sub) != NOTE_ROWS:
            continue
        if any(not isinstance(r, list) or len(r) != NOTE_COLS for r in sub):
            continue
        for i in range(NOTE_ROWS):
            grid[tr * NOTE_ROWS + i][tc * NOTE_COLS : (tc + 1) * NOTE_COLS] = sub[i]
    return grid


def identify_pattern(row: int, col: int, notes_wide: int) -> Grid:
    """The identify flash for one tile: its reading-order position and its
    (row, col), 1-indexed for humans, like an OS monitor arrangement."""
    position = row * notes_wide + col + 1
    return text_to_board_array(f"\nPOSITION {position}\nR{row + 1} C{col + 1}", rows=NOTE_ROWS, cols=NOTE_COLS)


class _TileLink:
    """One Note's Local API endpoint and the slice it last took."""

    def __init__(self, tile: Tile, http: OutputHttp) -> None:
        self.tile = tile
        self.http = http
        self.url = f"http://{tile.host}:{tile.port}/local-api/message"
        self.headers = {"X-Vestaboard-Local-Api-Key": tile.local_api_key, "Content-Type": "application/json"}
        self.last: Grid | None = None
        self._lock = threading.Lock()

    def _post(self, payload: Any) -> requests.Response:
        # A tile's backoff waits on a token of its own, which nothing cancels:
        # a tile's write finishes once begun, as it always has.
        return post_with_retry(self.http, self.url, self.headers, payload, LOCAL_REQUEST_TIMEOUT, threading.Event())

    def send(self, subgrid: Grid, native: Any | None, force: bool) -> tuple[bool, bool]:
        """``(success, was_sent)`` for this tile's slice."""
        with self._lock:
            if not force and self.last == subgrid:
                logger.debug("Character array unchanged, skipping send")
                return True, False
            payload = local_payload(subgrid, native)
            try:
                response = self._post(payload)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to send character array to board: {e}")
                failed = getattr(e, "response", None)
                if failed is not None:
                    logger.error(f"Response: {failed.text}")
                return False, False
            self.last = subgrid
            logger.info(f"Character array sent successfully to board{transition_info(native)}")
            return True, True

    def read(self) -> Grid | None:
        try:
            response = self.http.get(self.url, headers=self.headers, timeout=LOCAL_REQUEST_TIMEOUT)
            response.raise_for_status()
            return parse_read_message_payload(response.json())
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to read current message: {e}")
            return None


def local_payload(frame: Grid, native: Any | None) -> dict[str, Any]:
    """The Local API's write body: ``{"characters": ...}`` plus any native
    transition parameters (``strategy``, ``step_interval_ms``, ``step_size``)."""
    payload: dict[str, Any] = {"characters": frame}
    if native is not None:
        if native.strategy is not None:
            payload["strategy"] = native.strategy
        if native.step_interval_ms is not None:
            payload["step_interval_ms"] = native.step_interval_ms
        if native.step_size is not None:
            payload["step_size"] = native.step_size
    return payload


def transition_info(native: Any | None) -> str:
    """`` with <strategy> transition (<n>ms interval)`` for the send log line."""
    if native is None or not native.strategy:
        return ""
    info = f" with {native.strategy} transition"
    if native.step_interval_ms:
        info += f" ({native.step_interval_ms}ms interval)"
    return info


def post_with_retry(
    http: OutputHttp,
    url: str,
    headers: dict[str, str],
    payload: Any,
    timeout: tuple[float, float],
    cancel: Any,
) -> requests.Response:
    """POST with a single connection-level retry after a short backoff.

    Retries (once) ONLY errors where the board never ACCEPTED the
    connection (:func:`~.transport.is_retryable_send_error`). A
    ``ReadTimeout`` is a board that answered and then went quiet: not
    retried. An HTTP error response is the board answering: returned to the
    caller, never retried. A host outside ``FIESTABOARD_OUTPUTS_ALLOW_HOSTS``
    is a decision, not a flaky connection: never retried. The backoff waits
    on *cancel* (anything with ``wait(seconds) -> bool``), so a preempting
    write abandons the retry promptly.
    """
    from src.plugins import OutputHostBlocked

    last_exc: requests.exceptions.RequestException | None = None
    for attempt in range(1, SEND_MAX_ATTEMPTS + 1):
        try:
            return http.post(url, headers=headers, json=payload, timeout=timeout)
        except OutputHostBlocked:
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            if attempt >= SEND_MAX_ATTEMPTS or not is_retryable_send_error(exc):
                break
            logger.debug(
                "Send attempt %d/%d failed with connection-level error (%s); retrying in %.1fs",
                attempt,
                SEND_MAX_ATTEMPTS,
                exc,
                SEND_RETRY_BACKOFF_SECONDS,
            )
            if cancel.wait(SEND_RETRY_BACKOFF_SECONDS):
                logger.debug("Send retry abandoned: cancel signalled during backoff")
                break
    assert last_exc is not None
    raise last_exc


class TileArray:
    """A local note array's tiles, driven as one board."""

    def __init__(self, tiles: tuple[Tile, ...], notes_wide: int, notes_tall: int, http: OutputHttp) -> None:
        self.notes_wide = notes_wide
        self.notes_tall = notes_tall
        self.links: dict[Pos, _TileLink] = {
            (t.row, t.col): _TileLink(t, http) for t in tiles if t.row < notes_tall and t.col < notes_wide
        }
        #: Per-tile ``(success, was_sent)`` of the most recent write.
        self.last_tile_results: dict[Pos, tuple[bool, bool]] = {}
        self._read_back: dict[Pos, Grid] = {}
        logger.info(
            "Local note-array client initialized: %d/%d tiles configured (%d wide × %d tall)",
            len(self.links),
            notes_wide * notes_tall,
            notes_wide,
            notes_tall,
        )

    @property
    def rows(self) -> int:
        return self.notes_tall * NOTE_ROWS

    @property
    def cols(self) -> int:
        return self.notes_wide * NOTE_COLS

    def device_key(self) -> str:
        """The array, as the set of LAN endpoints its tiles answer on."""
        endpoints = sorted(f"{link.tile.host}:{link.tile.port}" for link in self.links.values())
        return "note-array-local:" + ",".join(endpoints)

    @staticmethod
    def _tile_region(pos: Pos) -> FrameRegion:
        """The cells tile *pos* (row, col in Notes) shows on the whole board."""
        return FrameRegion(row=pos[0] * NOTE_ROWS, col=pos[1] * NOTE_COLS, rows=NOTE_ROWS, cols=NOTE_COLS)

    def accepts(self, frame: Any) -> bool:
        if (
            not isinstance(frame, list)
            or len(frame) != self.rows
            or any(not isinstance(r, list) or len(r) != self.cols for r in frame)
        ):
            nrows = len(frame) if isinstance(frame, list) else 0
            ncols = len(frame[0]) if nrows and isinstance(frame[0], list) else 0
            logger.error("Invalid grid for local note array: got %dx%d, need %dx%d", nrows, ncols, self.rows, self.cols)
            return False
        return True

    def _pool(self, jobs: int) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(max_workers=min(MAX_TILE_WORKERS, jobs))

    def write(self, frame: Grid, native: Any | None, force: bool) -> WriteResult:
        """Slice *frame* and POST each configured tile its slice.

        Native transition parameters go to every tile: each Note animates its
        own slice. Success only when EVERY configured tile took its slice; a
        tile that took it while another failed leaves the board half-updated:
        ``partial``, with the failed tiles' regions.
        """
        if not self.accepts(frame):
            return WriteResult(False, False)
        if not self.links:
            logger.error("Local note array has no configured tiles; cannot send")
            return WriteResult(False, False)
        subgrids = slice_grid(frame, self.notes_wide, self.notes_tall)

        def send_tile(pos: Pos) -> tuple[Pos, tuple[bool, bool]]:
            return pos, self.links[pos].send(subgrids[pos], native, force)

        with self._pool(len(self.links)) as pool:
            results = dict(pool.map(send_tile, sorted(self.links)))

        self.last_tile_results = results
        failed = [pos for pos, (ok, _) in results.items() if not ok]
        any_was_sent = any(was_sent for _, was_sent in results.values())
        if failed:
            for pos in failed:
                logger.error(
                    "Tile (row=%d, col=%d) at %s failed to accept its slice", pos[0], pos[1], self.links[pos].tile.host
                )
            return WriteResult(
                False,
                any_was_sent,
                partial=len(failed) < len(results),
                failed_regions=tuple(self._tile_region(pos) for pos in sorted(failed)),
            )
        logger.info(
            "Local note-array send complete: %d tiles updated, %d skipped (unchanged)",
            sum(1 for _, was_sent in results.values() if was_sent),
            sum(1 for _, was_sent in results.values() if not was_sent),
        )
        return WriteResult(True, any_was_sent)

    def identify(self, positions: list[Pos]) -> dict[Pos, bool]:
        """Flash each tile's slot label onto that tile only, forced.
        ``{(row, col): success}``; a position with no configured tile, or
        whose tile raised, is ``False``."""

        def flash(pos: Pos) -> tuple[Pos, bool]:
            link = self.links.get(pos)
            if link is None:
                return pos, False
            try:
                success, _ = link.send(identify_pattern(pos[0], pos[1], self.notes_wide), None, True)
            except Exception as exc:  # one tile's failure must not abort the rest
                logger.error("Identify failed for tile (%d,%d): %s", pos[0], pos[1], exc)
                success = False
            return pos, bool(success)

        if not positions:
            return {}
        with self._pool(len(positions)) as pool:
            return dict(pool.map(flash, positions))

    def read(self) -> Grid | None:
        """Every tile read and stitched; ``None`` unless the array is fully
        assigned AND every read succeeded (a partial grid would poison the
        dedupe and misreport the board)."""
        total = self.notes_wide * self.notes_tall
        self._read_back = {}
        if len(self.links) < total:
            logger.debug("Local note-array read skipped: %d/%d tiles assigned", len(self.links), total)
            return None

        def read_tile(pos: Pos) -> tuple[Pos, Grid | None]:
            return pos, self.links[pos].read()

        with self._pool(len(self.links)) as pool:
            reads = dict(pool.map(read_tile, sorted(self.links)))
        self._read_back = {pos: sub for pos, sub in reads.items() if sub}
        if any(sub is None for sub in reads.values()):
            failed = [pos for pos, sub in reads.items() if sub is None]
            logger.error("Local note-array read failed for tiles: %s", failed)
            return None
        return stitch_grid(reads, self.notes_wide, self.notes_tall)

    def adopt_read(self) -> None:
        """Each tile that read back now dedupes against what it read."""
        for pos, sub in self._read_back.items():
            self.links[pos].last = sub

    def forget(self) -> None:
        """Every tile's dedupe cleared: the next write re-sends each slice."""
        for link in self.links.values():
            link.last = None

    def any_reachable(self) -> bool:
        """True if at least one tile answers a read (the array is partly usable)."""
        return any(link.read() is not None for link in self.links.values())
