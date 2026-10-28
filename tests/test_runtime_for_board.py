"""Every board write and read goes through the board's live runtime.

``DisplayService.runtime_for(board_id)`` answers a board's **live**
runtime: the one the engine sends through, holding the board's send lock,
cancel token, frame cache and send floor. Before this layer, the welcome
message, the live editor, detect-size, identify and the debug system-info
probe each built a throwaway client of their own — which only worked because
a virtual board's frames sat in a module-level registry, and which meant
those writes never preempted a running transition and never told the board's
dedupe cache what the board now shows.

Pinned here:

- a direct ``send_characters`` on a bound driver is a runtime write: from
  outside a run it preempts the in-flight transition and takes the lock; a
  frame sent from inside the run (the transition's own) does not preempt it;
- nothing in ``src/`` constructs a driver except the runtime factory
  (``src/outputs/factory.py``) and the client modules themselves;
- the routes that used to build throwaway clients use the live runtime (or,
  for unsaved credentials, a draft driver from the same factory).
"""

from __future__ import annotations

import ast
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.outputs import OutputRuntime
from tests.first_party_drivers import panel_driver
from tests.live_boards import install_live_boards
from tests.test_wire_goldens import grid_of, install_wire_recorder, local_flagship, note_array_local

REPO = Path(__file__).resolve().parents[1]
TIMEOUT = 3.0


def _grid(fill: int = 0) -> list[list[int]]:
    return [[fill] * 22 for _ in range(6)]


class _BlockingRunner:
    """A transition that runs until its run is cancelled (or TIMEOUT passes)."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.cancelled: list[bool] = []

    def run(self, *, cancel_event, **_kwargs):
        self.started.set()
        self.cancelled.append(cancel_event.wait(TIMEOUT))
        return True, True


@pytest.fixture
def plugins_on(monkeypatch):
    monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)


@pytest.fixture
def api() -> TestClient:
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def wire(monkeypatch):
    return install_wire_recorder(monkeypatch)


# --- a plain write is a runtime write ------------------------------------------------


class TestDirectWritesAreRuntimeWrites:
    def test_a_direct_write_preempts_the_in_flight_transition(self, plugins_on):
        client = panel_driver("flagship")
        client.set_output_runtime(OutputRuntime("panel"))
        runner = _BlockingRunner()
        client.set_transition_runner(runner)
        t = threading.Thread(target=client.render, args=(_grid(1),), kwargs={"strategy": "plugin:wipe"})
        t.start()
        assert runner.started.wait(TIMEOUT)

        client.send_characters(_grid(2), force=True)  # e.g. /debug/blank, MQTT blank_board
        t.join(TIMEOUT)

        assert runner.cancelled == [True], "the direct write did not preempt the running transition"

    def test_a_frame_sent_inside_a_run_does_not_preempt_that_run(self, plugins_on):
        client = panel_driver("flagship")
        runtime = OutputRuntime("panel")
        client.set_output_runtime(runtime)
        seen: list[bool] = []

        class _TwoFrames:
            def run(self, *, board_client, cancel_event, to_grid, **_kwargs):
                board_client.send_characters(_grid(5), strategy=None, force=True)
                seen.append(cancel_event.is_set())
                return board_client.send_characters(to_grid, strategy=None, force=True)

        client.set_transition_runner(_TwoFrames())
        assert client.render(_grid(6), strategy="plugin:wipe") == (True, True)
        assert seen == [False]
        assert runtime.last_frame == _grid(6)


# --- one factory --------------------------------------------------------------------

# Every board's driver is an output plugin instance in the plugin adapter.
CLIENT_MODULES = {REPO / "src" / "outputs" / "plugin_driver.py"}
# The runtime factory, the output registry it resolves through, and the two
# places that hold an output's builder: plugin registration (third-party) and
# the first-party loader. (The conformance suite drives a private instance of
# the plugin under test for its floor rule — never a board.)
FACTORY = {
    REPO / "src" / "outputs" / "factory.py",
    REPO / "src" / "outputs" / "registry.py",
    REPO / "src" / "outputs" / "plugin_registration.py",
    REPO / "src" / "outputs" / "first_party.py",
    REPO / "src" / "outputs" / "conformance.py",
}
CONSTRUCTORS = {
    "OutputPluginDriver",
    "VestaboardOutput",
    "FiestaPanelOutput",
    "board_client_from_board_dict",
}


def _driver_constructions(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path in CLIENT_MODULES or path in FACTORY:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in CONSTRUCTORS:
                found.append(f"{path.relative_to(root.parent)}:{node.lineno} {name}(...)")
    return found


class TestOneFactory:
    def test_nothing_outside_the_factory_builds_a_driver(self):
        sites = _driver_constructions(REPO / "src")
        assert sites == [], "drivers built outside src/outputs/factory.py:\n  " + "\n  ".join(sites)

    def test_the_scan_sees_a_planted_construction(self, tmp_path):
        planted = tmp_path / "src" / "planted.py"
        planted.parent.mkdir()
        planted.write_text("def f(b):\n    return OutputPluginDriver(VestaboardOutput(b, {}))\n")
        assert len(_driver_constructions(planted.parent)) == 2


# --- the routes use the live runtime ------------------------------------------------------


class TestRoutesUseTheLiveRuntime:
    def test_the_welcome_message_lands_in_the_live_runtimes_frame_store(self, api, wire):
        service = install_live_boards([local_flagship()])
        resp = api.post("/send-welcome-message")
        assert resp.status_code == 200, resp.text
        assert service.get_runtime("wire-local").output.last_frame is not None

    def test_the_welcome_message_goes_to_the_board_named(self, api, wire):
        """The wizard names the board it just created; the primary (a seeded
        placeholder, or any other board) is not written."""
        service = install_live_boards([local_flagship(), local_flagship("wire-second", host="192.168.0.11")])
        resp = api.post("/send-welcome-message", json={"board_id": "wire-second"})
        assert resp.status_code == 200, resp.text
        assert service.get_runtime("wire-second").output.last_frame is not None
        assert service.get_runtime("wire-local").output.last_frame is None

    def test_the_welcome_message_to_an_unknown_board_is_404(self, api, wire):
        service = install_live_boards([local_flagship()])
        resp = api.post("/send-welcome-message", json={"board_id": "nope"})
        assert resp.status_code == 404, resp.text
        assert service.get_runtime("wire-local").output.last_frame is None

    def test_a_live_edit_lands_in_the_live_runtimes_frame_store(self, api, wire):
        service = install_live_boards([local_flagship()])
        resp = api.post("/templates/render/live", json={"template": ["LIVE EDIT"]})
        assert resp.json()["sent_to_board"] is True, resp.text
        assert service.get_runtime("wire-local").output.last_frame == grid_of("LIVE EDIT")

    def test_detect_size_reads_through_the_live_driver(self, api, wire, monkeypatch):
        service = install_live_boards([local_flagship()])
        reads: list[bool] = []

        def read(sync_cache: bool = False):
            reads.append(sync_cache)
            return _grid(0)

        monkeypatch.setattr(service.get_runtime("wire-local").client, "read_current_message", read)
        resp = api.post("/settings/board/wire-local/detect-size")
        assert resp.status_code == 200, resp.text
        assert reads == [False]

    def test_identify_of_a_saved_tile_preempts_the_boards_running_transition(self, api, wire, plugins_on):
        service = install_live_boards([note_array_local()])
        client = service.get_runtime("wire-tiles").client
        runner = _BlockingRunner()
        client.set_transition_runner(runner)
        grid = [[0] * 30 for _ in range(3)]
        t = threading.Thread(target=client.render, args=(grid,), kwargs={"strategy": "plugin:wipe"}, daemon=True)
        t.start()
        assert runner.started.wait(TIMEOUT)

        resp = api.post("/settings/board/wire-tiles/identify", json={"target": "tile", "row": 0, "col": 1})
        t.join(TIMEOUT)

        assert resp.status_code == 200, resp.text
        assert runner.cancelled == [True], "identify wrote past the board's runtime"

    def test_system_info_reports_configured_only_with_a_live_connection(self, api, wire):
        service = install_live_boards([local_flagship()])
        assert api.get("/debug/system-info").json()["board_configured"] is True
        service.runtimes = {}
        assert api.get("/debug/system-info").json()["board_configured"] is False
