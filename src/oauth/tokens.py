"""Token storage: ``data/oauth_tokens.json``, owner-readable only.

One record per connection, keyed by the plugin's registry key
(``spotify`` or ``spotify:kitchen``). A connection belongs to exactly one
plugin instance; two plugins that talk to the same provider each hold their
own tokens and can be disconnected independently.

Tokens never leave this process: nothing here is serialised into an API
response, and the file is not in ``src/backup/service.py``'s allow-list, so
it is never written into a downloadable backup either.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.atomic_io import write_json_atomic
from src.paths import get_data_dir

logger = logging.getLogger(__name__)

TOKENS_FILENAME = "oauth_tokens.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TokenSet:
    """The tokens held for one connection."""

    access_token: str
    token_type: str = "Bearer"
    refresh_token: str = ""
    #: Epoch seconds, or ``None`` when the provider gave no lifetime.
    expires_at: float | None = None
    scopes: tuple[str, ...] = ()
    obtained_at: float = 0.0
    #: Set when a refresh was refused; the user has to connect again.
    needs_reauthorization: bool = False

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> TokenSet:
        return cls(
            access_token=str(record.get("access_token", "")),
            token_type=str(record.get("token_type", "Bearer")),
            refresh_token=str(record.get("refresh_token", "")),
            expires_at=record.get("expires_at"),
            scopes=tuple(record.get("scopes", ())),
            obtained_at=float(record.get("obtained_at", 0.0)),
            needs_reauthorization=bool(record.get("needs_reauthorization", False)),
        )

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["scopes"] = list(self.scopes)
        return record


class TokenStore:
    """Thread-safe store of :class:`TokenSet` by connection id."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else get_data_dir() / TOKENS_FILENAME
        self._lock = threading.RLock()
        self._connections: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Could not read %s (%s); starting with no connections", self._path, exc)
            return {}
        connections = data.get("connections") if isinstance(data, dict) else None
        return dict(connections) if isinstance(connections, dict) else {}

    def _save(self) -> None:
        # private=True: owner-only from the moment the staging file exists.
        write_json_atomic(
            self._path,
            {"schema_version": SCHEMA_VERSION, "connections": self._connections},
            private=True,
        )

    def get(self, connection_id: str) -> TokenSet | None:
        with self._lock:
            record = self._connections.get(connection_id)
        return TokenSet.from_record(record) if record else None

    def put(self, connection_id: str, tokens: TokenSet) -> None:
        with self._lock:
            self._connections[connection_id] = tokens.to_record()
            self._save()

    def delete(self, connection_id: str) -> bool:
        """Forget a connection's tokens. Returns whether any were stored."""
        with self._lock:
            if self._connections.pop(connection_id, None) is None:
                return False
            self._save()
            return True

    def ids(self) -> list[str]:
        with self._lock:
            return sorted(self._connections)
