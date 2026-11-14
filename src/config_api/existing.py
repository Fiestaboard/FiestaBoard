"""Is this display already set up? (H19)

The setup wizard asks before it saves a display: the address (or cloud key)
it is about to use, against every board the hub already has. Read-only, and
deliberately literal:

- **Hosts** compare as written: lower case, without a scheme, a path, a
  trailing dot or surrounding space. No DNS lookup, so ``pixoo.local`` and
  the IP it resolves to are two answers (and the check costs nothing).
- **Ports** only tell two devices apart when both sides name one: a
  note array's tiles can share a host on different ports, and a request
  without a port means "that host, whatever port".
- **Any output.** A board's host is its Vestaboard connection's (and each
  note-array tile's) or an output plugin's ``output_config.host``: one
  address is one device, whichever output drives it.
- **Secrets** (a cloud key, a note-array token) match by constant-time
  comparison and are never returned. An empty or masked (``***``) one
  matches nothing. A local API key is deliberately *not* compared: the host
  already identifies a local board, and comparing keys would only add a
  key-confirmation oracle.
"""

from __future__ import annotations

import hmac
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

from src.settings.board_shape import VESTABOARD, board_view

_MASKED = "***"


def split_host_port(value: Any) -> tuple[str, int | None]:
    """*value* as ``(comparable host, port written into it or None)``:
    ``"HTTP://Pixoo.Local.:7001/"`` is ``("pixoo.local", 7001)``."""
    text = str(value or "").strip().lower()
    if not text:
        return "", None
    if "://" in text:
        text = urlsplit(text).netloc
    text = text.split("/", 1)[0]
    port = None
    if text.startswith("["):  # [v6]:port
        end = text.find("]")
        host, rest = (text[1:end], text[end + 1 :]) if end >= 0 else (text[1:], "")
        port = _port(rest[1:]) if rest.startswith(":") else None
        text = host
    elif text.count(":") == 1:  # host:port
        text, written = text.split(":", 1)
        port = _port(written)
    return text.rstrip("."), port


def normalize_host(value: Any) -> str:
    """*value* as a comparable host: ``"HTTP://Pixoo.Local./"`` is ``"pixoo.local"``."""
    return split_host_port(value)[0]


def _port(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _addresses(board: Mapping[str, Any]) -> Iterable[tuple[str, int | None]]:
    """Every (host, port) *board* drives: its own, its tiles', its output plugin's."""
    view = board_view(board)
    if view.get("output") == VESTABOARD:
        yield normalize_host(view.get("host")), _port(view.get("port"))
        for tile in view.get("tiles") or []:
            if isinstance(tile, Mapping):
                yield normalize_host(tile.get("host")), _port(tile.get("port"))
    config = view.get("output_config")
    if isinstance(config, Mapping):
        yield normalize_host(config.get("host")), _port(config.get("port"))


def _same_secret(given: str | None, stored: Any) -> bool:
    if not given or given == _MASKED or not isinstance(stored, str) or not stored:
        return False
    return hmac.compare_digest(given.encode(), stored.encode())


def _matched(board: Mapping[str, Any], host: str, port: int | None, cloud_key: str | None, token: str | None):
    if host:
        for stored_host, stored_port in _addresses(board):
            if stored_host == host and (port is None or stored_port is None or port == stored_port):
                return "host"
    view = board_view(board)
    if _same_secret(cloud_key, view.get("cloud_key")):
        return "cloud_key"
    if _same_secret(token, view.get("note_array_token")):
        return "note_array_token"
    return None


def existing_boards(
    boards: Iterable[Mapping[str, Any]],
    *,
    host: str | None = None,
    port: int | None = None,
    cloud_key: str | None = None,
    note_array_token: str | None = None,
    exclude_board_id: str | None = None,
) -> list[dict[str, str]]:
    """``[{board_id, name, output, matched}]``: the boards already using this display, each once."""
    wanted, written_port = split_host_port(host)
    if port is None:
        port = written_port  # "host:port" with no port field names that port
    found = []
    for board in boards:
        if not isinstance(board, Mapping) or board.get("id") == exclude_board_id:
            continue
        matched = _matched(board, wanted, port, cloud_key, note_array_token)
        if matched:
            found.append(
                {
                    "board_id": str(board.get("id")),
                    "name": str(board.get("name") or ""),
                    "output": str(board_view(board).get("output") or ""),
                    "matched": matched,
                }
            )
    return found


def hub_existing_boards(**query: Any) -> list[dict[str, str]]:
    """:func:`existing_boards` over this hub's boards."""
    from src.settings.service import get_settings_service

    return existing_boards(get_settings_service().get_board_settings().boards or [], **query)
