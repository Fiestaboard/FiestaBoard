"""Every atomic JSON store must survive a second process saving the same file.

The stores under ``data/`` guard themselves with ``threading.Lock``, which
serialises threads and nothing else. ``data/`` is shared across processes all
the time — one per ``pytest -n auto`` xdist worker, or the API server next to a
CLI script — and with a fixed ``<file>.tmp`` staging name the process that
renames second finds its source already gone:

    FileNotFoundError: [Errno 2] No such file or directory:
      '.../data/config.json.tmp' -> '.../data/config.json'

That is a real CI failure: it took down ``test_welcome_success`` on #1555 and
``test_renders_plain_text`` on main, neither of which has anything to do with
saving config. These tests pin the contract that makes it impossible.
"""

import contextlib
import json
import threading
from pathlib import Path

import pytest

from src.atomic_io import staging_path


@pytest.fixture
def competing_writer(monkeypatch):
    """Run one full competing save inside the window before our rename.

    The competitor does exactly what a second process would: stage a temp file
    under the fixed ``<target>.tmp`` name, then rename it over the target.
    """
    state = {"ran": False}

    real_replace = Path.replace

    def replace_after_a_competing_save(self, target):
        if not state["ran"]:
            state["ran"] = True
            competitor_tmp = Path(f"{target}.tmp")
            competitor_tmp.write_text(json.dumps({"written_by": "the other process"}))
            real_replace(competitor_tmp, target)
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace_after_a_competing_save)
    yield state
    monkeypatch.undo()


def test_staging_path_is_scoped_to_the_process():
    """Two processes must never pick the same staging filename."""
    import os

    assert staging_path(Path("/data/pages.json")) == Path(f"/data/pages.json.{os.getpid()}.tmp")


def _saved_without_error(save, target: Path, competing_writer) -> dict:
    save()
    assert competing_writer["ran"], "the competing save never ran — the test proves nothing"
    assert not list(target.parent.glob(f"{target.name}*.tmp")), "staging file left behind"
    return json.loads(target.read_text())


def test_config_manager_survives_a_competing_process(tmp_path, competing_writer):
    from src.config_manager import ConfigManager

    ConfigManager._instance = None
    ConfigManager._lock = threading.Lock()
    target = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(target))
    cm._config["general"]["timezone"] = "America/Chicago"

    on_disk = _saved_without_error(cm._save_internal, target, competing_writer)
    assert on_disk["general"]["timezone"] == "America/Chicago"

    ConfigManager._instance = None


def test_settings_service_survives_a_competing_process(tmp_path, competing_writer):
    from src.settings.service import SettingsService

    target = tmp_path / "settings.json"
    svc = SettingsService(settings_file=str(target))

    on_disk = _saved_without_error(
        lambda: svc._atomic_write_json({"display": {"reduce_motion": True}}), target, competing_writer
    )
    assert on_disk["display"]["reduce_motion"] is True


def test_page_storage_survives_a_competing_process(tmp_path, competing_writer):
    from src.pages.models import Page
    from src.pages.storage import PageStorage

    target = tmp_path / "pages.json"
    storage = PageStorage(storage_file=str(target))
    storage._pages["p1"] = Page(id="p1", name="Kept", type="template", template=["hi", "", "", "", "", ""])

    on_disk = _saved_without_error(storage._save, target, competing_writer)
    assert [p["name"] for p in on_disk["pages"]] == ["Kept"]


def test_schedule_storage_survives_a_competing_process(tmp_path, competing_writer):
    from src.schedules.storage import ScheduleStorage

    target = tmp_path / "schedules.json"
    storage = ScheduleStorage(storage_file=str(target))
    storage._default_page_by_board = {"board-1": "page-9"}

    on_disk = _saved_without_error(storage._save, target, competing_writer)
    assert on_disk["default_page_by_board"] == {"board-1": "page-9"}


def test_collection_storage_survives_a_competing_process(tmp_path, competing_writer):
    from src.collections.models import Collection
    from src.collections.storage import CollectionStorage

    target = tmp_path / "collections.json"
    storage = CollectionStorage(storage_file=str(target))
    collection = Collection(name="Mornings", page_ids=["page-1"])
    storage._collections[collection.id] = collection

    on_disk = _saved_without_error(storage._save, target, competing_writer)
    assert [c["name"] for c in on_disk["collections"]] == ["Mornings"]


def test_auth_service_survives_a_competing_process(tmp_path, competing_writer):
    from src.auth.service import AuthService

    target = tmp_path / "auth.json"
    svc = AuthService(auth_file=target)
    svc._data["auth_pref"] = "enabled"

    on_disk = _saved_without_error(svc._save, target, competing_writer)
    assert on_disk["auth_pref"] == "enabled"


def test_auth_file_keeps_owner_only_permissions_through_a_competing_save(tmp_path, competing_writer):
    """The credential store is 0600; a per-process staging name must not widen it."""
    import stat

    from src.auth.service import AuthService

    target = tmp_path / "auth.json"
    svc = AuthService(auth_file=target)
    svc._save()

    assert competing_writer["ran"]
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0, f"auth.json is group/world accessible: {mode:o}"


def test_a_crashed_process_leaves_a_staging_file_that_does_not_block_the_next_save(tmp_path):
    """A SIGKILLed writer's orphaned staging file must not wedge later saves."""
    from src.config_manager import ConfigManager

    ConfigManager._instance = None
    ConfigManager._lock = threading.Lock()
    target = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(target))

    orphan = staging_path(target)
    orphan.write_text("{ truncated by a crash")

    cm._config["general"]["timezone"] = "America/Chicago"
    cm._save_internal()

    assert json.loads(target.read_text())["general"]["timezone"] == "America/Chicago"
    with contextlib.suppress(FileNotFoundError):
        orphan.unlink()

    ConfigManager._instance = None
