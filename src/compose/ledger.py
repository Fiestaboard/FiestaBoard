"""Bounded durable UUID outcomes. A cached result never dispatches hardware again."""

import copy
import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from src.paths import get_data_dir
from src.storage.json_store import JsonStore

from .models import ComposeReceipt, ComposeRequest, instant


class ComposeRequestConflict(ValueError):
    pass


class ComposeHistoryFull(ValueError):
    pass


def fingerprint(request: ComposeRequest) -> str:
    encoded = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def actor_digest(actor: str) -> str:
    return hashlib.sha256(actor.encode()).hexdigest()


class ComposeLedger:
    def __init__(self, path: str | Path, *, maximum_records: int = 512):
        self._store = JsonStore(path, current_schema_version=1, label="Compose request outcomes")
        self.maximum_records = maximum_records
        raw = self._store.load()
        if raw is None:
            raw = {"records": {}}
        if not isinstance(raw, dict) or not isinstance(raw.get("records"), dict):
            raise ValueError("Compose request history is unavailable")
        if len(raw["records"]) > maximum_records:
            raise ValueError("Compose request history exceeds its bound")
        self._records = copy.deepcopy(raw["records"])
        interrupted = False
        for key, record in self._records.items():
            try:
                receipt = ComposeReceipt.model_validate(record["receipt"])
                if (
                    str(receipt.request_id) != key
                    or not isinstance(record.get("fingerprint"), str)
                    or not isinstance(record.get("actor"), str)
                    or not isinstance(record.get("created_at"), str)
                ):
                    raise ValueError("Invalid record")
                instant(record["created_at"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("Compose request history is unavailable") from None
            if receipt.status in {"preparing", "dispatching"}:
                record["receipt"] = receipt.model_copy(
                    update={
                        "status": "unknown",
                        "sent": None,
                        "reason": "The hub restarted before this outcome was recorded",
                    }
                ).model_dump(mode="json")
                interrupted = True
        if interrupted:
            self._persist(self._records)

    def _persist(self, records: dict) -> None:
        self._store.save({"records": records})
        self._records = records

    def _matching(self, request: ComposeRequest, board_id: str) -> dict:
        record = self._records.get(str(request.request_id))
        if record is None or record["fingerprint"] != fingerprint(request) or record["receipt"]["board_id"] != board_id:
            raise ComposeRequestConflict("Compose request identity does not match")
        return record

    def begin(
        self, request: ComposeRequest, *, board_id: str, actor: str, now: datetime | None = None
    ) -> tuple[ComposeReceipt, bool]:
        now = now or datetime.now(UTC)
        with self._store.lock:
            existing = self._records.get(str(request.request_id))
            if existing is not None:
                record = self._matching(request, board_id)
                if record["actor"] != actor_digest(actor):
                    raise ComposeRequestConflict("Compose request identity does not match")
                return ComposeReceipt.model_validate(record["receipt"]), False
            request.validate_admission(now=now)
            cutoff = (now - timedelta(days=2)).isoformat()
            records = {
                key: copy.deepcopy(value)
                for key, value in self._records.items()
                if value["created_at"] >= cutoff or value["receipt"]["status"] in {"held", "dispatching"}
            }
            if len(records) >= self.maximum_records:
                raise ComposeHistoryFull("Compose request history is full; no request was sent")
            receipt = ComposeReceipt(
                request_id=request.request_id, board_id=board_id, status="preparing", duration=request.duration
            )
            records[str(request.request_id)] = {
                "fingerprint": fingerprint(request),
                "actor": actor_digest(actor),
                "created_at": now.isoformat(),
                "receipt": receipt.model_dump(mode="json"),
            }
            self._persist(records)
            return receipt, True

    def get(self, request_id: UUID, *, board_id: str, actor: str) -> ComposeReceipt | None:
        with self._store.lock:
            record = self._records.get(str(request_id))
            if record is None:
                return None
            if record["actor"] != actor_digest(actor) or record["receipt"]["board_id"] != board_id:
                raise ComposeRequestConflict("Compose request identity does not match")
            return ComposeReceipt.model_validate(record["receipt"])

    def status(self, request: ComposeRequest, *, board_id: str) -> ComposeReceipt:
        with self._store.lock:
            return ComposeReceipt.model_validate(self._matching(request, board_id)["receipt"])

    def update(self, request: ComposeRequest, *, board_id: str, **values) -> ComposeReceipt:
        with self._store.lock:
            current = self._matching(request, board_id)
            receipt = ComposeReceipt.model_validate(current["receipt"])
            records = copy.deepcopy(self._records)
            result = ComposeReceipt.model_validate({**receipt.model_dump(mode="json"), **values})
            records[str(request.request_id)]["receipt"] = result.model_dump(mode="json")
            self._persist(records)
            return result

    def reconcile_held(self, *, board_id: str, current_request_id: str | None) -> None:
        """Caller holds settings; terminal receipts never become physical retries."""
        with self._store.lock:
            records = copy.deepcopy(self._records)
            changed = False
            for key, record in records.items():
                receipt = record["receipt"]
                if receipt["board_id"] == board_id and receipt["status"] == "held" and key != current_request_id:
                    receipt.update(
                        status="superseded",
                        sent=False,
                        held_until=None,
                        reason="This intent is no longer held for delivery",
                    )
                    changed = True
            if changed:
                self._persist(records)

    def mark_dispatching(self, request: ComposeRequest, *, board_id: str) -> bool:
        with self._store.lock:
            if self.status(request, board_id=board_id).status not in {"preparing", "held"}:
                return False
            self.update(request, board_id=board_id, status="dispatching", sent=None, held_until=None)
            return True

    def mark_held(self, request: ComposeRequest, *, board_id: str, held_until: str | None) -> ComposeReceipt:
        return self.update(
            request,
            board_id=board_id,
            status="held",
            sent=False,
            held_until=held_until,
            reason="Held until silence ends; the requested duration starts on accepted delivery",
        )

    def delivered(self, request: ComposeRequest, *, board_id: str, released_at: datetime, sent: bool) -> ComposeReceipt:
        with self._store.lock:
            current = self.status(request, board_id=board_id)
            if current.status not in {"preparing", "dispatching", "held"}:
                return current
            expiry = request.expires_at(released_at=released_at)
            return self.update(
                request,
                board_id=board_id,
                status="sent" if sent else "unchanged",
                sent=sent,
                started_at=released_at.isoformat(),
                expires_at=expiry,
                reason=None if sent else "The display already showed this content",
            )


_ledger: ComposeLedger | None = None
_ledger_lock = threading.Lock()


def get_compose_ledger() -> ComposeLedger:
    global _ledger
    path = get_data_dir() / "compose_requests.json"
    with _ledger_lock:
        if _ledger is None or _ledger._store.path != path:
            _ledger = ComposeLedger(path)
        return _ledger
