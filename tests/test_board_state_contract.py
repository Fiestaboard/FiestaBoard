"""Value-level goldens for the four "what is on the board" surfaces (issue #1912).

Four readers answer the same question — the board's actual flap grid,
selected from FiestaBoard's own caches or, on one surface, a live read:

* ``GET /board/current-message`` — authenticated; poll cache, or a live read
  with ``?force=true`` (primary board only).
* ``GET /panel/{panel_id}/frame`` — unauthenticated TV viewer; answers what
  FiestaBoard last displayed/sent, immediately, and **never** performs a
  network read (a viewer polls every 2s and must not hammer a misconfigured
  physical board).
* MCP ``get_board_content`` — same grid plus a ``source`` field, ``ToolError``
  on failure.
* ``GET /v1/boards/{board}`` — the public API's merged board read.

#1912 folds their cache-selection logic into ``src/board_state.py``. That is
a behaviour-touching refactor across four transports — one pointed at
customers' wall displays — so these goldens were RECORDED ON THE UNCHANGED
TREE FIRST and must stay byte-identical through the consolidation. They are
*values*, not shapes: the shape goldens in ``tests/golden/responses/`` cannot
see a ``cached_at`` that silently moved from the poll time to the send time,
or a ``source`` that flipped from ``polled`` to ``last_sent``.

Every scenario drives the real route / tool through the deterministic fakes
in ``tests/board_state_fakes.py`` and real board clients where the client's
own logic matters (``VirtualBoardClient``'s shape guard). Timestamps are
fixed so the ISO strings are exact. One scenario per test, so a drift names
the exact behaviour that moved.

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
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.panels.models import Panel
from tests.board_state_fakes import FLAGSHIP, NOTE, PhysicalClient, Runtime, Service, grid, virtual

GOLDEN_PATH = Path(__file__).parent / "golden" / "responses" / "board_state.json"
RECORD = os.environ.get("RECORD_BOARD_STATE_GOLDEN") == "1"

REGENERATE_HINT = (
    "Board-state values drifted from tests/golden/responses/board_state.json. "
    "The readers must keep answering exactly what they answered before "
    "#1912 — fix the code. If the change is intentional, regenerate with:\n"
    "    RECORD_BOARD_STATE_GOLDEN=1 pytest tests/test_board_state_contract.py\n"
    "then review `git diff tests/golden/responses/board_state.json` line by line."
)

# The seams each surface resolves its collaborators through.
DISPLAY_SERVICE = "src.display_runtime.get_service"
PANELS_SERVICE = "src.panels.routes.get_service"
PANEL_SERVICE = "src.panels.routes.get_panel_service"
MCP_SERVICE = "src.api_server.get_service"
V1_SERVICE = "src.api_server.get_service"

# Fixed clocks: 2023-11-14T22:13:20+00:00 and one minute later.
POLLED_AT = 1_700_000_000.0
SENT_AT = 1_700_000_060.0

BOARDS = [
    {"id": "b1", "name": "Living Room", "device_type": "flagship", "api_mode": "local"},
    {"id": "b2", "name": "Kitchen", "device_type": "note", "api_mode": "local"},
    {"id": "vb", "name": "Hall TV", "device_type": "note", "api_mode": "virtual"},
]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """One real settings service, three boards, patched at the shared singleton."""
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


def _load_golden() -> dict[str, dict[str, Any]]:
    if not GOLDEN_PATH.exists():
        return {}
    with GOLDEN_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)["surfaces"]


def _check_or_record(surface: str, label: str, record: dict[str, Any]) -> None:
    """Compare one scenario's record with the golden file (or record it)."""
    if RECORD:
        surfaces = _load_golden()
        surfaces.setdefault(surface, {})[label] = record
        payload = {
            "_comment": (
                "Value-level goldens for the 'what is on the board' readers "
                "(issue #1912). Recorded on the tree BEFORE the consolidation. Do not "
                "hand-edit: regenerate with "
                "`RECORD_BOARD_STATE_GOLDEN=1 pytest tests/test_board_state_contract.py` "
                "and review the diff."
            ),
            "surfaces": {s: dict(sorted(surfaces[s].items())) for s in sorted(surfaces)},
        }
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with GOLDEN_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return
    golden = _load_golden().get(surface, {})
    if label not in golden:
        pytest.fail(f"[{surface}] {label}: no golden record.\n{REGENERATE_HINT}")
    assert record == golden[label], (
        f"[{surface}] {label}: value drifted.\n"
        f"golden:  {json.dumps(golden[label], indent=2, sort_keys=True)}\n"
        f"current: {json.dumps(record, indent=2, sort_keys=True)}\n"
        f"{REGENERATE_HINT}"
    )


def _http(response, **extra: Any) -> dict[str, Any]:
    return {"status": response.status_code, "body": response.json(), **extra}


def _primary(**client_kwargs) -> Service:
    return Service({"b1": Runtime(PhysicalClient(last_sent=grid(FLAGSHIP, 1), **client_kwargs))})


def _with_polled(service: Service, shape=FLAGSHIP, code=2) -> Service:
    service.runtimes["b1"].polled_characters = grid(shape, code)
    service.runtimes["b1"].polled_at = POLLED_AT
    return service


def _secondary(rt: Runtime) -> Service:
    return Service({"b1": Runtime(PhysicalClient(live=grid(FLAGSHIP, 3))), "b2": rt})


# ---------------------------------------------------------------------------
# Surface 1 — GET /board/current-message
# ---------------------------------------------------------------------------

Scenario = Callable[[], tuple[Service, str]]

CURRENT_MESSAGE: dict[str, Scenario] = {
    "primary.polled_cache": lambda: (_with_polled(_primary(live=grid(FLAGSHIP, 3))), ""),
    "primary.polled_cache.by_board_id": lambda: (_with_polled(_primary(live=grid(FLAGSHIP, 3))), "?board_id=b1"),
    "primary.force_live_read_primes_cache": lambda: (
        _with_polled(_primary(live=grid(FLAGSHIP, 3), use_cloud=True)),
        "?force=true",
    ),
    "primary.no_cache_falls_to_live_read": lambda: (_primary(live=grid(FLAGSHIP, 3)), ""),
    "primary.live_read_failure": lambda: (_primary(live=None), ""),
    "primary.force_live_read_failure_despite_cache": lambda: (_with_polled(_primary(live=None)), "?force=true"),
    "primary.virtual_board_live_read": lambda: (
        Service({"b1": Runtime(virtual("flagship", frame=grid(FLAGSHIP, 4), sent_at=SENT_AT))}),
        "",
    ),
    # A virtual primary whose memory refuses (nothing displayed yet) is not a
    # failed network read: it answers empty + geometry, never a 503.
    "primary.virtual_board_nothing_displayed": lambda: (Service({"b1": Runtime(virtual("flagship"))}), ""),
    "primary.virtual_board_nothing_displayed.force": lambda: (
        Service({"b1": Runtime(virtual("flagship"))}),
        "?force=true",
    ),
    "primary.virtual_board_stale_shape_frame.force": lambda: (
        Service({"b1": Runtime(virtual("flagship", frame=grid(FLAGSHIP, 4), displayed=grid(NOTE, 4)))}),
        "?force=true",
    ),
    "primary.sentinel_keyed_runtime.by_board_id": lambda: (
        Service({"__primary__": Runtime(PhysicalClient(live=grid(FLAGSHIP, 3)))}, primary_key="__primary__"),
        "?board_id=b1",
    ),
    "secondary.polled_cache_wins_over_last_sent": lambda: (
        _secondary(
            Runtime(
                PhysicalClient(last_sent=grid(NOTE, 5), live=grid(NOTE, 6)), polled=grid(NOTE, 7), polled_at=POLLED_AT
            )
        ),
        "?board_id=b2",
    ),
    "secondary.last_sent_cache": lambda: (
        _secondary(Runtime(PhysicalClient(last_sent=grid(NOTE, 5), live=grid(NOTE, 6), use_cloud=True))),
        "?board_id=b2",
    ),
    "secondary.force_is_ignored_never_live_reads": lambda: (
        _secondary(Runtime(PhysicalClient(last_sent=grid(NOTE, 5), live=grid(NOTE, 6)))),
        "?board_id=b2&force=true",
    ),
    "secondary.nothing_sent_yet_is_geometry": lambda: (_secondary(Runtime(PhysicalClient())), "?board_id=b2"),
    "secondary.no_runtime_is_geometry": lambda: (
        Service({"b1": Runtime(PhysicalClient(live=grid(FLAGSHIP, 3)))}),
        "?board_id=b2",
    ),
    "secondary.virtual_board_frame": lambda: (
        Service(
            {
                "b1": Runtime(PhysicalClient(live=grid(FLAGSHIP, 3))),
                "vb": Runtime(virtual("note", frame=grid(NOTE, 8), sent_at=SENT_AT)),
            }
        ),
        "?board_id=vb",
    ),
    "secondary.virtual_board_stale_shape_frame": lambda: (
        Service(
            {
                "b1": Runtime(PhysicalClient(live=grid(FLAGSHIP, 3))),
                "vb": Runtime(virtual("note", frame=grid(NOTE, 8), displayed=grid(FLAGSHIP, 8), sent_at=SENT_AT)),
            }
        ),
        "?board_id=vb",
    ),
    "unknown_board": lambda: (_secondary(Runtime(PhysicalClient())), "?board_id=nope"),
    "no_board_client": lambda: (Service({}), ""),
}


@pytest.mark.parametrize("label", sorted(CURRENT_MESSAGE))
def test_current_message(client, label):
    service, query = CURRENT_MESSAGE[label]()
    with patch(DISPLAY_SERVICE, return_value=service):
        response = client.get(f"/board/current-message{query}")
    primary_rt = service.runtimes.get(service._primary_key)
    _check_or_record(
        "GET /board/current-message",
        label,
        _http(
            response,
            live_reads=service.live_reads(),
            cache_after=primary_rt.polled_characters if primary_rt is not None else None,
        ),
    )


# ---------------------------------------------------------------------------
# Surface 2 — GET /panel/{panel_id}/frame
# ---------------------------------------------------------------------------


def _primary_rt() -> Runtime:
    return Runtime(PhysicalClient(last_sent=grid(FLAGSHIP, 1), live=grid(FLAGSHIP, 3)))


PANEL_FRAME: dict[str, Callable[[], tuple[Service | None, str | None]]] = {
    "virtual.frame": lambda: (
        Service({"b1": _primary_rt(), "vb": Runtime(virtual("note", frame=grid(NOTE, 8), sent_at=SENT_AT))}),
        "vb",
    ),
    "virtual.nothing_sent_yet_is_geometry": lambda: (
        Service({"b1": _primary_rt(), "vb": Runtime(virtual("note"))}),
        "vb",
    ),
    "virtual.stale_shape_frame_is_null_not_last_sent": lambda: (
        Service(
            {
                "b1": _primary_rt(),
                "vb": Runtime(virtual("note", frame=grid(NOTE, 8), displayed=grid(FLAGSHIP, 8), sent_at=SENT_AT)),
            }
        ),
        "vb",
    ),
    # The viewer shows what FiestaBoard last displayed, immediately — a panel
    # on the primary board must not lag behind the 30s/180s poll cache.
    "virtual.primary_ignores_a_stale_poll_cache": lambda: (
        Service(
            {
                "b1": Runtime(
                    virtual("flagship", frame=grid(FLAGSHIP, 8), sent_at=SENT_AT),
                    polled=grid(FLAGSHIP, 9),
                    polled_at=POLLED_AT,
                )
            }
        ),
        "b1",
    ),
    "physical.primary_ignores_a_stale_poll_cache": lambda: (
        Service(
            {
                "b1": Runtime(
                    PhysicalClient(last_sent=grid(FLAGSHIP, 1), live=grid(FLAGSHIP, 3)),
                    polled=grid(FLAGSHIP, 9),
                    polled_at=POLLED_AT,
                )
            }
        ),
        "b1",
    ),
    "physical.last_sent_cache_never_live_reads": lambda: (
        Service({"b1": _primary_rt(), "b2": Runtime(PhysicalClient(last_sent=grid(NOTE, 5), live=grid(NOTE, 6)))}),
        "b2",
    ),
    "physical.nothing_sent_yet_is_geometry": lambda: (
        Service({"b1": _primary_rt(), "b2": Runtime(PhysicalClient(live=grid(NOTE, 6)))}),
        "b2",
    ),
    "physical.primary_under_legacy_sentinel_falls_back_to_vb_client": lambda: (
        Service({"__primary__": _primary_rt()}, primary_key="__primary__"),
        "b1",
    ),
    "board_missing_from_settings_is_flagship_geometry": lambda: (Service({"b1": _primary_rt()}), "gone"),
    "no_display_service": lambda: (None, "vb"),
    "unknown_panel": lambda: (Service({"b1": _primary_rt()}), None),
}


@pytest.mark.parametrize("label", sorted(PANEL_FRAME))
def test_panel_frame(client, label):
    service, board_id = PANEL_FRAME[label]()
    panels = Mock()
    panels.get_panel_by_ref.return_value = Panel(name="Hall TV", board_id=board_id) if board_id is not None else None
    with patch(PANEL_SERVICE, return_value=panels), patch(PANELS_SERVICE, return_value=service):
        response = client.get("/panel/abc123def456/frame")
    _check_or_record(
        "GET /panel/{panel_id}/frame",
        label,
        _http(response, physical_live_reads=service.live_reads() if service is not None else 0),
    )


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


def _mcp_primary(**client_kwargs) -> Service:
    return Service({"b1": Runtime(PhysicalClient(**client_kwargs))})


def _mcp_secondary(rt: Runtime) -> Service:
    return Service({"b1": Runtime(PhysicalClient()), "b2": rt})


MCP_CONTENT: dict[str, Callable[[], tuple[Service | None, dict[str, Any]]]] = {
    "primary.polled_cache": lambda: (
        _with_polled(_mcp_primary(last_sent=grid(FLAGSHIP, 1), live=grid(FLAGSHIP, 3))),
        {},
    ),
    "primary.polled_cache.by_board_id": lambda: (
        _with_polled(_mcp_primary(last_sent=grid(FLAGSHIP, 1), live=grid(FLAGSHIP, 3))),
        {"board_id": "b1"},
    ),
    "primary.last_sent_cache": lambda: (_mcp_primary(last_sent=grid(FLAGSHIP, 1), live=grid(FLAGSHIP, 3)), {}),
    "primary.nothing_observed_is_null": lambda: (_mcp_primary(live=grid(FLAGSHIP, 3)), {}),
    "primary.sentinel_keyed_runtime.by_board_id": lambda: (
        Service({"__primary__": Runtime(PhysicalClient(last_sent=grid(FLAGSHIP, 1)))}, primary_key="__primary__"),
        {"board_id": "b1"},
    ),
    "secondary.polled_cache_wins_over_last_sent": lambda: (
        _mcp_secondary(
            Runtime(
                PhysicalClient(last_sent=grid(NOTE, 5), live=grid(NOTE, 6)), polled=grid(NOTE, 7), polled_at=POLLED_AT
            )
        ),
        {"board_id": "b2"},
    ),
    "secondary.last_sent_cache": lambda: (
        _mcp_secondary(Runtime(PhysicalClient(last_sent=grid(NOTE, 5), live=grid(NOTE, 6)))),
        {"board_id": "b2"},
    ),
    "secondary.nothing_sent_yet_is_null": lambda: (_mcp_secondary(Runtime(PhysicalClient())), {"board_id": "b2"}),
    "secondary.no_runtime_is_null": lambda: (Service({"b1": Runtime(PhysicalClient())}), {"board_id": "b2"}),
    "secondary.virtual_board_frame": lambda: (
        Service({"b1": Runtime(PhysicalClient()), "vb": Runtime(virtual("note", frame=grid(NOTE, 8)))}),
        {"board_id": "vb"},
    ),
    "secondary.virtual_board_stale_shape_frame": lambda: (
        Service(
            {
                "b1": Runtime(PhysicalClient()),
                "vb": Runtime(virtual("note", frame=grid(NOTE, 8), displayed=grid(FLAGSHIP, 8))),
            }
        ),
        {"board_id": "vb"},
    ),
    "unknown_board": lambda: (Service({"b1": Runtime(PhysicalClient())}), {"board_id": "nope"}),
    "no_display_service": lambda: (None, {}),
}


@pytest.fixture(scope="module")
def mcp():
    pytest.importorskip("mcp", reason="mcp package not installed")
    from src.mcp_server import _build_mcp_server

    instance = _build_mcp_server()
    assert instance is not None
    return instance


@pytest.mark.parametrize("label", sorted(MCP_CONTENT))
def test_mcp_get_board_content(settings, mcp, label):
    service, kwargs = MCP_CONTENT[label]()
    with patch(MCP_SERVICE, return_value=service):
        outcome = _call_tool(mcp, **kwargs)
    _check_or_record(
        "MCP get_board_content",
        label,
        {**outcome, "live_reads": service.live_reads() if service is not None else 0},
    )


# ---------------------------------------------------------------------------
# Surface 4 — GET /v1/boards/{board} (the board-content half only)
# ---------------------------------------------------------------------------

V1_KEYS = ("characters", "text", "expected_characters", "read_at")

V1_BOARD: dict[str, Callable[[], tuple[Service, str]]] = {
    "primary.polled_cache": lambda: (
        _with_polled(_mcp_primary(last_sent=grid(FLAGSHIP, 1), live=grid(FLAGSHIP, 3))),
        "primary",
    ),
    "primary.last_sent_cache": lambda: (_mcp_primary(last_sent=grid(FLAGSHIP, 1), live=grid(FLAGSHIP, 3)), "b1"),
    "primary.nothing_observed_is_null": lambda: (_mcp_primary(live=grid(FLAGSHIP, 3)), "primary"),
    "primary.sentinel_keyed_runtime.by_board_id": lambda: (
        Service({"__primary__": Runtime(PhysicalClient(last_sent=grid(FLAGSHIP, 1)))}, primary_key="__primary__"),
        "b1",
    ),
    "secondary.polled_cache_wins_over_last_sent": lambda: (
        _mcp_secondary(
            Runtime(
                PhysicalClient(last_sent=grid(NOTE, 5), live=grid(NOTE, 6)), polled=grid(NOTE, 7), polled_at=POLLED_AT
            )
        ),
        "b2",
    ),
    "secondary.last_sent_cache": lambda: (
        _mcp_secondary(Runtime(PhysicalClient(last_sent=grid(NOTE, 5), live=grid(NOTE, 6)))),
        "b2",
    ),
    "secondary.no_runtime_is_null": lambda: (Service({"b1": Runtime(PhysicalClient())}), "b2"),
    "secondary.virtual_board_frame": lambda: (
        Service({"b1": Runtime(PhysicalClient()), "vb": Runtime(virtual("note", frame=grid(NOTE, 8)))}),
        "vb",
    ),
}


@pytest.mark.parametrize("label", sorted(V1_BOARD))
def test_v1_board_content(client, label):
    service, board = V1_BOARD[label]()
    with patch(V1_SERVICE, return_value=service), patch(DISPLAY_SERVICE, return_value=service):
        response = client.get(f"/v1/boards/{board}")
    assert response.status_code == 200, response.text
    body = response.json()
    _check_or_record(
        "GET /v1/boards/{board}",
        label,
        {"status": response.status_code, "body": {k: body[k] for k in V1_KEYS}, "live_reads": service.live_reads()},
    )


def test_every_golden_record_still_has_a_scenario():
    """A scenario that was deleted must take its golden record with it."""
    expected = {
        "GET /board/current-message": set(CURRENT_MESSAGE),
        "GET /panel/{panel_id}/frame": set(PANEL_FRAME),
        "MCP get_board_content": set(MCP_CONTENT),
        "GET /v1/boards/{board}": set(V1_BOARD),
    }
    recorded = {surface: set(records) for surface, records in _load_golden().items()}
    assert recorded == expected, REGENERATE_HINT
