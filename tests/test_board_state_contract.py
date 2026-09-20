"""Value-level goldens for the three "what is on the board" surfaces (issue #1912).

Three readers answer the same question — the board's actual flap grid,
selected from FiestaBoard's own caches or, on one surface, a live read:

* ``GET /board/current-message`` — authenticated; poll cache, or a live read
  with ``?force=true`` (primary board only).
* ``GET /panel/{panel_id}/frame`` — unauthenticated TV viewer; **never** a
  network read (a viewer polls every 2s and must not hammer a misconfigured
  physical board).
* MCP ``get_board_content`` — same grid plus a ``source`` field, ``ToolError``
  on failure.

#1912 folds their cache-selection logic into ``src/board_state.py``. That is
a behaviour-touching refactor across three transports — one pointed at
customers' wall displays — so these goldens were RECORDED ON THE UNCHANGED
TREE FIRST and must stay byte-identical through the consolidation. They are
*values*, not shapes: the shape goldens in ``tests/golden/responses/`` cannot
see a ``cached_at`` that silently moved from the poll time to the send time,
or a ``source`` that flipped from ``polled`` to ``last_sent``.

Every scenario drives the real route / tool through a deterministic fake of
the ``DisplayService`` surface the readers consult (``vb_client``, the primary
poll cache, per-board runtimes) and real board clients where the client's own
logic matters (``VirtualBoardClient``'s shape guard). Timestamps are fixed so
the ISO strings are exact.

Regenerating the golden file
----------------------------
Only when a response change is intentional::

    RECORD_BOARD_STATE_GOLDEN=1 pytest tests/test_board_state_contract.py

then review ``git diff tests/golden/responses/board_state.json`` line by line.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.panels.models import Panel
from src.virtual_board_client import VirtualBoardClient

GOLDEN_PATH = Path(__file__).parent / "golden" / "responses" / "board_state.json"
RECORD = os.environ.get("RECORD_BOARD_STATE_GOLDEN") == "1"

REGENERATE_HINT = (
    "Board-state values drifted from tests/golden/responses/board_state.json. "
    "The three readers must keep answering exactly what they answered before "
    "#1912 — fix the code. If the change is intentional, regenerate with:\n"
    "    RECORD_BOARD_STATE_GOLDEN=1 pytest tests/test_board_state_contract.py\n"
    "then review `git diff tests/golden/responses/board_state.json` line by line."
)

# The seams each surface resolves its collaborators through.
DISPLAY_SERVICE = "src.display_runtime.get_service"
PANELS_SERVICE = "src.panels.routes.get_service"
PANEL_SERVICE = "src.panels.routes.get_panel_service"
MCP_SERVICE = "src.api_server.get_service"

# Fixed clocks: 2023-11-14T22:13:20+00:00 and one minute later.
POLLED_AT = 1_700_000_000.0
SENT_AT = 1_700_000_060.0

FLAGSHIP = (6, 22)
NOTE = (3, 15)


def _grid(shape: tuple[int, int], code: int) -> list[list[int]]:
    rows, cols = shape
    return [[code] * cols for _ in range(rows)]


# ---------------------------------------------------------------------------
# Deterministic stand-ins for the DisplayService surface the readers consult
# ---------------------------------------------------------------------------


class _PhysicalClient:
    """A physical board client: last-sent cache plus a scripted live read."""

    is_virtual = False

    def __init__(self, *, last_sent=None, live=None, use_cloud=False):
        self._last_characters = last_sent
        self.use_cloud = use_cloud
        self._live = live
        self.live_reads = 0

    def read_current_message(self, sync_cache: bool = False):
        self.live_reads += 1
        return self._live


class _Runtime:
    def __init__(self, client=None, polled=None, polled_at=None):
        self.client = client
        self.polled_characters = polled
        self.polled_at = polled_at


class _Service:
    """Just the DisplayService surface the three readers touch.

    ``runtimes`` is keyed the way a real install keys it — by settings board
    id, or by the legacy ``__primary__`` sentinel for the primary board on
    installs that predate per-board runtimes.
    """

    def __init__(self, runtimes: dict[str, _Runtime], primary_key: str):
        self.runtimes = runtimes
        self._primary_key = primary_key

    @property
    def vb_client(self):
        rt = self.runtimes.get(self._primary_key)
        return rt.client if rt is not None else None

    @property
    def _polled_characters(self):
        rt = self.runtimes.get(self._primary_key)
        return rt.polled_characters if rt is not None else None

    @_polled_characters.setter
    def _polled_characters(self, value):
        self.runtimes[self._primary_key].polled_characters = value

    @property
    def _polled_at(self):
        rt = self.runtimes.get(self._primary_key)
        return rt.polled_at if rt is not None else None

    @_polled_at.setter
    def _polled_at(self, value):
        self.runtimes[self._primary_key].polled_at = value

    def get_runtime(self, board_id):
        return self.runtimes.get(board_id)

    def get_board_client(self, board_id):
        rt = self.runtimes.get(board_id)
        return rt.client if rt is not None else None


def _virtual(shape_device: str, *, frame=None, displayed=None):
    """An anonymous (instance-local state) virtual client with a fixed send time."""
    client = VirtualBoardClient(device_type=shape_device)
    if frame is not None:
        ok, sent = client.send_characters(frame)
        assert (ok, sent) == (True, True), "seed frame never landed"
        client._state.last_sent_at = SENT_AT
    if displayed is not None:
        # Simulate a re-fit that left an old-shape frame behind.
        client._state.displayed_characters = displayed
    return client


# ---------------------------------------------------------------------------
# Settings: one real service, three boards, patched at the shared singleton
# ---------------------------------------------------------------------------

BOARDS = [
    {"id": "b1", "name": "Living Room", "device_type": "flagship", "api_mode": "local"},
    {"id": "b2", "name": "Kitchen", "device_type": "note", "api_mode": "local"},
    {"id": "vb", "name": "Hall TV", "device_type": "note", "api_mode": "virtual"},
]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    import src.settings.service as settings_module

    svc = settings_module.SettingsService(settings_file=str(tmp_path / "settings.json"))
    svc.set_boards([dict(b) for b in BOARDS])
    monkeypatch.setattr(settings_module, "_settings_service", svc)
    assert svc.get_primary_board_id() == "b1"
    return svc


@pytest.fixture
def client(settings):
    from src.api_server import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Golden bookkeeping
# ---------------------------------------------------------------------------


def _check_or_record(surface: str, records: list[dict[str, Any]]) -> None:
    """Compare *records* for one surface with the golden file (or record them)."""
    if RECORD:
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if GOLDEN_PATH.exists():
            with GOLDEN_PATH.open(encoding="utf-8") as fh:
                existing = json.load(fh).get("surfaces", {})
        existing[surface] = records
        payload = {
            "_comment": (
                "Value-level goldens for the three 'what is on the board' readers "
                "(issue #1912). Recorded on the tree BEFORE the consolidation. Do not "
                "hand-edit: regenerate with "
                "`RECORD_BOARD_STATE_GOLDEN=1 pytest tests/test_board_state_contract.py` "
                "and review the diff."
            ),
            "surfaces": {key: existing[key] for key in sorted(existing)},
        }
        with GOLDEN_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return
    if not GOLDEN_PATH.exists():
        pytest.fail(f"Missing golden file {GOLDEN_PATH}.\n{REGENERATE_HINT}")
    with GOLDEN_PATH.open(encoding="utf-8") as fh:
        golden = json.load(fh)["surfaces"][surface]
    golden_by_label = {r["label"]: r for r in golden}
    current_by_label = {r["label"]: r for r in records}
    assert list(current_by_label) == list(golden_by_label), REGENERATE_HINT
    for label, current in current_by_label.items():
        assert current == golden_by_label[label], (
            f"[{surface}] {label}: value drifted.\n"
            f"golden:  {json.dumps(golden_by_label[label], indent=2, sort_keys=True)}\n"
            f"current: {json.dumps(current, indent=2, sort_keys=True)}\n"
            f"{REGENERATE_HINT}"
        )


def _http(label: str, response, **extra: Any) -> dict[str, Any]:
    return {"label": label, "status": response.status_code, "body": response.json(), **extra}


# ---------------------------------------------------------------------------
# Surface 1 — GET /board/current-message
# ---------------------------------------------------------------------------


def test_current_message_values(client):
    records: list[dict[str, Any]] = []

    def run(label: str, service: _Service, query: str = "") -> _Service:
        with patch(DISPLAY_SERVICE, return_value=service):
            response = client.get(f"/board/current-message{query}")
        primary = service.vb_client
        records.append(
            _http(
                label,
                response,
                live_reads=getattr(primary, "live_reads", 0),
                cache_after=service._polled_characters,
            )
        )
        return service

    def primary(**client_kwargs) -> _Service:
        return _Service(
            {"b1": _Runtime(_PhysicalClient(last_sent=_grid(FLAGSHIP, 1), **client_kwargs))},
            primary_key="b1",
        )

    # -- primary board ------------------------------------------------------
    svc = primary(live=_grid(FLAGSHIP, 3))
    svc._polled_characters, svc._polled_at = _grid(FLAGSHIP, 2), POLLED_AT
    run("primary.polled_cache", svc)

    svc = primary(live=_grid(FLAGSHIP, 3))
    svc._polled_characters, svc._polled_at = _grid(FLAGSHIP, 2), POLLED_AT
    run("primary.polled_cache.by_board_id", svc, "?board_id=b1")

    svc = primary(live=_grid(FLAGSHIP, 3), use_cloud=True)
    svc._polled_characters, svc._polled_at = _grid(FLAGSHIP, 2), POLLED_AT
    run("primary.force_live_read_primes_cache", svc, "?force=true")

    run("primary.no_cache_falls_to_live_read", primary(live=_grid(FLAGSHIP, 3)))

    run("primary.live_read_failure", primary(live=None))

    svc = primary(live=None)
    svc._polled_characters, svc._polled_at = _grid(FLAGSHIP, 2), POLLED_AT
    run("primary.force_live_read_failure_despite_cache", svc, "?force=true")

    svc = _Service({"b1": _Runtime(_virtual("flagship", frame=_grid(FLAGSHIP, 4)))}, primary_key="b1")
    run("primary.virtual_board_live_read", svc)

    svc = _Service({"__primary__": _Runtime(_PhysicalClient(live=_grid(FLAGSHIP, 3)))}, primary_key="__primary__")
    run("primary.sentinel_keyed_runtime.by_board_id", svc, "?board_id=b1")

    # -- secondary board ----------------------------------------------------
    def secondary(rt: _Runtime) -> _Service:
        return _Service({"b1": _Runtime(_PhysicalClient(live=_grid(FLAGSHIP, 3))), "b2": rt}, primary_key="b1")

    b2 = _PhysicalClient(last_sent=_grid(NOTE, 5), live=_grid(NOTE, 6))
    svc = secondary(_Runtime(b2, polled=_grid(NOTE, 7), polled_at=POLLED_AT))
    run("secondary.polled_cache_wins_over_last_sent", svc, "?board_id=b2")

    b2 = _PhysicalClient(last_sent=_grid(NOTE, 5), live=_grid(NOTE, 6), use_cloud=True)
    run("secondary.last_sent_cache", secondary(_Runtime(b2)), "?board_id=b2")

    b2 = _PhysicalClient(last_sent=_grid(NOTE, 5), live=_grid(NOTE, 6))
    svc = secondary(_Runtime(b2))
    run("secondary.force_is_ignored_never_live_reads", svc, "?board_id=b2&force=true")
    records[-1]["secondary_live_reads"] = b2.live_reads

    run("secondary.nothing_sent_yet_is_geometry", secondary(_Runtime(_PhysicalClient())), "?board_id=b2")

    svc = _Service({"b1": _Runtime(_PhysicalClient(live=_grid(FLAGSHIP, 3)))}, primary_key="b1")
    run("secondary.no_runtime_is_geometry", svc, "?board_id=b2")

    svc = secondary(_Runtime(_PhysicalClient(live=_grid(FLAGSHIP, 3))))
    svc.runtimes["vb"] = _Runtime(_virtual("note", frame=_grid(NOTE, 8)))
    run("secondary.virtual_board_frame", svc, "?board_id=vb")

    svc.runtimes["vb"] = _Runtime(_virtual("note", frame=_grid(NOTE, 8), displayed=_grid(FLAGSHIP, 8)))
    run("secondary.virtual_board_stale_shape_frame", svc, "?board_id=vb")

    run("unknown_board", secondary(_Runtime(_PhysicalClient())), "?board_id=nope")

    # -- no client at all ---------------------------------------------------
    run("no_board_client", _Service({}, primary_key="b1"))

    _check_or_record("GET /board/current-message", records)


# ---------------------------------------------------------------------------
# Surface 2 — GET /panel/{panel_id}/frame
# ---------------------------------------------------------------------------


def test_panel_frame_values(client):
    records: list[dict[str, Any]] = []

    def run(label: str, service: _Service | None, board_id: str | None) -> None:
        panels = Mock()
        panels.get_panel_by_ref.return_value = (
            Panel(name="Hall TV", board_id=board_id) if board_id is not None else None
        )
        with patch(PANEL_SERVICE, return_value=panels), patch(PANELS_SERVICE, return_value=service):
            response = client.get("/panel/abc123def456/frame")
        live_reads = 0
        if service is not None:
            live_reads = sum(getattr(rt.client, "live_reads", 0) for rt in service.runtimes.values())
        records.append(_http(label, response, physical_live_reads=live_reads))

    primary_rt = _Runtime(_PhysicalClient(last_sent=_grid(FLAGSHIP, 1), live=_grid(FLAGSHIP, 3)))

    svc = _Service({"b1": primary_rt, "vb": _Runtime(_virtual("note", frame=_grid(NOTE, 8)))}, primary_key="b1")
    run("virtual.frame", svc, "vb")

    svc = _Service({"b1": primary_rt, "vb": _Runtime(_virtual("note"))}, primary_key="b1")
    run("virtual.nothing_sent_yet_is_geometry", svc, "vb")

    stale = _virtual("note", frame=_grid(NOTE, 8), displayed=_grid(FLAGSHIP, 8))
    svc = _Service({"b1": primary_rt, "vb": _Runtime(stale)}, primary_key="b1")
    run("virtual.stale_shape_frame_is_null_not_last_sent", svc, "vb")

    b2 = _PhysicalClient(last_sent=_grid(NOTE, 5), live=_grid(NOTE, 6))
    svc = _Service({"b1": primary_rt, "b2": _Runtime(b2)}, primary_key="b1")
    run("physical.last_sent_cache_never_live_reads", svc, "b2")

    svc = _Service({"b1": primary_rt, "b2": _Runtime(_PhysicalClient(live=_grid(NOTE, 6)))}, primary_key="b1")
    run("physical.nothing_sent_yet_is_geometry", svc, "b2")

    svc = _Service({"__primary__": primary_rt}, primary_key="__primary__")
    run("physical.primary_under_legacy_sentinel_falls_back_to_vb_client", svc, "b1")

    svc = _Service({"b1": primary_rt}, primary_key="b1")
    run("board_missing_from_settings_is_flagship_geometry", svc, "gone")

    run("no_display_service", None, "vb")

    run("unknown_panel", _Service({"b1": primary_rt}, primary_key="b1"), None)

    _check_or_record("GET /panel/{panel_id}/frame", records)


# ---------------------------------------------------------------------------
# Surface 3 — MCP get_board_content
# ---------------------------------------------------------------------------


def _call_tool(mcp: Any, **kwargs: Any) -> dict[str, Any]:
    from mcp.server.mcpserver.exceptions import ToolError

    tool = mcp._tool_manager._tools["get_board_content"]
    try:
        result = tool.fn(**kwargs)
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
    except ToolError as exc:
        return {"error": str(exc)}
    return {"result": result}


def test_mcp_get_board_content_values(settings):
    pytest.importorskip("mcp", reason="mcp package not installed")
    from src.mcp_server import _build_mcp_server

    mcp = _build_mcp_server()
    assert mcp is not None
    records: list[dict[str, Any]] = []

    def run(label: str, service: _Service | None, **kwargs: Any) -> None:
        with patch(MCP_SERVICE, return_value=service):
            outcome = _call_tool(mcp, **kwargs)
        live_reads = 0
        if service is not None:
            live_reads = sum(getattr(rt.client, "live_reads", 0) for rt in service.runtimes.values())
        records.append({"label": label, **outcome, "live_reads": live_reads})

    def primary(**client_kwargs) -> _Service:
        return _Service({"b1": _Runtime(_PhysicalClient(**client_kwargs))}, primary_key="b1")

    svc = primary(last_sent=_grid(FLAGSHIP, 1), live=_grid(FLAGSHIP, 3))
    svc._polled_characters, svc._polled_at = _grid(FLAGSHIP, 2), POLLED_AT
    run("primary.polled_cache", svc)
    run("primary.polled_cache.by_board_id", svc, board_id="b1")

    run("primary.last_sent_cache", primary(last_sent=_grid(FLAGSHIP, 1), live=_grid(FLAGSHIP, 3)))

    run("primary.nothing_observed_is_null", primary(live=_grid(FLAGSHIP, 3)))

    svc = _Service({"__primary__": _Runtime(_PhysicalClient(last_sent=_grid(FLAGSHIP, 1)))}, primary_key="__primary__")
    run("primary.sentinel_keyed_runtime.by_board_id", svc, board_id="b1")

    b2 = _PhysicalClient(last_sent=_grid(NOTE, 5), live=_grid(NOTE, 6))
    svc = _Service(
        {"b1": _Runtime(_PhysicalClient()), "b2": _Runtime(b2, polled=_grid(NOTE, 7), polled_at=POLLED_AT)},
        primary_key="b1",
    )
    run("secondary.polled_cache_wins_over_last_sent", svc, board_id="b2")

    b2 = _PhysicalClient(last_sent=_grid(NOTE, 5), live=_grid(NOTE, 6))
    run(
        "secondary.last_sent_cache",
        _Service({"b1": _Runtime(_PhysicalClient()), "b2": _Runtime(b2)}, primary_key="b1"),
        board_id="b2",
    )

    run(
        "secondary.nothing_sent_yet_is_null",
        _Service({"b1": _Runtime(_PhysicalClient()), "b2": _Runtime(_PhysicalClient())}, primary_key="b1"),
        board_id="b2",
    )

    run("secondary.no_runtime_is_null", _Service({"b1": _Runtime(_PhysicalClient())}, primary_key="b1"), board_id="b2")

    svc = _Service(
        {"b1": _Runtime(_PhysicalClient()), "vb": _Runtime(_virtual("note", frame=_grid(NOTE, 8)))}, primary_key="b1"
    )
    run("secondary.virtual_board_frame", svc, board_id="vb")

    stale = _virtual("note", frame=_grid(NOTE, 8), displayed=_grid(FLAGSHIP, 8))
    run(
        "secondary.virtual_board_stale_shape_frame",
        _Service({"b1": _Runtime(_PhysicalClient()), "vb": _Runtime(stale)}, primary_key="b1"),
        board_id="vb",
    )

    run("unknown_board", _Service({"b1": _Runtime(_PhysicalClient())}, primary_key="b1"), board_id="nope")

    run("no_display_service", None)

    _check_or_record("MCP get_board_content", records)
