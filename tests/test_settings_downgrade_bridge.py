"""The downgrade bridge: a rolled-back build boots from its own pre-upgrade backup.

Output-plugins plan D8 ("Rollback"). Phase 4 will move settings.json to schema
v4; an older build reading a v4 file refuses to start (``SchemaTooNewError``),
so "roll back one release" would mean "lose the board". The newer build's
migration always leaves ``settings.json.v{N}_backup`` — the file exactly as
this build last wrote it — so this build can step back onto it:

* too new + ``settings.json.v{CURRENT}_backup`` present: the too-new file is
  set aside as ``settings.json.v{found}_aside-<UTC timestamp>``, the backup is
  copied into place and then **deleted**, a notice naming the aside file is
  recorded for the web UI, and the normal load continues;
* too new + no backup: today's refusal, with a message that says what to do.

Why the backup is deleted: the newer build writes its pre-migration backup
only when none exists (``service.py`` "if not backup_path.exists()"). A backup
left behind after a rollback would be the *first* upgrade's snapshot, so the
next upgrade-then-rollback would silently restore it and lose everything
changed in between. ``test_a_second_rollback_restores_the_second_snapshot``
pins that.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.settings.board_shape import board_view
from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION as CURRENT

FUTURE = CURRENT + 1
ROLLBACK_FIXTURES = Path(__file__).parent / "fixtures" / "rollback"
ASIDE = re.compile(rf"^settings\.json\.v{FUTURE}_aside-\d{{8}}T\d{{6}}Z$")


def _board(key: str) -> dict:
    return {
        "id": "00000000-0000-4000-8000-000000000001",
        "name": "Living Room",
        "device_type": "flagship",
        "api_mode": "local",
        "host": "192.168.0.10",
        "port": 7000,
        "local_api_key": key,
    }


def _current_file(key: str = "test_local_key", **extra) -> dict:
    """A settings.json this build wrote (schema CURRENT)."""
    return {"schema_version": CURRENT, "board": {"board_type": "black", "boards": [_board(key)]}, **extra}


def _future_file(key: str = "test_local_key") -> dict:
    """A settings.json a newer build wrote: connection moved under output_config (D8's v4 shape)."""
    board = _board(key)
    connection = {k: board.pop(k) for k in ("api_mode", "host", "port", "local_api_key")}
    board.update({"output": "vestaboard", "output_config": connection})
    return {"schema_version": FUTURE, "board": {"board_type": "black", "boards": [board]}}


def _write(path: Path, data: dict) -> bytes:
    raw = (json.dumps(data, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return raw


def _newer_build_upgrades(data_dir: Path) -> None:
    """What the newer build's migration does to this build's file: back it up
    *only if no backup exists*, then stamp the file with the newer schema."""
    settings = data_dir / "settings.json"
    backup = data_dir / f"settings.json.v{CURRENT}_backup"
    if not backup.exists():
        shutil.copy2(settings, backup)
    current = json.loads(settings.read_text())
    _write(settings, {**_future_file(current["board"]["boards"][0]["local_api_key"])})


def _asides(data_dir: Path) -> list[Path]:
    return sorted(p for p in data_dir.iterdir() if p.name.startswith(f"settings.json.v{FUTURE}_aside-"))


def _service(data_dir: Path):
    from src.settings.service import SettingsService

    return SettingsService(settings_file=str(data_dir / "settings.json"))


@pytest.fixture
def data_dir(_isolated_data_dir) -> Path:
    _isolated_data_dir.mkdir(parents=True, exist_ok=True)
    return _isolated_data_dir


# ---------------------------------------------------------------------------
# Too new, backup present: swap, delete the backup, keep the aside, notice
# ---------------------------------------------------------------------------


def test_a_too_new_file_with_a_backup_boots_from_the_backup(data_dir):
    backup_bytes = _write(data_dir / f"settings.json.v{CURRENT}_backup", _current_file())
    future_bytes = _write(data_dir / "settings.json", _future_file())

    service = _service(data_dir)

    assert (data_dir / "settings.json").read_bytes() == backup_bytes
    assert board_view(service.get_board_settings().boards[0])["local_api_key"] == "test_local_key"
    asides = _asides(data_dir)
    assert [ASIDE.match(p.name) is not None for p in asides] == [True]
    assert asides[0].read_bytes() == future_bytes


def test_the_backup_is_deleted_after_the_swap(data_dir):
    _write(data_dir / f"settings.json.v{CURRENT}_backup", _current_file())
    _write(data_dir / "settings.json", _future_file())

    _service(data_dir)

    assert not (data_dir / f"settings.json.v{CURRENT}_backup").exists()


def test_the_bridge_records_a_notice_naming_the_aside_file(data_dir):
    _write(data_dir / f"settings.json.v{CURRENT}_backup", _current_file())
    _write(data_dir / "settings.json", _future_file())

    notice = _service(data_dir).get_restore_notice()

    aside = _asides(data_dir)[0]
    assert notice is not None
    assert notice.aside_path == str(aside)
    assert notice.aside_file == aside.name
    assert (notice.found_version, notice.restored_version) == (FUTURE, CURRENT)


def test_the_store_is_writable_after_the_bridge(data_dir):
    _write(data_dir / f"settings.json.v{CURRENT}_backup", _current_file())
    _write(data_dir / "settings.json", _future_file())

    service = _service(data_dir)
    service.set_polling_interval(45)

    on_disk = json.loads((data_dir / "settings.json").read_text())
    assert on_disk["schema_version"] == CURRENT
    assert on_disk["polling"]["interval_seconds"] == 45


def test_a_second_rollback_restores_the_second_snapshot(data_dir):
    """Upgrade, roll back, change something, upgrade again, roll back again:
    the second rollback must land on the second upgrade's snapshot."""
    _write(data_dir / "settings.json", _current_file("test_first_key"))
    _newer_build_upgrades(data_dir)
    _service(data_dir)  # first rollback

    # Back on this build the user re-saves the board with a new key.
    _write(data_dir / "settings.json", _current_file("test_second_key"))
    _newer_build_upgrades(data_dir)
    service = _service(data_dir)  # second rollback

    assert board_view(service.get_board_settings().boards[0])["local_api_key"] == "test_second_key"


def test_a_backup_that_is_itself_too_new_is_not_swapped_in(data_dir):
    from src.storage.json_store import SchemaTooNewError

    backup_bytes = _write(data_dir / f"settings.json.v{CURRENT}_backup", _future_file())
    future_bytes = _write(data_dir / "settings.json", _future_file())

    with pytest.raises(SchemaTooNewError):
        _service(data_dir)

    assert (data_dir / "settings.json").read_bytes() == future_bytes
    assert (data_dir / f"settings.json.v{CURRENT}_backup").read_bytes() == backup_bytes
    assert _asides(data_dir) == []


# ---------------------------------------------------------------------------
# Too new, no backup: unchanged refusal, actionable message
# ---------------------------------------------------------------------------


def test_a_too_new_file_without_a_backup_is_still_refused(data_dir):
    from src.storage.json_store import SchemaTooNewError

    future_bytes = _write(data_dir / "settings.json", _future_file())

    with pytest.raises(SchemaTooNewError) as excinfo:
        _service(data_dir)

    assert (data_dir / "settings.json").read_bytes() == future_bytes
    assert _asides(data_dir) == []
    assert not (data_dir / "settings_restore_notice.json").exists()
    message = str(excinfo.value)
    assert f"settings.json.v{CURRENT}_backup" in message  # what this build looked for
    assert "reinstall" in message.lower()  # and what the operator can do


# ---------------------------------------------------------------------------
# Not too new: the bridge never fires
# ---------------------------------------------------------------------------


def test_a_current_file_leaves_an_existing_backup_alone(data_dir):
    backup_bytes = _write(data_dir / f"settings.json.v{CURRENT}_backup", _current_file("test_backup_key"))
    current_bytes = _write(data_dir / "settings.json", _current_file())

    service = _service(data_dir)

    assert (data_dir / "settings.json").read_bytes() == current_bytes
    assert (data_dir / f"settings.json.v{CURRENT}_backup").read_bytes() == backup_bytes
    assert _asides(data_dir) == []
    assert service.get_restore_notice() is None


def test_an_older_file_migrates_normally_and_keeps_the_backup(data_dir):
    backup_bytes = _write(data_dir / f"settings.json.v{CURRENT}_backup", _current_file("test_backup_key"))
    older = _current_file()
    older["schema_version"] = CURRENT - 1
    _write(data_dir / "settings.json", older)

    service = _service(data_dir)

    assert json.loads((data_dir / "settings.json").read_text())["schema_version"] == CURRENT
    assert (data_dir / f"settings.json.v{CURRENT}_backup").read_bytes() == backup_bytes
    assert board_view(service.get_board_settings().boards[0])["local_api_key"] == "test_local_key"
    assert service.get_restore_notice() is None


# ---------------------------------------------------------------------------
# The notice over HTTP, and dismissing it
# ---------------------------------------------------------------------------


def _rolled_back_api(data_dir: Path) -> TestClient:
    from src.api_server import app

    _write(data_dir / f"settings.json.v{CURRENT}_backup", _current_file())
    _write(data_dir / "settings.json", _future_file())
    return TestClient(app)


def test_the_api_serves_the_notice(data_dir):
    api = _rolled_back_api(data_dir)

    resp = api.get("/settings/restore-notice")

    assert resp.status_code == 200
    notice = resp.json()["notice"]
    aside = _asides(data_dir)[0]
    assert notice["aside_path"] == str(aside)
    assert notice["aside_file"] == aside.name
    assert (notice["found_version"], notice["restored_version"]) == (FUTURE, CURRENT)
    assert notice["restored_at"].endswith("Z")


def test_the_notice_survives_a_restart_until_dismissed(data_dir):
    from src.settings import service as settings_module

    api = _rolled_back_api(data_dir)
    assert api.get("/settings/restore-notice").json()["notice"] is not None

    settings_module._settings_service = None  # a restart: the file is now current
    assert api.get("/settings/restore-notice").json()["notice"] is not None

    dismissed = api.delete("/settings/restore-notice")
    assert dismissed.status_code == 200
    assert dismissed.json() == {"notice": None}

    settings_module._settings_service = None
    assert api.get("/settings/restore-notice").json() == {"notice": None}
    # Dismissing removes the notice, never the aside file the user may still need.
    assert len(_asides(data_dir)) == 1


def test_no_notice_on_a_normal_boot(data_dir):
    from src.api_server import app

    _write(data_dir / "settings.json", _current_file())

    assert TestClient(app).get("/settings/restore-notice").json() == {"notice": None}


# ---------------------------------------------------------------------------
# End to end: a rolled-back data dir puts today's bytes on the wire
# ---------------------------------------------------------------------------


def _as_the_v3_build(monkeypatch) -> None:
    """Run this process as the last settings-v3 build (the bridge release).

    Its loader is this one with the schema pinned at 3 and the v3->v4
    migration absent: the bridge, the refusal and the backup naming all read
    ``CURRENT_SETTINGS_SCHEMA_VERSION`` at call time. The board readers are
    this build's, which read a v3 (flat) board exactly as v3 did.
    """
    import src.settings.service as service

    monkeypatch.setattr(service, "CURRENT_SETTINGS_SCHEMA_VERSION", 3)
    monkeypatch.setattr(service, "MIGRATIONS", [m for m in service.MIGRATIONS if m[0] <= 3])


def test_a_v4_upgrade_rolled_back_to_the_bridge_build_sends_what_it_sent_before(data_dir, monkeypatch):
    """Plan D8 rollback, end to end: this build migrates a real v3 install to
    v4 (leaving ``settings.json.v3_backup``); the bridge build then boots the
    v4 file, steps back onto the backup, and every board sends the same bytes."""
    from src.api_server import app
    from tests.test_upgrade_fixtures import boot, check_send
    from tests.test_wire_goldens import install_floor_clock, install_wire_recorder

    wire = install_wire_recorder(monkeypatch)
    install_floor_clock(monkeypatch)
    upgraded = boot("v9_10_schema3_multi_board", data_dir)
    assert json.loads((data_dir / "settings.json").read_text())["schema_version"] == 4
    v3_bytes = (data_dir / "settings.json.v3_backup").read_bytes()
    assert upgraded.boards[0]["output"] == "vestaboard"

    _as_the_v3_build(monkeypatch)
    from tests.conftest import _drop_all_singletons
    from tests.test_upgrade_fixtures import Booted

    _drop_all_singletons()
    rolled_back = Booted(data_dir)

    notice = rolled_back.settings.get_restore_notice()
    assert notice is not None and (notice.found_version, notice.restored_version) == (4, 3)
    assert not (data_dir / "settings.json.v3_backup").exists(), "the bridge deletes the backup it restored"
    on_disk = json.loads((data_dir / "settings.json").read_text())
    assert on_disk["schema_version"] == 3
    # The restored file is the v3 snapshot: the connection is flat again.
    assert json.loads(v3_bytes)["board"]["boards"][0]["host"] == on_disk["board"]["boards"][0]["host"] == "192.168.0.10"
    assert "output_config" not in on_disk["board"]["boards"][0]
    assert rolled_back.service.board_init_errors == {}
    client = TestClient(app)
    for index, golden in ((0, "local_flagship_send"), (1, "rw_cloud_send"), (2, "note_array_cloud_send")):
        check_send(golden, client, wire, rolled_back.boards[index]["id"])


def test_a_v4_file_with_a_stale_v3_backup_boots_without_the_bridge(data_dir, monkeypatch):
    """This build reads v4: the pre-written v4 rollback fixture boots as-is
    (no swap, the v3 backup left alone) and sends the A4 golden."""
    from src.api_server import app
    from tests.test_upgrade_fixtures import boot, check_send
    from tests.test_wire_goldens import install_floor_clock, install_wire_recorder

    wire = install_wire_recorder(monkeypatch)
    install_floor_clock(monkeypatch)
    booted = boot("v10_beta_schema4_with_v3_backup", data_dir, root=ROLLBACK_FIXTURES)

    assert booted.settings.get_restore_notice() is None
    assert (data_dir / "settings.json.v3_backup").exists()
    assert booted.service.board_init_errors == {}
    check_send("local_flagship_send", TestClient(app), wire, booted.boards[0]["id"])


def test_the_bridge_build_restores_the_pre_written_v4_fixture(data_dir, monkeypatch):
    """The same fixture on the bridge build: too new, so the v3 backup is
    restored and the board sends the A4 golden."""
    from src.api_server import app
    from tests.test_upgrade_fixtures import boot, check_send
    from tests.test_wire_goldens import install_floor_clock, install_wire_recorder

    wire = install_wire_recorder(monkeypatch)
    install_floor_clock(monkeypatch)
    _as_the_v3_build(monkeypatch)
    booted = boot("v10_beta_schema4_with_v3_backup", data_dir, root=ROLLBACK_FIXTURES)

    assert booted.settings.get_restore_notice() is not None
    assert booted.service.board_init_errors == {}
    check_send("local_flagship_send", TestClient(app), wire, booted.boards[0]["id"])
