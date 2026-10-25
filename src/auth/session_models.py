"""Persistent sign-in metadata; secret digests never leave the auth layer."""

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class SessionRecord:
    id: str
    digest: str
    username: str
    account_generation: int
    kind: str
    device_name: str
    client_id: str
    app_version: str
    method: str
    created_ms: int
    expires_ms: int
    last_active_ms: int
    revoked_ms: int | None = None

    def summary(self) -> dict:
        def iso(value: int) -> str:
            return datetime.fromtimestamp(value / 1000, UTC).isoformat()

        return {
            "id": self.id,
            "kind": self.kind,
            "device_name": self.device_name,
            "client_id": self.client_id,
            "app_version": self.app_version,
            "method": self.method,
            "created_at": iso(self.created_ms),
            "expires_at": iso(self.expires_ms),
            "last_active_at": iso(self.last_active_ms),
        }
