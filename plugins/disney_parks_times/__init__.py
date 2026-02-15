"""Disney Park Queue Times plugin for FiestaBoard.

Displays wait times for Disney parks and rides from Queue-Times.com.
Data is updated every 5 minutes by the API. Attribution required.
"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

QUEUE_TIMES_BASE = "https://queue-times.com"
DISNEY_GROUP_ID = 2  # Walt Disney Attractions
CACHE_TTL = 300  # 5 minutes
MAX_LINE_LEN = 22
RIDE_ABBR_LEN = 14  # Abbreviated ride name for board display (fits "  Name: 99m" in 22 chars)
TINY_ABBR_LEN = 5  # Very short abbreviation for compact display
# Fixed width in tiles so multiple formatted on one line align (1 color + 5 abbr + 1 space + wait = 8-9; pad to 11 so two fit in 22)
FORMATTED_TILES = 11

# Board color codes for state_color / formatted
COLOR_OPEN = "{66}"   # green - operating normally
COLOR_CLOSED = "{63}"  # red - closed / not operating

# Known tiny abbreviations (max 5 chars) from common Disney fan usage (wdwmagic, touringplans, etc.).
# Keys are lowercase substrings to match in ride name; longest match wins. Sorted alphabetically by key.
_KNOWN_TINY_ABBR: List[tuple] = [
    ("big thunder mountain railroad", "THUND"),
    ("buzz lightyear", "BUZZ"),
    ("carousel of progress", "COP"),
    ("country bear jamboree", "CBJ"),
    ("expedition everest", "EE"),
    ("flight of passage", "FOP"),
    ("frozen ever after", "FRZN"),
    ("guardians of the galaxy", "GOTG"),
    ("haunted mansion", "HM"),
    ("indiana jones", "INDY"),
    ("it's a small world", "SMALL"),
    ("jungle cruise", "JUNGL"),
    ("kilimanjaro safaris", "KS"),
    ("living with the land", "LWTL"),
    ("mickey and minnie's runaway railway", "MMRR"),
    ("millennium falcon", "MFSR"),
    ("mission space", "MS"),
    ("mission: space", "MS"),
    ("na'vi river journey", "NRJ"),
    ("navi river journey", "NRJ"),
    ("peter pan's flight", "PPF"),
    ("pirates of the caribbean", "POTC"),
    ("rise of the resistance", "RISE"),
    ("rock n roller coaster", "RNR"),
    ("rock 'n' roller coaster", "RNR"),
    ("runaway railway", "MMRR"),
    ("seven dwarfs mine train", "7DMT"),
    ("small world", "SMALL"),
    ("soarin", "SOARN"),
    ("soarin'", "SOARN"),
    ("space mountain", "SMNT"),
    ("spaceship earth", "SE"),
    ("splash mountain", "SPLMT"),
    ("star tours", "ST"),
    ("star wars: rise of the resistance", "RISE"),
    ("test track", "TT"),
    ("tower of terror", "TOT"),
    ("toy story mania", "TSMM"),
    ("toy story midway mania", "TSMM"),
    ("twilight zone tower of terror", "TOT"),
]


def _abbreviate_ride_name(name: str, max_len: int = RIDE_ABBR_LEN) -> str:
    """Shorten ride name for display; prefer truncation at word boundary."""
    if not name or len(name) <= max_len:
        return (name or "").strip()
    truncated = name[: max_len + 1].rsplit(" ", 1)
    if len(truncated) == 2 and truncated[0]:
        return truncated[0].strip()
    return name[:max_len].strip()


def _tiny_abbr(name: str, max_len: int = TINY_ABBR_LEN) -> str:
    """Very short ride name (max 5 chars); use known abbreviations when possible.
    Single-rider lines get a trailing '1' so they differ from the main line (e.g. SMNT1 vs SMNT).
    No spaces in the result; always uppercase for board display.
    """
    n = (name or "").strip().lower()
    if not n:
        return ""
    is_single_rider = "single rider" in n
    match = ""
    abbr = ""
    for key_phrase, known in _KNOWN_TINY_ABBR:
        if key_phrase in n and len(key_phrase) > len(match):
            match, abbr = key_phrase, known
    if abbr:
        base = abbr[:max_len].upper()
    else:
        # Fallback: first max_len chars of name, spaces removed, then uppercase for board
        base = "".join((name or "").strip().split())[:max_len].upper()
    if is_single_rider:
        if len(base) < max_len:
            base = (base + "1")[:max_len]
        else:
            base = base[: max_len - 1] + "1"
    return base


# Module-level cache for park names (id -> name)
_park_names_cache: Dict[int, str] = {}
_park_names_cache_time: float = 0


def _get_park_name(park_id: int) -> str:
    """Resolve park_id to display name via parks.json (cached)."""
    global _park_names_cache, _park_names_cache_time
    now = time.time()
    if now - _park_names_cache_time > CACHE_TTL and park_id not in _park_names_cache:
        try:
            resp = requests.get(f"{QUEUE_TIMES_BASE}/parks.json", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            for group in data:
                if group.get("id") == DISNEY_GROUP_ID:
                    for p in group.get("parks", []):
                        _park_names_cache[p["id"]] = p.get("name", str(p["id"]))
                    break
            _park_names_cache_time = now
        except Exception as e:
            logger.warning("Failed to fetch park names: %s", e)
    return _park_names_cache.get(park_id, f"Park {park_id}")


class DisneyParksTimesPlugin(PluginBase):
    """Disney park queue times from Queue-Times.com."""

    def __init__(self, manifest: Dict[str, Any]):
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: float = 0

    @property
    def plugin_id(self) -> str:
        return "disney_parks_times"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors = []
        parks_config = config.get("parks", [])
        if not parks_config:
            errors.append("At least one park with rides is required")
        for i, entry in enumerate(parks_config):
            if not isinstance(entry, dict):
                errors.append(f"Park entry {i + 1} is invalid")
                continue
            ride_ids = entry.get("ride_ids") or []
            if not ride_ids:
                errors.append(f"Park entry {i + 1}: select at least one ride")
        return errors

    def fetch_data(self) -> PluginResult:
        parks_config = self.config.get("parks", [])
        if not parks_config:
            return PluginResult(
                available=False,
                error="No parks configured. Add at least one park and select rides."
            )

        # Optional: use cached result if within TTL
        refresh = self.config.get("refresh_seconds", 300)
        now = time.time()
        if self._cache and (now - self._cache_time) < refresh:
            lines = self._build_formatted_lines(self._cache)
            return PluginResult(
                available=True,
                data=self._cache,
                formatted_lines=lines,
            )

        parks_data: List[Dict[str, Any]] = []
        for entry in parks_config:
            park_id = entry.get("park_id")
            ride_ids = entry.get("ride_ids") or []
            if park_id is None or not ride_ids:
                continue
            try:
                park_id = int(park_id)
            except (TypeError, ValueError):
                continue
            ride_id_set = {int(r) for r in ride_ids if r is not None}
            try:
                resp = requests.get(
                    f"{QUEUE_TIMES_BASE}/parks/{park_id}/queue_times.json",
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning("Queue-Times fetch failed for park %s: %s", park_id, e)
                park_name = _get_park_name(park_id)
                parks_data.append({
                    "park_id": park_id,
                    "park_name": park_name[:22],
                    "rides": [{"ride_id": 0, "ride_name": "Unavailable", "ride_abbr": "Unavail", "tiny_abbr": "Unavl", "wait_time": 0, "is_open": False, "status": "Error", "state_color": "{63}", "formatted": "{63}Unavl --  "}],  # Pad to FORMATTED_TILES (11)
                })
                continue

            park_name = _get_park_name(park_id)
            rides_out: List[Dict[str, Any]] = []
            for land in data.get("lands", []):
                for ride in land.get("rides", []):
                    rid = ride.get("id")
                    if rid not in ride_id_set:
                        continue
                    wait = ride.get("wait_time", 0) or 0
                    is_open = ride.get("is_open", False)
                    status = "Open" if is_open else "Closed"
                    name = (ride.get("name") or str(rid)).strip()
                    ride_abbr = _abbreviate_ride_name(name)
                    tiny_abbr = _tiny_abbr(name)
                    state_color = COLOR_OPEN if is_open else COLOR_CLOSED
                    wait_str = f"{wait}m" if is_open else "--"
                    # No space between color and abbr so the board doesn't show a blank tile
                    base = f"{state_color}{tiny_abbr:<5} {wait_str}"
                    # Pad to fixed tile count so multiple formatted on same line align (color=1 + 5 + 1 + len(wait_str) tiles)
                    tile_count = 1 + 5 + 1 + len(wait_str)
                    pad = max(0, FORMATTED_TILES - tile_count)
                    formatted = base + (" " * pad)
                    rides_out.append({
                        "ride_id": rid,
                        "ride_name": name,
                        "ride_abbr": ride_abbr,
                        "tiny_abbr": tiny_abbr,
                        "wait_time": wait,
                        "is_open": is_open,
                        "status": status,
                        "state_color": state_color,
                        "formatted": formatted,
                    })
            # Keep order of ride_ids from config
            order = {rid: i for i, rid in enumerate(ride_ids)}
            rides_out.sort(key=lambda r: order.get(r["ride_id"], 999))
            parks_data.append({
                "park_id": park_id,
                "park_name": park_name[:22],
                "rides": rides_out,
            })

        if not parks_data:
            return PluginResult(
                available=False,
                error="No park data could be loaded. Check your park and ride selection."
            )

        result_data: Dict[str, Any] = {
            "parks": parks_data,
            "formatted": "Queue Times"[:22],
        }
        self._cache = result_data
        self._cache_time = time.time()
        lines = self._build_formatted_lines(result_data)
        return PluginResult(
            available=True,
            data=result_data,
            formatted_lines=lines,
        )

    def _build_formatted_lines(self, data: Dict[str, Any]) -> List[str]:
        """Build 6-line default display; include attribution."""
        lines: List[str] = []
        lines.append("DISNEY QUEUE TIMES".center(22)[:22])
        flat: List[tuple] = []  # (park_name, ride_abbr, wait_time, is_open)
        for park in data.get("parks", []):
            for ride in park.get("rides", []):
                flat.append((
                    ride.get("ride_abbr") or (ride.get("ride_name") or "")[:RIDE_ABBR_LEN],
                    ride.get("wait_time", 0),
                    ride.get("is_open", False),
                ))
        for rabbr, wait, is_open in flat[:4]:
            if is_open:
                line = f"{rabbr}: {wait}m"
            else:
                line = f"{rabbr}: Closed"
            lines.append(line[:22])
        while len(lines) < 5:
            lines.append("")
        lines.append("Queue-Times.com".ljust(22)[:22])  # Attribution
        return lines[:6]

    def get_formatted_display(self) -> Optional[List[str]]:
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None
        return self._build_formatted_lines(self._cache or {})

    def cleanup(self) -> None:
        self._cache = None
        logger.debug("%s cleanup", self.plugin_id)


Plugin = DisneyParksTimesPlugin
