"""Upgrade fixtures: data directories from past releases boot to today's wire.

The output-plugins program will migrate settings to schema v4 and move the
Vestaboard transport into a plugin (Phase 4). "Existing users notice nothing"
is only a claim until real data from the versions people actually run boots
on the new code and puts the same bytes on the wire. This module is that
proof, and the place every later layer re-proves it.

The fixtures
------------
``tests/fixtures/upgrade/<label>/`` is a scrubbed data directory, shaped the
way the release named in its label wrote it (field sets and key order taken
from ``git show <tag>:src/settings/service.py`` and friends). Every value is
fake: RFC 1918 hosts, ``test_``-prefixed keys, public-landmark coordinates.

========================================  ====================================
label                                     what it pins
========================================  ====================================
``v1_27_legacy_local``                    before ``boards[]``: settings has
                                          only ``board_type``; the connection
                                          lives in ``config.json -> board.*``
                                          (the shape #1760 migrated away from)
``v1_27_legacy_cloud``                    the same, over the RW Cloud API
``v2_0_schema0_boards_note``              ``boards[]`` with no schema_version;
                                          the board carries its own key and
                                          config.json a *stale* one that must
                                          never win
``v8_0_schema1_note_array_cloud``         settings v1; cloud note array; an
                                          expired v1 temporary override
``v8_33_schema2_local_tiles``             settings v2; local-tile note array;
                                          an older ``v1_backup`` beside it
``v8_33_schema2_legacy_panel``            a FiestaPanel whose virtual board is
                                          a Note-block ``note_array``
                                          (panels v4), re-fit at boot, next to
                                          a physical Flagship
``v9_10_schema3_multi_board``             settings v3; five boards, one per
                                          transport, plus a current panel
``v9_10_schema3_both_backups``            settings v3 with BOTH
                                          ``settings.json.v2_backup`` and
                                          ``.v3_backup`` on disk (plan D8)
``v10_beta_schema4_https_on``             settings v4 with the retired HTTPS
                                          (Beta) flag on: boots to plain HTTP
                                          with the flag dropped (settings v5)
``v10_beta_schema5_install_transition``   settings v5 with an install-wide
                                          transition (diagonal, 40 ms, step 2)
                                          and the transition plugins beta on:
                                          the board runs the same transition
                                          as its own (settings v6)
``v10_beta_schema5_no_board_section``     the same transition with no
                                          ``board`` section at all: v6 builds
                                          the default board (importing the
                                          legacy config.json connection) so
                                          the transition is not dropped
``v10_beta_schema5_empty_boards``         the same with ``boards: []``
========================================  ====================================

What a test does
----------------
Copy the fixture into the per-test data dir (``FIESTABOARD_DATA_DIR``), boot
the way ``src.api_server.lifespan`` does — ``_run_startup_migrations()``
(config.json silence migrations and the panel re-fit; the first of them to
read settings runs the settings schema migrations), then a real
``DisplayService`` building every board's client from the migrated settings
— and drive one representative send per board. The wire it produces is
compared with the A4 golden for that transport (``tests/golden/wire``): every
request byte-for-byte, and the caller's result except for the board id,
which is the fixture's own. Where a fixture's stored settings yield wire A4
has no scenario for, the golden is this module's own (``UPGRADE_GOLDENS``,
prefixed ``upgrade_``), recorded with A4's ``UPDATE_WIRE_GOLDENS=1`` mode.

``DisplayService.initialize()`` is not called (it starts the board-state
poll thread); ``_build_board_clients`` is the part of it that reads boards.

A failure here means a stored install would behave differently after the
upgrade. Fix the code, not the fixture — a fixture is what a user has on
disk and cannot be edited.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.markup_compat import MarkupFinding, scan_data_dir, scan_document, scan_text
from tests.test_wire_goldens import (
    GOLDEN_DIR,
    FakeMonotonic,
    WireRecorder,
    assert_matches_golden,
    install_floor_clock,
    install_wire_recorder,
    make_response,
    route_result,
)

FIXTURES = Path(__file__).parent / "fixtures" / "upgrade"


# The A4 harness, unchanged: the recorder replaces requests.post/get, the
# floor clock is frozen before any client is built.
@pytest.fixture
def wire(monkeypatch) -> WireRecorder:
    return install_wire_recorder(monkeypatch)


@pytest.fixture
def clock(monkeypatch) -> FakeMonotonic:
    return install_floor_clock(monkeypatch)


@pytest.fixture
def api() -> TestClient:
    from src.api_server import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Booting a fixture
# ---------------------------------------------------------------------------


class Booted:
    """A fixture data dir after a production-shaped boot."""

    def __init__(self, data_dir: Path):
        import src.display_runtime as display_runtime
        from src.api_server import _run_startup_migrations
        from src.main import DisplayService
        from src.settings.service import get_settings_service

        self.data_dir = data_dir
        _run_startup_migrations()
        self.settings = get_settings_service()
        self.service = DisplayService()
        self.service._build_board_clients(sync_cache=False)
        # The adaptive post-send read thread is timer-driven; see the A4 module.
        self.service.request_board_refresh = lambda *a, **k: None
        display_runtime._service = self.service

    @property
    def boards(self) -> list[dict]:
        return self.settings.get_board_settings().boards


def boot(label: str, data_dir: Path, root: Path = FIXTURES) -> Booted:
    from tests.conftest import _drop_all_singletons

    shutil.copytree(root / label, data_dir, dirs_exist_ok=True)
    # Nothing may have opened a store before the fixture's files were there.
    _drop_all_singletons()
    return Booted(data_dir)


# ---------------------------------------------------------------------------
# Comparing against an A4 wire golden
# ---------------------------------------------------------------------------

#: Result fields that name the A4 scenario's own board, or count an A4-only
#: test control, rather than describe the wire.
_SCENARIO_ONLY = {"refresh_requests"}
_SCENARIO_ONLY_BODY = {"board_id"}


def _comparable(result: dict) -> dict:
    out = {k: v for k, v in result.items() if k not in _SCENARIO_ONLY}
    if isinstance(out.get("body"), dict):
        out["body"] = {k: v for k, v in out["body"].items() if k not in _SCENARIO_ONLY_BODY}
    return out


def assert_wire_matches_golden(golden: str, steps: list[tuple[list[dict], dict]]) -> None:
    expected = json.loads((GOLDEN_DIR / f"{golden}.json").read_text())["steps"]
    assert len(steps) == len(expected), f"{golden}: {len(steps)} steps driven, golden has {len(expected)}"
    for i, ((requests, result), want) in enumerate(zip(steps, expected, strict=True)):
        assert requests == want["requests"], (
            f"{golden} step {i} ({want['action']}): wire differs\n"
            f"  golden:   {json.dumps(want['requests'])}\n  observed: {json.dumps(requests)}"
        )
        assert _comparable(result) == _comparable(want["result"]), f"{golden} step {i} ({want['action']}): result"


# ---------------------------------------------------------------------------
# One driver per golden: the same calls the A4 scenario makes
# ---------------------------------------------------------------------------


def _send(api, wire, board_id: str, text: str) -> list[tuple[list[dict], dict]]:
    resp = api.post("/send-message", json={"text": text, "board_id": board_id})
    return [(wire.take(), route_result(resp))]


def _v1_send(api, wire, board_id: str, text: str) -> list[tuple[list[dict], dict]]:
    resp = api.post(f"/v1/boards/{board_id}/message", json={"text": text})
    return [(wire.take(), route_result(resp))]


def drive_local_tiles(api, wire, board_id: str) -> list[tuple[list[dict], dict]]:
    failing = {"192.168.0.21"}

    def respond(method, url, kwargs):
        if method == "POST" and any(f"//{host}:" in url for host in failing):
            return make_response(500, {"error": "tile down"}, url)
        return None

    wire.respond = respond
    steps = _v1_send(api, wire, board_id, "HELLO TILES")
    failing.clear()
    steps += _v1_send(api, wire, board_id, "HELLO TILES")
    wire.respond = None
    return steps


def drive_panel(api, wire, board_id: str, panel_id: str) -> list[tuple[list[dict], dict]]:
    sent = api.post(f"/v1/boards/{board_id}/message", json={"text": "ON THE TV"})
    steps = [(wire.take(), {"status": sent.status_code, "sent": sent.json().get("sent")})]
    frame = api.get(f"/panel/{panel_id}/frame")
    steps.append((wire.take(), route_result(frame, strip=("updated_at",))))
    return steps


DRIVERS = {
    "local_flagship_send": lambda api, wire, bid: _send(api, wire, bid, "HELLO WORLD"),
    "local_note_send": lambda api, wire, bid: _send(api, wire, bid, "HI NOTE"),
    "rw_cloud_send": lambda api, wire, bid: _send(api, wire, bid, "HELLO CLOUD"),
    "note_array_cloud_send": lambda api, wire, bid: _v1_send(api, wire, bid, "HELLO ARRAY"),
    "local_tiles_partial_failure_retry": drive_local_tiles,
}


@dataclass(frozen=True)
class UpgradeGolden:
    """A wire golden owned by this module: a stored setting A4 has no scenario for.

    Recorded and compared with A4's machinery (``UPDATE_WIRE_GOLDENS=1``
    regenerates it; same file format, same directory), driven by one of the
    A4 drivers above.
    """

    driver: str
    description: str
    seam: str
    actions: tuple[str, ...]


UPGRADE_GOLDENS: dict[str, UpgradeGolden] = {
    "upgrade_v2_0_note_stored_column_strategy": UpgradeGolden(
        driver="local_note_send",
        description=(
            "A v2.0 install stored transitions.strategy='column' with no interval or step size; after the "
            "upgrade the Local-API payload carries strategy alone (A4's native_strategy_local sets all three)."
        ),
        seam="POST /send-message with board_id, booted from tests/fixtures/upgrade/v2_0_schema0_boards_note",
        actions=("send text HI NOTE",),
    ),
    "upgrade_v10_beta_schema5_install_transition": UpgradeGolden(
        driver="local_flagship_send",
        description=(
            "A v10 beta install stored an install-wide transition (diagonal, 40 ms, step 2); settings v6 copies "
            "it onto the board, and the Local-API payload carries all three exactly as before the upgrade."
        ),
        seam="POST /send-message with board_id, booted from tests/fixtures/upgrade/v10_beta_schema5_install_transition",
        actions=("send text HELLO WORLD",),
    ),
}


def check_send(golden: str, api, wire, board_id: str) -> None:
    """Drive *golden*'s scenario on *board_id* and compare with the golden."""
    own = UPGRADE_GOLDENS.get(golden)
    steps = DRIVERS[own.driver if own else golden](api, wire, board_id)
    if own is None:
        assert_wire_matches_golden(golden, steps)
        return
    payload = {
        "scenario": golden,
        "description": own.description,
        "seam": own.seam,
        "steps": [
            {"action": action, "requests": requests, "result": result}
            for action, (requests, result) in zip(own.actions, steps, strict=True)
        ],
    }
    assert_matches_golden(golden, payload)


# ---------------------------------------------------------------------------
# What each fixture must do after the upgrade
# ---------------------------------------------------------------------------


def uid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


@dataclass
class Expect:
    #: (board index in boards[], golden) per board that sends over the wire
    sends: list[tuple[int, str]]
    board_count: int
    page_count: int
    #: board index -> panel id, for virtual boards (golden: panel_frame)
    panels: dict[int, str] = field(default_factory=dict)
    #: board index -> (device_type, rows, cols) the board must have after boot
    shapes: dict[int, tuple[str, int | None, int | None]] = field(default_factory=dict)
    #: settings.json schema_version the fixture ships with (a backup of
    #: exactly these bytes must exist after boot when it is behind)
    from_schema: int = 3


EXPECT: dict[str, Expect] = {
    "v1_27_legacy_local": Expect(sends=[(0, "local_flagship_send")], board_count=1, page_count=1, from_schema=0),
    "v1_27_legacy_cloud": Expect(sends=[(0, "rw_cloud_send")], board_count=1, page_count=1, from_schema=0),
    "v2_0_schema0_boards_note": Expect(
        sends=[(0, "upgrade_v2_0_note_stored_column_strategy")], board_count=1, page_count=1, from_schema=0
    ),
    "v8_0_schema1_note_array_cloud": Expect(
        sends=[(0, "note_array_cloud_send")], board_count=1, page_count=1, from_schema=1
    ),
    "v8_33_schema2_local_tiles": Expect(
        sends=[(0, "local_tiles_partial_failure_retry")], board_count=1, page_count=1, from_schema=2
    ),
    "v8_33_schema2_legacy_panel": Expect(
        sends=[(0, "local_flagship_send")],
        board_count=2,
        page_count=2,
        panels={1: "denTVpanel01"},
        # The Note-block panel (note_array 1x4 = 12x15) is re-fit per character.
        shapes={1: ("panel", 12, 29)},
        from_schema=2,
    ),
    "v9_10_schema3_multi_board": Expect(
        sends=[
            (0, "local_flagship_send"),
            (1, "rw_cloud_send"),
            (2, "note_array_cloud_send"),
            (3, "local_note_send"),
        ],
        board_count=5,
        page_count=2,
        panels={4: "denTVpanel02"},
        shapes={4: ("panel", 12, 29)},
    ),
    "v9_10_schema3_both_backups": Expect(sends=[(0, "local_flagship_send")], board_count=1, page_count=1),
    "v10_beta_schema4_https_on": Expect(sends=[(0, "local_flagship_send")], board_count=1, page_count=1, from_schema=4),
    "v10_beta_schema5_install_transition": Expect(
        sends=[(0, "upgrade_v10_beta_schema5_install_transition")], board_count=1, page_count=1, from_schema=5
    ),
    "v10_beta_schema5_no_board_section": Expect(
        sends=[(0, "upgrade_v10_beta_schema5_install_transition")], board_count=1, page_count=1, from_schema=5
    ),
    "v10_beta_schema5_empty_boards": Expect(
        sends=[(0, "upgrade_v10_beta_schema5_install_transition")], board_count=1, page_count=1, from_schema=5
    ),
}


def test_every_fixture_has_an_expectation():
    on_disk = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
    assert on_disk == sorted(EXPECT)


@pytest.fixture
def data_dir(_isolated_data_dir) -> Path:
    return _isolated_data_dir


@pytest.mark.parametrize("label", sorted(EXPECT))
def test_fixture_boots_to_the_same_wire(label, data_dir, api, wire, clock):
    expect = EXPECT[label]
    booted = boot(label, data_dir)

    assert booted.service.board_init_errors == {}, booted.service.board_init_errors
    boards = booted.boards
    assert len(boards) == expect.board_count
    for index, (device_type, rows, cols) in expect.shapes.items():
        board = boards[index]
        assert (board["device_type"], board.get("grid_rows"), board.get("grid_cols")) == (device_type, rows, cols)

    for index, golden in expect.sends:
        check_send(golden, api, wire, boards[index]["id"])

    for index, panel_id in expect.panels.items():
        assert_wire_matches_golden("panel_frame", drive_panel(api, wire, boards[index]["id"], panel_id))

    # Nothing else touched the wire (no stray read, no send to another board).
    assert wire.take() == []


@pytest.mark.parametrize("label", sorted(EXPECT))
def test_fixture_stores_load_and_settle_at_current_schema(label, data_dir):
    from src.pages.service import get_page_service
    from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION

    expect = EXPECT[label]
    original = (FIXTURES / label / "settings.json").read_bytes()
    shipped_backups = {p.name: p.read_bytes() for p in (FIXTURES / label).glob("settings.json.v*_backup")}

    boot(label, data_dir)

    on_disk = json.loads((data_dir / "settings.json").read_text())
    assert on_disk["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION

    # Pre-migration snapshot: written once, holding exactly the shipped bytes.
    if expect.from_schema < CURRENT_SETTINGS_SCHEMA_VERSION:
        backup = data_dir / f"settings.json.v{expect.from_schema}_backup"
        assert backup.read_bytes() == shipped_backups.get(backup.name, original)
    # Backups that were already there are never rewritten or removed.
    for name, content in shipped_backups.items():
        assert (data_dir / name).read_bytes() == content, name

    page_service = get_page_service()
    assert len(page_service.list_pages()) == expect.page_count
    assert page_service.storage._failed_entries == []


@pytest.mark.parametrize("label", sorted(EXPECT))
def test_an_upgraded_install_never_sees_the_setup_wizard(label, data_dir, api, monkeypatch):
    """Plan D13/D18: first run is "no board has a usable output AND the wizard
    was neither completed nor skipped". No release before this one stored a
    wizard state, so every fixture proves its boards alone keep the wizard away.
    The runner's board env vars are cleared so the fixture's files decide."""
    for name in ("BOARD_READ_WRITE_KEY", "FB_READ_WRITE_KEY", "BOARD_LOCAL_API_KEY", "FB_LOCAL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name in ("BOARD_HOST", "FB_HOST"):
        monkeypatch.delenv(name, raising=False)
    boot(label, data_dir)

    assert api.get("/settings/wizard").json() == {"state": None}
    assert api.get("/config/validate").json()["is_first_run"] is False


def test_legacy_config_block_never_overrides_a_board_that_has_credentials(data_dir, api, wire, clock):
    """v2.0's config.json holds a stale key for another host; the board's own wins."""
    booted = boot("v2_0_schema0_boards_note", data_dir)

    # Settings v4 keeps a Vestaboard's connection in its output_config (plan D8).
    config = booted.boards[0]["output_config"]
    assert (config["host"], config["local_api_key"]) == ("192.168.0.11", "test_note_key")


# ---------------------------------------------------------------------------
# Extended-markup scan (plan D15)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", sorted(EXPECT))
def test_fixture_text_keeps_its_meaning_under_extended_markup(label):
    """Report every stored string extended markup would reinterpret.

    None is expected in these fixtures. A finding here is not a bug in the
    fixture: it is the release-notes edge D15 names, and this list is what the
    upgrade that enables the parser must surface.
    """
    findings = scan_data_dir(FIXTURES / label)
    assert findings == [], "\n".join(f"{f.store}:{f.location} {f.kind} {f.marker!r} in {f.text!r}" for f in findings)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{red:HOT}", [("colour_span", "{red:")]),
        ("{RED:hot}", [("colour_span", "{RED:")]),
        ("{63:HOT}", [("colour_span", "{63:")]),
        ("{#ff8800:HOT}", [("colour_span", "{#ff8800:")]),
        ("{black/white:OPEN}", [("block_span", "{black/white:")]),
        ("{icon:sun} 72F", [("icon", "{icon:")]),
        ("{red:HOT {63}} {icon:x}", [("colour_span", "{red:"), ("icon", "{icon:")]),
        ("{red:no closing brace", [("colour_span", "{red:")]),
    ],
)
def test_scan_text_finds_extended_markup_heads(text, expected):
    assert scan_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "{red}{63}{filled}{/red}{/}",  # legacy colour tiles and end tags
        "{center}{{date_time.time}}",  # alignment prefix + template variable
        "{{weather.temperature|pad:3}}",  # filter argument inside a variable
        "{{red}}",  # a template colour tile, not a span (the Task 12 flip made {{red:x}} a span)
        "{filled:X}",  # filled is a tile, not a span colour
        "{fog}",  # the one legacy shortcut a split-flap draws the same after the flip
        "TIME: 10:30",
    ],
)
def test_scan_text_ignores_todays_grammar(text):
    assert scan_text(text) == []


def test_scan_reports_store_and_location():
    pages = {"pages": [{"name": "Ok", "template": ["HI"]}, {"name": "Hot", "template": ["", "{red:HOT}"]}]}
    config = {"features": {"silence_schedule": {"indicator_text": "{icon:moon}"}}, "general": {"name": "{red:x}"}}

    assert scan_document("pages.json", pages) == [
        MarkupFinding("pages.json", "pages[1].template[1]", "colour_span", "{red:", "{red:HOT}")
    ]
    # Only board-text keys are scanned: general.name is not board text.
    assert scan_document("config.json", config) == [
        MarkupFinding("config.json", "features.silence_schedule.indicator_text", "icon", "{icon:", "{icon:moon}")
    ]


def test_scan_data_dir_reads_live_stores_only(tmp_path):
    (tmp_path / "pages.json").write_text(json.dumps({"pages": [{"template": ["{icon:sun}"]}]}))
    (tmp_path / "settings.json.v2_backup").write_text(json.dumps({"temporary_override": {"template": ["{red:X}"]}}))
    (tmp_path / "broken.json").write_text("{not json")

    findings = scan_data_dir(tmp_path)

    assert [(f.store, f.kind) for f in findings] == [("pages.json", "icon")]
