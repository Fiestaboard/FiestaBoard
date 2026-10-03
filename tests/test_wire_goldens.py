"""Wire goldens: exactly what FiestaBoard puts on the network, per scenario.

The output-plugins program (Phase 0, "safety net") is about to move board
transport behind a new seam. Before any of that lands, this module
pins the HTTP boundary as it is TODAY, so every later refactor must keep these
files byte-identical — or change one on purpose and say why in its PR.

What a golden pins
------------------
``tests/golden/wire/<scenario>.json`` holds an ordered list of steps. Each
step records:

* ``requests`` — every call that reached ``requests.post`` / ``requests.get``
  during the step, in call order, with ``method``, ``url`` and every keyword
  the caller passed (``headers``, ``json``, ``timeout``, ...). Nothing is
  sorted or filtered; tuples become lists only because JSON has no tuple.
* ``result`` — what the caller got back: an HTTP route's status code and
  JSON body, or a client's ``(success, was_sent)`` pair / ``SendOutcome``
  fields, plus any runtime flag the scenario is about.

This is the layer BELOW ``tests/golden/engine`` (which pins the engine's
calls INTO the board client with a stub client). Together they pin the whole
path from "the engine decided to send" to "these bytes left the process".

Seams
-----
Scenarios drive the highest public seam that is deterministic: the FastAPI
routes through ``TestClient`` (with a real ``DisplayService`` installed as the
runtime singleton, real settings in the per-test data dir, and real board
clients built from those settings), and the board client directly where no
route exists (plugin transitions, throttle verdicts, client rebuilds,
external-write polling). Only ``requests.post`` / ``requests.get`` are
replaced, by :class:`WireRecorder`; the suite's network fence stays on.

Deliberate test-side controls (each documented where it is applied):

* the RW-Cloud / note-array send floor reads ``src.board_client._time_module``
  ``.monotonic`` at client construction; scenarios that cross a floor swap
  that module for a fake clock (:class:`FakeMonotonic`);
* the module-level note-array floor registry is replaced with an empty dict
  per test so no other test's token leaks into a verdict;
* the local note-array fan-out runs its tiles on a ``ThreadPoolExecutor``.
  Completion order there is a scheduler accident, so these goldens swap in a
  serial executor: tiles are POSTed in the order the code submits them
  (``sorted(tile_clients)``, i.e. row-major) — the only order the code
  itself defines;
* ``DisplayService.request_board_refresh`` (the adaptive post-send read
  thread: timer-driven GETs 0.5–3 s after a send) is replaced with a counter.
  The golden records THAT a refresh was requested, not the timer's reads,
  which depend on wall-clock scheduling;
* ``FIESTABOARD_OUTPUTS_ALLOW_HOSTS`` is unset (production default: allow
  all) so the fence never shapes a golden.

Volatile values stripped from results (nothing is stripped from requests):

* ``updated_at`` in ``GET /panel/{id}/frame`` — wall-clock send time;
* panel and virtual-board ids minted by ``POST /panels`` — random tokens,
  never written into a golden (the request URL carries them, so panel
  scenarios record no URL for the frame read itself).

Regenerating
------------
Off by default. To re-record after an INTENDED wire change::

    UPDATE_WIRE_GOLDENS=1 pytest tests/test_wire_goldens.py

then review ``git diff tests/golden/wire`` line by line and justify every
change in the PR. A golden that changes without a sentence in the PR saying
why is a regression, not a refresh.
"""

from __future__ import annotations

import difflib
import json
import os
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient

GOLDEN_DIR = Path(__file__).parent / "golden" / "wire"
UPDATE = os.environ.get("UPDATE_WIRE_GOLDENS") == "1"

FLAGSHIP_ROWS, FLAGSHIP_COLS = 6, 22


# ---------------------------------------------------------------------------
# Golden file I/O
# ---------------------------------------------------------------------------


def _is_number_row(value: Any) -> bool:
    """A grid row or a ``(connect, read)`` timeout pair: printed on one line."""
    return isinstance(value, list) and all(isinstance(v, int | float) and not isinstance(v, bool) for v in value)


def _dump(value: Any, indent: int = 0) -> str:
    """JSON with one line per grid row, so a golden diff points at the row that moved.

    Plain ``json.dumps(indent=2)`` puts every flap code on its own line — a
    6x22 grid becomes 132 lines and a one-tile change is unreadable.
    """
    pad = "  " * indent
    inner = "  " * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [f"{inner}{json.dumps(k)}: {_dump(v, indent + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        if _is_number_row(value):
            return json.dumps(value)
        items = [f"{inner}{_dump(v, indent + 1)}" for v in value]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    return json.dumps(value)


def assert_matches_golden(name: str, payload: dict) -> None:
    """Compare ``payload`` with ``tests/golden/wire/<name>.json`` (or record it)."""
    path = GOLDEN_DIR / f"{name}.json"
    text = _dump(payload) + "\n"
    if UPDATE:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return
    assert path.exists(), f"Missing wire golden {path}; record it with UPDATE_WIRE_GOLDENS=1"
    expected = path.read_text()
    if text != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=f"golden/wire/{name}.json",
                tofile="observed",
            )
        )
        pytest.fail(f"Wire golden {name!r} changed:\n{diff}", pytrace=False)


def _normalize(value: Any) -> Any:
    """JSON round-trip: tuples -> lists, exactly as a golden stores them."""
    return json.loads(json.dumps(value))


# ---------------------------------------------------------------------------
# The recorder
# ---------------------------------------------------------------------------


def make_response(status: int = 200, body: Any = None, url: str = "") -> requests.Response:
    """A real ``requests.Response`` so ``raise_for_status`` / ``json`` behave natively."""
    resp = requests.models.Response()
    resp.status_code = status
    resp.url = url
    resp.reason = {200: "OK", 429: "Too Many Requests", 500: "Internal Server Error"}.get(status, "")
    resp.encoding = "utf-8"
    resp._content = b"" if body is None else json.dumps(body).encode()
    resp.headers["Content-Type"] = "application/json"
    return resp


Responder = Callable[[str, str, dict], "requests.Response | BaseException | None"]


class WireRecorder:
    """Stands in for ``requests.post`` / ``requests.get`` and records every call.

    ``respond`` may return a Response, raise-able exception, or ``None`` for
    the default (POST -> 200 ``{}``; GET -> 200 ``{"message": <read grid>}``
    when ``read_grids`` has one for the URL, else 200 ``{}``).
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._lock = threading.Lock()
        self.respond: Responder | None = None
        self.read_grids: dict[str, list[list[int]]] = {}

    def _call(self, method: str, url: str, kwargs: dict) -> requests.Response:
        record = {"method": method, "url": url}
        record.update(_normalize(kwargs))
        with self._lock:
            self.calls.append(record)
        outcome = self.respond(method, url, kwargs) if self.respond is not None else None
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is not None:
            return outcome
        if method == "GET" and url in self.read_grids:
            return make_response(200, {"message": self.read_grids[url]}, url)
        return make_response(200, {}, url)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self._call("POST", url, kwargs)

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self._call("GET", url, kwargs)

    def take(self) -> list[dict]:
        """Return and clear the calls recorded since the last take."""
        with self._lock:
            calls, self.calls = self.calls, []
        return calls


class FakeMonotonic:
    """Controllable ``time.monotonic`` for the send-floor clock."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def monotonic(self) -> float:
        return self.t


class _SerialExecutor:
    """Drop-in for ``ThreadPoolExecutor`` that runs ``map`` in submission order."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> _SerialExecutor:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def map(self, fn: Callable, items: Iterable) -> Iterable:
        return [fn(item) for item in items]


@pytest.fixture
def wire(monkeypatch) -> WireRecorder:
    return install_wire_recorder(monkeypatch)


def install_wire_recorder(monkeypatch) -> WireRecorder:
    """The ``wire`` fixture's body, reusable by other modules' fixtures."""
    import src.board_client as board_client
    import src.note_array_local_client as note_array_local_client

    recorder = WireRecorder()
    monkeypatch.setattr(requests, "post", recorder.post)
    monkeypatch.setattr(requests, "get", recorder.get)
    monkeypatch.delenv("FIESTABOARD_OUTPUTS_ALLOW_HOSTS", raising=False)
    # Fresh note-array floor registry: it is module-level by design (it must
    # survive client rebuilds), so without this one test's token would carry
    # its window into another's verdict.
    monkeypatch.setattr(board_client, "_note_array_last_send", {})
    monkeypatch.setattr(note_array_local_client, "ThreadPoolExecutor", _SerialExecutor)
    return recorder


@pytest.fixture
def clock(monkeypatch) -> FakeMonotonic:
    """Freeze the send-floor clock. Must be requested BEFORE clients are built."""
    return install_floor_clock(monkeypatch)


def install_floor_clock(monkeypatch) -> FakeMonotonic:
    """The ``clock`` fixture's body, reusable by other modules' fixtures."""
    import src.board_client as board_client

    fake = FakeMonotonic()
    monkeypatch.setattr(board_client, "_time_module", SimpleNamespace(monotonic=fake.monotonic))
    return fake


# ---------------------------------------------------------------------------
# Boards and the runtime
# ---------------------------------------------------------------------------

LOCAL_HOST = "192.168.0.10"


def local_flagship(board_id: str = "wire-local", **extra: Any) -> dict:
    return {
        "id": board_id,
        "name": "Wire Local",
        "device_type": "flagship",
        "api_mode": "local",
        "host": LOCAL_HOST,
        "port": 7000,
        "local_api_key": "test_local_key",
        **extra,
    }


def local_note(board_id: str = "wire-note") -> dict:
    return {
        "id": board_id,
        "name": "Wire Note",
        "device_type": "note",
        "api_mode": "local",
        "host": "192.168.0.11",
        "port": 7000,
        "local_api_key": "test_note_key",
    }


def rw_cloud(board_id: str = "wire-cloud") -> dict:
    return {
        "id": board_id,
        "name": "Wire Cloud",
        "device_type": "flagship",
        "api_mode": "cloud",
        "cloud_key": "test_rw_key",
    }


def note_array_cloud(board_id: str = "wire-array") -> dict:
    return {
        "id": board_id,
        "name": "Wire Array",
        "device_type": "note_array",
        "api_mode": "cloud",
        "note_array_token": "test_array_token",
        "notes_wide": 2,
        "notes_tall": 1,
    }


def _tile(row: int, col: int, host: str, key: str) -> dict:
    return {"row": row, "col": col, "host": host, "port": 7000, "local_api_key": key, "enabled": True}


def note_array_local(board_id: str = "wire-tiles") -> dict:
    return {
        "id": board_id,
        "name": "Wire Tiles",
        "device_type": "note_array",
        "api_mode": "local",
        "notes_wide": 2,
        "notes_tall": 1,
        "tiles": [
            _tile(0, 0, "192.168.0.20", "test_tile_key_a"),
            _tile(0, 1, "192.168.0.21", "test_tile_key_b"),
        ],
    }


class Runtime:
    """A real ``DisplayService`` (never ``initialize()``d: no poll thread) on real settings."""

    def __init__(self, boards: list[dict]):
        import src.display_runtime as display_runtime
        from src.main import DisplayService
        from src.settings.service import get_settings_service

        self.settings = get_settings_service()
        self.settings.set_boards(boards)
        self.service = DisplayService()
        self.service._build_board_clients(sync_cache=False)
        self.refresh_requests = 0

        def _count_refresh(*_args: Any, **_kwargs: Any) -> None:
            self.refresh_requests += 1

        self.service.request_board_refresh = _count_refresh
        display_runtime._service = self.service

    def client(self, board_id: str) -> Any:
        return self.service.get_board_client(board_id)


@pytest.fixture
def api() -> TestClient:
    from src.api_server import app

    return TestClient(app)


def route_result(resp, *, strip: tuple[str, ...] = ()) -> dict:
    """Status + JSON body (+ Retry-After when present) of a route response."""
    body = resp.json()
    if isinstance(body, dict):
        for key in strip:
            body.pop(key, None)
    out: dict[str, Any] = {"status": resp.status_code, "body": body}
    if "Retry-After" in resp.headers:
        out["retry_after_header"] = resp.headers["Retry-After"]
    return out


def outcome_result(outcome: Any) -> dict:
    """A client send's return value, field by field."""
    if hasattr(outcome, "_asdict"):
        return {"type": "SendOutcome", **outcome._asdict()}
    return {"type": "tuple", "value": list(outcome)}


def grid_of(text: str, rows: int = FLAGSHIP_ROWS, cols: int = FLAGSHIP_COLS) -> list[list[int]]:
    from src.text_to_board import text_to_board_array

    return text_to_board_array(text, rows=rows, cols=cols)


class Scenario:
    """Collects steps for one golden."""

    def __init__(self, name: str, description: str, seam: str, wire: WireRecorder):
        self.payload: dict[str, Any] = {"scenario": name, "description": description, "seam": seam, "steps": []}
        self.name = name
        self.wire = wire

    def step(self, action: str, result: dict) -> None:
        self.payload["steps"].append({"action": action, "requests": self.wire.take(), "result": result})

    def check(self) -> None:
        assert_matches_golden(self.name, self.payload)


# ---------------------------------------------------------------------------
# Sends through POST /send-message, /v1/boards/{board}/message
# ---------------------------------------------------------------------------


def test_local_flagship_send(api, wire):
    rt = Runtime([local_flagship()])
    s = Scenario(
        "local_flagship_send",
        "Local-API Flagship: one POST of {characters} to :7000/local-api/message.",
        "POST /send-message",
        wire,
    )
    s.step(
        "send text HELLO WORLD",
        {
            **route_result(api.post("/send-message", json={"text": "HELLO WORLD"})),
            "refresh_requests": rt.refresh_requests,
        },
    )
    s.check()


def test_local_note_send(api, wire):
    rt = Runtime([local_note()])
    s = Scenario(
        "local_note_send",
        "Local-API Note: a 3x15 grid, same endpoint shape as a Flagship.",
        "POST /send-message",
        wire,
    )
    s.step(
        "send text HI NOTE",
        {**route_result(api.post("/send-message", json={"text": "HI NOTE"})), "refresh_requests": rt.refresh_requests},
    )
    s.check()


def test_rw_cloud_send(api, wire, clock):
    rt = Runtime([rw_cloud()])
    s = Scenario(
        "rw_cloud_send",
        "Read/Write Cloud API: the bare grid (no wrapper) to rw.vestaboard.com with the RW key header.",
        "POST /send-message",
        wire,
    )
    s.step(
        "send text HELLO CLOUD",
        {
            **route_result(api.post("/send-message", json={"text": "HELLO CLOUD"})),
            "refresh_requests": rt.refresh_requests,
        },
    )
    s.check()


def test_note_array_cloud_send(api, wire, clock):
    Runtime([note_array_cloud()])
    s = Scenario(
        "note_array_cloud_send",
        "Note-array Cloud API: {characters: grid} with X-Vestaboard-Token, 3x30 for a 2x1 array.",
        "POST /v1/boards/{board}/message",
        wire,
    )
    s.step(
        "send text HELLO ARRAY", route_result(api.post("/v1/boards/wire-array/message", json={"text": "HELLO ARRAY"}))
    )
    s.check()


def test_local_tiles_partial_failure_then_retry(api, wire):
    Runtime([note_array_local()])
    failing = {"192.168.0.21"}

    def respond(method, url, kwargs):
        if method == "POST" and any(f"//{host}:" in url for host in failing):
            return make_response(500, {"error": "tile down"}, url)
        return None

    wire.respond = respond
    s = Scenario(
        "local_tiles_partial_failure_retry",
        "Local note array (2 tiles): tile (0,1) fails; the identical retry re-POSTs ONLY that tile.",
        "POST /v1/boards/{board}/message",
        wire,
    )
    s.step(
        "send HELLO TILES while tile (0,1) answers 500",
        route_result(api.post("/v1/boards/wire-tiles/message", json={"text": "HELLO TILES"})),
    )
    failing.clear()
    s.step(
        "send the same text again with every tile healthy",
        route_result(api.post("/v1/boards/wire-tiles/message", json={"text": "HELLO TILES"})),
    )
    s.check()


def test_native_strategy_local(api, wire):
    rt = Runtime([local_flagship()])
    rt.settings.update_transition_settings(strategy="column", step_interval_ms=250, step_size=2)
    s = Scenario(
        "native_strategy_local",
        "Built-in transition: strategy/step_interval_ms/step_size ride in the Local-API payload.",
        "POST /send-message (transition settings: column, 250ms, step 2)",
        wire,
    )
    s.step("send text WAVE", route_result(api.post("/send-message", json={"text": "WAVE"})))
    s.check()


def test_native_strategy_dropped_on_cloud(api, wire, clock):
    rt = Runtime([rw_cloud(), note_array_cloud()])
    rt.settings.update_transition_settings(strategy="column", step_interval_ms=250, step_size=2)
    s = Scenario(
        "native_strategy_dropped_on_cloud",
        "Built-in transition settings never reach a cloud payload (RW: bare grid; note array: stripped).",
        "POST /send-message with board_id (transition settings: column, 250ms, step 2)",
        wire,
    )
    s.step(
        "send WAVE to the RW cloud board",
        route_result(api.post("/send-message", json={"text": "WAVE", "board_id": "wire-cloud"})),
    )
    s.step(
        "send WAVE to the cloud note array",
        route_result(api.post("/send-message", json={"text": "WAVE", "board_id": "wire-array"})),
    )
    s.check()


def test_unchanged_content_skip(api, wire):
    Runtime([local_flagship()])
    s = Scenario(
        "unchanged_skip",
        "Same text twice: the second send is skipped client-side (no request) and answers sent=false.",
        "POST /send-message",
        wire,
    )
    s.step("send SAME", route_result(api.post("/send-message", json={"text": "SAME"})))
    s.step("send SAME again", route_result(api.post("/send-message", json={"text": "SAME"})))
    s.check()


def test_force_resend(api, wire):
    Runtime([local_flagship()])
    s = Scenario(
        "force_resend",
        "force=true bypasses the unchanged cache: the identical grid is POSTed twice.",
        "POST /v1/boards/{board}/message",
        wire,
    )
    s.step(
        "send AGAIN force",
        route_result(api.post("/v1/boards/wire-local/message", json={"text": "AGAIN", "force": True})),
    )
    s.step(
        "send AGAIN force again",
        route_result(api.post("/v1/boards/wire-local/message", json={"text": "AGAIN", "force": True})),
    )
    s.check()


def test_paused_board_sends_nothing(api, wire):
    rt = Runtime([local_flagship()])
    rt.settings.set_paused(True, "wire-local")
    s = Scenario(
        "paused_no_request",
        "A paused board refuses the write with 409 and nothing goes on the wire.",
        "POST /send-message and POST /v1/boards/{board}/message",
        wire,
    )
    s.step("send PAUSED via /send-message", route_result(api.post("/send-message", json={"text": "PAUSED"})))
    s.step("send PAUSED via v1", route_result(api.post("/v1/boards/wire-local/message", json={"text": "PAUSED"})))
    s.check()


def test_silenced_board_sends_nothing(api, wire):
    Runtime([local_flagship()])
    s = Scenario(
        "silence_no_request",
        "Inside the silence window a manual send is refused with 409 and nothing goes on the wire. "
        "(The window itself is forced on via Config.is_silence_mode_active; its schedule math is not under test.)",
        "POST /send-message",
        wire,
    )
    with patch("src.board_guards.Config.is_silence_mode_active", return_value=True):
        s.step("send SHH", route_result(api.post("/send-message", json={"text": "SHH"})))
    s.check()


# ---------------------------------------------------------------------------
# Send floor (RW Cloud and note-array cloud: 15 s)
# ---------------------------------------------------------------------------


def test_throttle_route_429(api, wire, clock):
    Runtime([rw_cloud()])
    s = Scenario(
        "throttle_rw_cloud_route",
        "RW Cloud 15 s floor at the route: a second send 5 s later is dropped (no request) -> 429 + Retry-After.",
        "POST /send-message (frozen floor clock)",
        wire,
    )
    s.step("t=1000 send FIRST", route_result(api.post("/send-message", json={"text": "FIRST"})))
    clock.t += 5.0
    s.step("t=1005 send SECOND", route_result(api.post("/send-message", json={"text": "SECOND"})))
    clock.t += 10.0
    s.step("t=1015 send SECOND", route_result(api.post("/send-message", json={"text": "SECOND"})))
    s.check()


@pytest.mark.parametrize("board", [rw_cloud, note_array_cloud], ids=["rw_cloud", "note_array_cloud"])
def test_throttle_send_outcome(wire, clock, board):
    from src.board_client import board_client_from_board_dict

    cfg = board()
    client = board_client_from_board_dict(cfg)
    rows, cols = (3, 30) if cfg["device_type"] == "note_array" else (FLAGSHIP_ROWS, FLAGSHIP_COLS)
    s = Scenario(
        f"throttle_outcome_{board.__name__}",
        "Client render(with_outcome=True) across the 15 s floor: sent / throttled+retry_after / sent.",
        "board_client_from_board_dict(...).render(..., with_outcome=True)",
        wire,
    )
    s.step("t=1000 render ONE", outcome_result(client.render(grid_of("ONE", rows, cols), with_outcome=True)))
    clock.t += 4.5
    s.step("t=1004.5 render TWO", outcome_result(client.render(grid_of("TWO", rows, cols), with_outcome=True)))
    clock.t += 10.5
    s.step("t=1015 render TWO", outcome_result(client.render(grid_of("TWO", rows, cols), with_outcome=True)))
    s.check()


def test_upstream_429_releases_floor_slot(wire, clock):
    from src.board_client import board_client_from_board_dict

    client = board_client_from_board_dict(rw_cloud())
    answers = [make_response(429, {"error": "rate limited"})]
    wire.respond = lambda method, url, kwargs: answers.pop(0) if answers else None
    s = Scenario(
        "upstream_429_rw_cloud",
        "The cloud answering HTTP 429: no retry, (False, False), and the floor slot is released so an "
        "immediate resend goes out.",
        "board_client_from_board_dict(rw_cloud).render(..., with_outcome=True)",
        wire,
    )
    s.step(
        "t=1000 render HELLO (cloud answers 429)", outcome_result(client.render(grid_of("HELLO"), with_outcome=True))
    )
    clock.t += 1.0
    s.step(
        "t=1001 render HELLO (cloud answers 200)", outcome_result(client.render(grid_of("HELLO"), with_outcome=True))
    )
    s.check()


def test_floor_survives_client_rebuild_note_array(wire, clock):
    from src.board_client import board_client_from_board_dict

    cfg = note_array_cloud()
    s = Scenario(
        "floor_rebuild_note_array_cloud",
        "Note-array cloud floor is module-level keyed by token: a client rebuilt from the same saved board "
        "5 s later is still throttled.",
        "two board_client_from_board_dict(...) clients for one board",
        wire,
    )
    first = board_client_from_board_dict(cfg)
    s.step("t=1000 first client renders ONE", outcome_result(first.render(grid_of("ONE", 3, 30), with_outcome=True)))
    clock.t += 5.0
    rebuilt = board_client_from_board_dict(cfg)
    s.step(
        "t=1005 rebuilt client renders TWO", outcome_result(rebuilt.render(grid_of("TWO", 3, 30), with_outcome=True))
    )
    s.check()


def test_floor_rw_cloud_client_rebuild_current_behavior(wire, clock):
    from src.board_client import board_client_from_board_dict

    cfg = rw_cloud()
    s = Scenario(
        "floor_rebuild_rw_cloud_CURRENT",
        "CURRENT BEHAVIOR, to change deliberately in layer A10: the RW Cloud floor is per client instance, "
        "so a client rebuilt from the same saved board 5 s later is NOT throttled and POSTs inside the window.",
        "two board_client_from_board_dict(...) clients for one board",
        wire,
    )
    first = board_client_from_board_dict(cfg)
    s.step("t=1000 first client renders ONE", outcome_result(first.render(grid_of("ONE"), with_outcome=True)))
    clock.t += 5.0
    rebuilt = board_client_from_board_dict(cfg)
    s.step("t=1005 rebuilt client renders TWO", outcome_result(rebuilt.render(grid_of("TWO"), with_outcome=True)))
    s.check()


# ---------------------------------------------------------------------------
# Plugin transition
# ---------------------------------------------------------------------------


def test_plugin_transition_frames(wire):
    from src.board_client import board_client_from_board_dict
    from src.plugins.base import TransitionPluginBase
    from src.settings.service import get_settings_service
    from src.transitions import TransitionRunner

    class WireFakeTransition(TransitionPluginBase):
        """Two fixed intermediate frames, no delay: deterministic and instant."""

        @property
        def plugin_id(self) -> str:
            return "wire_fake"

        def generate_frames(self, from_grid, to_grid, device, config):
            yield grid_of("FRAME ONE"), 0
            yield grid_of("FRAME TWO"), 0

    plugin = WireFakeTransition(
        {
            "id": "wire_fake",
            "name": "Wire Fake",
            "version": "1.0.0",
            "plugin_type": "transition",
            "transition_settings": {"min_interval_ms": 0},
        }
    )
    get_settings_service().update_beta_settings({"transition_plugins_enabled": True})
    client = board_client_from_board_dict(local_flagship())
    client.set_transition_runner(TransitionRunner(lambda pid: plugin if pid == "wire_fake" else None))
    s = Scenario(
        "plugin_transition_local",
        "render(strategy='plugin:wire_fake') with the beta on: each plugin frame, then the snap to target, "
        "each a forced Local-API POST with no native strategy.",
        "BoardClient.render(..., strategy='plugin:<id>', with_outcome=True)",
        wire,
    )
    s.step(
        "render TARGET via plugin:wire_fake",
        outcome_result(
            client.render(grid_of("TARGET"), strategy="plugin:wire_fake", device_type="flagship", with_outcome=True)
        ),
    )
    s.check()


# ---------------------------------------------------------------------------
# Panels (virtual boards): no wire at all; the frame is the contract
# ---------------------------------------------------------------------------


def test_panel_frame(api, wire):
    Runtime([local_flagship()])
    created = api.post("/panels", json={"name": "Wire TV", "screen_diagonal_inches": 55})
    assert created.status_code == 201, created.text
    panel = created.json()
    s = Scenario(
        "panel_frame",
        "A FiestaPanel's virtual board: a write makes no request; GET /panel/{id}/frame serves the grid "
        "(updated_at stripped: wall-clock).",
        "POST /v1/boards/{board}/message then GET /panel/{id}/frame",
        wire,
    )
    wire.take()  # creating the panel is not part of the contract under test
    sent = api.post(f"/v1/boards/{panel['board_id']}/message", json={"text": "ON THE TV"})
    s.step("send ON THE TV to the panel's board", {"status": sent.status_code, "sent": sent.json().get("sent")})
    frame = api.get(f"/panel/{panel['id']}/frame")
    s.step("read the panel frame", route_result(frame, strip=("updated_at",)))
    s.check()


# ---------------------------------------------------------------------------
# Other board writers: welcome, live render, identify
# ---------------------------------------------------------------------------


def test_welcome_message(api, wire):
    rt = Runtime([local_flagship()])
    rt.settings.update_transition_settings(strategy="edges-to-center", step_interval_ms=100, step_size=1)
    s = Scenario(
        "welcome_local",
        "Setup-wizard welcome: a fresh client from the primary board, forced, with the transition settings.",
        "POST /send-welcome-message",
        wire,
    )
    s.step("send the welcome message", route_result(api.post("/send-welcome-message")))
    s.check()


def test_live_template_render(api, wire):
    Runtime([local_flagship()])
    s = Scenario(
        "live_render_local",
        "Live editor: a fresh client per request, forced, plain grid POST.",
        "POST /templates/render/live",
        wire,
    )
    s.step(
        "live-render ['LIVE EDIT']", route_result(api.post("/templates/render/live", json={"template": ["LIVE EDIT"]}))
    )
    s.check()


def test_identify_tile(api, wire):
    Runtime([note_array_local()])
    s = Scenario(
        "identify_tile",
        "Identify flash on local note-array tile (0,1): one forced POST of its slot pattern to that tile only.",
        "POST /settings/board/{board_id}/identify",
        wire,
    )
    s.step(
        "identify tile row 0 col 1",
        route_result(api.post("/settings/board/wire-tiles/identify", json={"target": "tile", "row": 0, "col": 1})),
    )
    s.check()


# ---------------------------------------------------------------------------
# Reads: detect-size, connection test, external-write detection
# ---------------------------------------------------------------------------


def test_detect_size(api, wire):
    Runtime([local_flagship(), note_array_cloud()])
    wire.read_grids["http://192.168.0.10:7000/local-api/message"] = [[0] * 22 for _ in range(6)]

    def respond(method, url, kwargs):
        if method == "GET" and url.startswith("https://cloud.vestaboard.com"):
            return make_response(200, {"currentMessage": {"layout": json.dumps([[0] * 30 for _ in range(3)])}}, url)
        return None

    wire.respond = respond
    s = Scenario(
        "detect_size",
        "Detect-size is one GET over the board's own transport (local flagship; cloud note array).",
        "POST /settings/board/{board_id}/detect-size",
        wire,
    )
    s.step("detect the local flagship", route_result(api.post("/settings/board/wire-local/detect-size")))
    s.step("detect the cloud note array", route_result(api.post("/settings/board/wire-array/detect-size")))
    s.check()


def test_config_board_test(api, wire):
    def respond(method, url, kwargs):
        if url.startswith("https://rw.vestaboard.com"):
            return make_response(200, {"currentMessage": {"layout": json.dumps([[0] * 22 for _ in range(6)])}}, url)
        return make_response(200, {"message": [[0] * 22 for _ in range(6)]}, url)

    wire.respond = respond
    s = Scenario(
        "config_board_test",
        "Connection probe: one unsaved GET with timeout=10 (not the client's split timeout), local then cloud.",
        "POST /config/board/test",
        wire,
    )
    s.step(
        "probe local",
        route_result(
            api.post(
                "/config/board/test", json={"api_mode": "local", "local_api_key": "test_probe_key", "host": LOCAL_HOST}
            )
        ),
    )
    s.step(
        "probe cloud",
        route_result(api.post("/config/board/test", json={"api_mode": "cloud", "cloud_key": "test_probe_rw"})),
    )
    s.check()


def test_external_write_detection(wire):
    rt = Runtime([local_flagship()])
    client = rt.client("wire-local")
    read_url = "http://192.168.0.10:7000/local-api/message"
    runtime = rt.service.get_runtime("wire-local")
    s = Scenario(
        "external_write_detection",
        "Poll reads are GETs of the send URL; two consecutive mismatching reads against the same last-sent "
        "grid mark the board out-of-band.",
        "DisplayService._poll_board_state_once (the board-state poll thread's body)",
        wire,
    )

    def flags() -> dict:
        return {
            "showing_out_of_band": runtime.showing_out_of_band,
            "suspect_baseline_set": runtime.external_change_suspect_baseline is not None,
        }

    s.step("send OURS", {"send": outcome_result(client.render(grid_of("OURS"))), **flags()})
    wire.read_grids[read_url] = grid_of("OURS")
    rt.service._poll_board_state_once()
    s.step("poll: board shows OURS", flags())
    wire.read_grids[read_url] = grid_of("THEIRS")
    rt.service._poll_board_state_once()
    s.step("poll: board shows THEIRS (first mismatch)", flags())
    rt.service._poll_board_state_once()
    s.step("poll: board still shows THEIRS (confirmed)", flags())
    s.check()
