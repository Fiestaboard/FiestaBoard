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

from .board_client import VALID_STRATEGIES, BoardClient, TransitionStrategy
from .devices import (
    note_array_dimensions,
    slice_note_array_grid,
    stitch_note_array_grid,
)

logger = logging.getLogger(__name__)

# Cap concurrent tile POSTs; an 8×8 array should not open 64 sockets at once.
MAX_TILE_WORKERS = 8


class NoteArrayLocalClient:
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
        self._last_characters: list[list[int]] | None = None
        self._last_text: str | None = None
        # Per-tile send results from the most recent send_characters call
        self.last_tile_results: dict[tuple[int, int], tuple[bool, bool]] = {}

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

    @property
    def _dims(self):
        return note_array_dimensions(self.notes_wide, self.notes_tall)

    def send_text(self, text: str, force: bool = False) -> tuple[bool, bool]:
        """Note arrays are characters-only; mirror the cloud client's refusal."""
        logger.error(
            "send_text is not supported for note-array boards; use send_characters()"
        )
        return (False, False)

    def send_characters(
        self,
        characters: list[list[int]],
        strategy: TransitionStrategy | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
    ) -> tuple[bool, bool]:
        """Slice the full grid and fan out one local POST per configured tile.

        Transition params are forwarded to every tile (the Local API supports
        them); each Note animates its own slice.

        Returns (success, was_sent): success only when EVERY configured tile
        accepted its slice — the composite cache is left unset on partial
        failure so the caller retries, and per-tile caches make that retry
        re-POST only the tiles that failed.
        """
        dims = self._dims
        if (
            not isinstance(characters, list)
            or len(characters) != dims.rows
            or any(not isinstance(r, list) or len(r) != dims.cols for r in characters)
        ):
            nrows = len(characters) if isinstance(characters, list) else 0
            ncols = (
                len(characters[0]) if nrows and isinstance(characters[0], list) else 0
            )
            logger.error(
                "Invalid grid for local note array: got %dx%d, need %dx%d",
                nrows,
                ncols,
                dims.rows,
                dims.cols,
            )
            return (False, False)

        if strategy is not None and strategy not in VALID_STRATEGIES:
            logger.error(
                f"Invalid strategy: {strategy}. Must be one of {VALID_STRATEGIES}"
            )
            return (False, False)

        if not self.tile_clients:
            logger.error("Local note array has no configured tiles; cannot send")
            return (False, False)

        if self.skip_unchanged and not force and self._last_characters == characters:
            logger.debug("Character array unchanged, skipping send")
            return (True, False)

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

        with ThreadPoolExecutor(
            max_workers=min(MAX_TILE_WORKERS, len(self.tile_clients))
        ) as pool:
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
            return (False, any_was_sent)

        self._last_characters = [row[:] for row in characters]
        self._last_text = None
        logger.info(
            "Local note-array send complete: %d tiles updated, %d skipped (unchanged)",
            sum(1 for _, was_sent in results.values() if was_sent),
            sum(1 for _, was_sent in results.values() if not was_sent),
        )
        return (True, any_was_sent)

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
            return pos, self.tile_clients[pos].read_current_message(
                sync_cache=sync_cache
            )

        with ThreadPoolExecutor(
            max_workers=min(MAX_TILE_WORKERS, len(self.tile_clients))
        ) as pool:
            reads = dict(pool.map(read_tile, sorted(self.tile_clients)))

        if any(sub is None for sub in reads.values()):
            failed = [pos for pos, sub in reads.items() if sub is None]
            logger.error("Local note-array read failed for tiles: %s", failed)
            return None

        stitched = stitch_note_array_grid(reads, self.notes_wide, self.notes_tall)
        if sync_cache:
            self._last_characters = [row[:] for row in stitched]
            self._last_text = None
        return stitched

    def clear_cache(self) -> None:
        """Clear the composite cache and every tile client's cache."""
        self._last_text = None
        self._last_characters = None
        for client in self.tile_clients.values():
            client.clear_cache()
        logger.debug(
            "Local note-array caches cleared (composite + %d tiles)",
            len(self.tile_clients),
        )

    def get_cache_status(self) -> dict:
        return {
            "has_cached_text": False,
            "has_cached_characters": self._last_characters is not None,
            "skip_unchanged_enabled": self.skip_unchanged,
            "cached_text_preview": None,
        }

    def would_send(
        self, text: str | None = None, characters: list[list[int]] | None = None
    ) -> bool:
        if not self.skip_unchanged:
            return True
        if characters is not None:
            return self._last_characters != characters
        return True

    def test_connection(self) -> bool:
        """True if at least one tile responds (the array is partially usable)."""
        return any(client.test_connection() for client in self.tile_clients.values())

    def test_all_tiles(self) -> dict[tuple[int, int], bool]:
        """Per-tile connectivity map for diagnostics."""

        def test_tile(pos: tuple[int, int]):
            return pos, self.tile_clients[pos].test_connection()

        if not self.tile_clients:
            return {}
        with ThreadPoolExecutor(
            max_workers=min(MAX_TILE_WORKERS, len(self.tile_clients))
        ) as pool:
            return dict(pool.map(test_tile, sorted(self.tile_clients)))
