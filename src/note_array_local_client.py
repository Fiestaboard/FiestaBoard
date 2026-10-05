"""Local-API fan-out client for note arrays.

Drives a W×H note array tile-by-tile over the LAN: the rendered virtual
frame is sliced into per-tile 3×15 subgrids and each physical Note receives
its slice via its own local API endpoint (host + port + key).

Composes plain local :class:`~src.board_client.BoardClient` instances — one
per tile — rather than reimplementing HTTP. Duck-type compatible with
``BoardClient`` for every external access the codebase makes (send/read,
cache management, ``use_cloud`` for read-poll interval selection).
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .board_client import (
    LOCAL_READ_BACK,
    VALID_STRATEGIES,
    BoardClient,
    TransitionRenderMixin,
    TransitionStrategy,
)
from .devices import (
    NOTE_COLS,
    NOTE_ROWS,
    note_array_dimensions,
    slice_note_array_grid,
    stitch_note_array_grid,
)
from .outputs.hooks import ReadBack
from .send_outcome import FrameRegion

logger = logging.getLogger(__name__)

# Cap concurrent tile POSTs; an 8×8 array should not open 64 sockets at once.
MAX_TILE_WORKERS = 8


class NoteArrayLocalClient(TransitionRenderMixin):
    """Drives a note array by fanning out to per-tile local BoardClients.

    Args:
        tiles: Configured tile dicts (in-range, enabled, credentialed) —
            pass ``BoardInstance.configured_tiles()``.
        notes_wide: Array width in Notes (cols = notes_wide * 15).
        notes_tall: Array height in Notes (rows = notes_tall * 3).
        skip_unchanged: Skip sending when the full grid is unchanged.
    """

    def __init__(
        self,
        tiles: list[dict],
        notes_wide: int,
        notes_tall: int,
        skip_unchanged: bool = True,
    ):
        self.notes_wide = notes_wide
        self.notes_tall = notes_tall
        # Duck-type surface shared with BoardClient
        self.use_cloud = False  # selects the local read-poll interval
        self.skip_unchanged = skip_unchanged
        self.api_key = ""
        # Per-tile send results from the most recent send_characters call
        self.last_tile_results: dict[tuple[int, int], tuple[bool, bool]] = {}
        # Transition-plugin render state (lock, cancel event, runner slot).
        self._init_transition_state()

        self.tile_clients: dict[tuple[int, int], BoardClient] = {}
        for tile in tiles:
            pos = (tile["row"], tile["col"])
            if pos[0] >= notes_tall or pos[1] >= notes_wide:
                continue
            self.tile_clients[pos] = BoardClient(
                api_key=tile["local_api_key"],
                host=tile["host"],
                use_cloud=False,
                skip_unchanged=True,
                port=tile.get("port") or None,
            )
        logger.info(
            "Local note-array client initialized: %d/%d tiles configured (%d wide × %d tall)",
            len(self.tile_clients),
            notes_wide * notes_tall,
            notes_wide,
            notes_tall,
        )

    def device_key(self) -> str:
        """The array, as the set of LAN endpoints its tiles answer on."""
        endpoints = sorted(f"{client.host}:{client._port}" for client in self.tile_clients.values())
        return "note-array-local:" + ",".join(endpoints)

    @property
    def _dims(self):
        return note_array_dimensions(self.notes_wide, self.notes_tall)

    @staticmethod
    def _tile_region(pos: tuple[int, int]) -> FrameRegion:
        """The cells tile *pos* (row, col in Notes) shows on the full grid."""
        return FrameRegion(row=pos[0] * NOTE_ROWS, col=pos[1] * NOTE_COLS, rows=NOTE_ROWS, cols=NOTE_COLS)

    def send_text(self, text: str, force: bool = False, *, with_outcome: bool = False) -> Any:
        """Note arrays are characters-only; mirror the cloud client's refusal."""
        logger.error("send_text is not supported for note-array boards; use send_characters()")
        return self._outcome(False, False, with_outcome=with_outcome)

    def send_characters(
        self,
        characters: list[list[int]],
        strategy: TransitionStrategy | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
        *,
        with_outcome: bool = False,
    ) -> Any:
        """Slice the full grid and fan out one local POST per configured tile.

        Transition params are forwarded to every tile (the Local API supports
        them); each Note animates its own slice.

        Returns (success, was_sent): success only when EVERY configured tile
        accepted its slice — the composite cache is left unset on partial
        failure so the caller retries, and per-tile caches make that retry
        re-POST only the tiles that failed.

        With ``with_outcome`` the same verdict comes back as a
        :class:`~src.send_outcome.SendOutcome` — ``render()`` forwards the
        keyword from send-message, the v1 grid send, MCP and debug writes.
        Local tiles have no send floor, so it is never throttled.
        """
        dims = self._dims
        if (
            not isinstance(characters, list)
            or len(characters) != dims.rows
            or any(not isinstance(r, list) or len(r) != dims.cols for r in characters)
        ):
            nrows = len(characters) if isinstance(characters, list) else 0
            ncols = len(characters[0]) if nrows and isinstance(characters[0], list) else 0
            logger.error(
                "Invalid grid for local note array: got %dx%d, need %dx%d",
                nrows,
                ncols,
                dims.rows,
                dims.cols,
            )
            return self._outcome(False, False, with_outcome=with_outcome)

        if strategy is not None and strategy not in VALID_STRATEGIES:
            logger.error(f"Invalid strategy: {strategy}. Must be one of {VALID_STRATEGIES}")
            return self._outcome(False, False, with_outcome=with_outcome)

        if not self.tile_clients:
            logger.error("Local note array has no configured tiles; cannot send")
            return self._outcome(False, False, with_outcome=with_outcome)

        # One runtime write: preempts the in-flight transition when called
        # directly, and holds the board's send lock across the whole fan-out.
        with self._output_runtime.write():
            if self.skip_unchanged and not force and self._frames.matches(characters):
                logger.debug("Character array unchanged, skipping send")
                return self._outcome(True, False, with_outcome=with_outcome)

            subgrids = slice_note_array_grid(characters, self.notes_wide, self.notes_tall)

            def send_tile(
                pos: tuple[int, int],
            ) -> tuple[tuple[int, int], tuple[bool, bool]]:
                client = self.tile_clients[pos]
                result = client.send_characters(
                    subgrids[pos],
                    strategy=strategy,
                    step_interval_ms=step_interval_ms,
                    step_size=step_size,
                    force=force,
                )
                return pos, result

            with ThreadPoolExecutor(max_workers=min(MAX_TILE_WORKERS, len(self.tile_clients))) as pool:
                results = dict(pool.map(send_tile, sorted(self.tile_clients)))

            self.last_tile_results = results
            failed = [pos for pos, (ok, _) in results.items() if not ok]
            any_was_sent = any(was_sent for _, was_sent in results.values())

            if failed:
                for pos in failed:
                    client = self.tile_clients[pos]
                    logger.error(
                        "Tile (row=%d, col=%d) at %s failed to accept its slice",
                        pos[0],
                        pos[1],
                        getattr(client, "host", "?"),
                    )
                # Leave the composite cache unset so the caller retries; tiles
                # that succeeded keep their own cache and will skip the re-send.
                # A tile that took its slice (sent, or already showing it) while
                # another failed leaves the board half-updated: a partial write.
                return self._outcome(
                    False,
                    any_was_sent,
                    with_outcome=with_outcome,
                    partial=len(failed) < len(results),
                    failed_regions=tuple(self._tile_region(pos) for pos in sorted(failed)),
                )

            self._frames.record_sent(characters)
            logger.info(
                "Local note-array send complete: %d tiles updated, %d skipped (unchanged)",
                sum(1 for _, was_sent in results.values() if was_sent),
                sum(1 for _, was_sent in results.values() if not was_sent),
            )
            return self._outcome(True, any_was_sent, with_outcome=with_outcome)

    def identify_tiles(self, positions: list[tuple[int, int]]) -> dict[tuple[int, int], bool]:
        """Flash each tile's slot label onto that tile only, forced.

        One write of this board, under its runtime (the in-flight run is
        preempted and the send lock held), so it never interleaves with the
        engine's sends. Returns ``{(row, col): success}``; a position with no
        configured tile, or whose tile raised, is ``False``.
        """
        from .devices import identify_pattern

        def flash(pos: tuple[int, int]) -> tuple[tuple[int, int], bool]:
            client = self.tile_clients.get(pos)
            if client is None:
                return pos, False
            try:
                success, _ = client.send_characters(identify_pattern(pos[0], pos[1], self.notes_wide), force=True)
            except Exception as exc:  # one tile's failure must not abort the rest
                logger.error("Identify failed for tile (%d,%d): %s", pos[0], pos[1], exc)
                success = False
            return pos, bool(success)

        if not positions:
            return {}
        with (
            self._output_runtime.write(),
            ThreadPoolExecutor(max_workers=min(MAX_TILE_WORKERS, len(positions))) as pool,
        ):
            return dict(pool.map(flash, positions))

    def read_current_message(self, sync_cache: bool = False) -> list[list[int]] | None:
        """Read every tile and stitch the full grid.

        Returns None unless the array is fully assigned AND every tile read
        succeeds — a partially-stitched grid would poison the skip-unchanged
        cache and misreport board state.
        """
        total_slots = self.notes_wide * self.notes_tall
        if len(self.tile_clients) < total_slots:
            logger.debug(
                "Local note-array read skipped: %d/%d tiles assigned",
                len(self.tile_clients),
                total_slots,
            )
            return None

        def read_tile(pos: tuple[int, int]):
            return pos, self.tile_clients[pos].read_current_message(sync_cache=sync_cache)

        with ThreadPoolExecutor(max_workers=min(MAX_TILE_WORKERS, len(self.tile_clients))) as pool:
            reads = dict(pool.map(read_tile, sorted(self.tile_clients)))

        if any(sub is None for sub in reads.values()):
            failed = [pos for pos, sub in reads.items() if sub is None]
            logger.error("Local note-array read failed for tiles: %s", failed)
            return None

        stitched = stitch_note_array_grid(reads, self.notes_wide, self.notes_tall)
        if sync_cache:
            self._frames.record_read(stitched)
        return stitched

    def clear_cache(self) -> None:
        """Clear the composite cache and every tile client's cache."""
        self._frames.forget()
        for client in self.tile_clients.values():
            client.clear_cache()
        logger.debug(
            "Local note-array caches cleared (composite + %d tiles)",
            len(self.tile_clients),
        )

    def get_cache_status(self) -> dict:
        return {
            "has_cached_text": False,
            "has_cached_characters": self._frames.characters is not None,
            "skip_unchanged_enabled": self.skip_unchanged,
            "cached_text_preview": None,
        }

    def would_send(self, text: str | None = None, characters: list[list[int]] | None = None) -> bool:
        if not self.skip_unchanged:
            return True
        if characters is not None:
            return not self._frames.matches(characters)
        return True

    def test_connection(self) -> bool:
        """True if at least one tile responds (the array is partially usable)."""
        return any(client.test_connection() for client in self.tile_clients.values())

    @property
    def read_back(self) -> ReadBack:
        """Every tile is read over the LAN."""
        return LOCAL_READ_BACK

    @property
    def connection_label(self) -> str:
        """The tiles are driven over the Local API."""
        return "Local API"
