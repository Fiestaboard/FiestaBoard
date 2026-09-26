"""A settings write the OS refuses must not report success (Phase 2, Task 10b).

``SettingsService._save_to_file`` was the only log-without-raise persistence
path in the codebase — every other store (pages, collections, schedules,
panels, config_manager) logs *and* re-raises. 24 setter call sites and ~20
endpoints therefore answered HTTP 200 having persisted nothing: on a full
disk or a read-only ``data/`` the UI showed the new value, the in-memory
object held it, and the next restart silently reverted it.

Background paths (boot-time seed save, the expiry GC in
``get_temporary_override`` / ``consume_temporary_override``) are the
deliberate exception: they run outside a request, so they log and continue
rather than take the process down. Those exceptions are pinned here too, so
"it is swallowed" can never quietly come back for the request paths.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.settings.service import SettingsService, TemporaryOverride


@pytest.fixture
def client():
    # raise_server_exceptions=False so we observe the 500 the ASGI server
    # would send rather than having the exception re-raised into the test.
    return TestClient(app, raise_server_exceptions=False)


def _service(tmp_path) -> SettingsService:
    return SettingsService(str(tmp_path / "settings.json"))


def _make_undirectory(tmp_path):
    """Return a path whose parent is a regular file.

    Writing there fails with ``NotADirectoryError`` (an ``OSError``) for
    every user including root, so this stands in for a read-only or full
    data directory without depending on permission bits the test container
    ignores.
    """
    blocker = tmp_path / "data-dir-gone"
    blocker.write_text("this is a file, not a directory")
    return blocker / "settings.json"


class TestServiceLevel:
    def test_a_refused_write_propagates_out_of_a_setter(self, tmp_path):
        service = _service(tmp_path)
        service.set_polling_interval(30)  # sanity: the happy path works

        service._store._path = _make_undirectory(tmp_path)

        with pytest.raises(OSError):
            service.set_polling_interval(45)

    def test_boot_seed_save_failure_does_not_kill_the_service(self, tmp_path):
        """Startup must survive an unwritable data dir — read-only settings
        are still better than a process that will not boot."""
        with patch.object(SettingsService, "_save_to_file", side_effect=OSError(28, "No space left on device")):
            service = _service(tmp_path)
        assert service.get_polling_settings() is not None

    def test_get_override_gc_failure_does_not_break_the_read(self, tmp_path):
        """The display loop reads the override every tick; a failed GC write
        must not turn a read into an exception."""
        service = _service(tmp_path)
        service.set_temporary_override(TemporaryOverride(page_id="p1", expires_at="2000-01-01T00:00:00+00:00"))
        service._store._path = _make_undirectory(tmp_path)

        assert service.get_temporary_override() is None

    def test_consume_override_gc_failure_does_not_break_the_read(self, tmp_path):
        service = _service(tmp_path)
        service.set_temporary_override(TemporaryOverride(page_id="p1", expires_at="2000-01-01T00:00:00+00:00"))
        service._store._path = _make_undirectory(tmp_path)

        # Returns the expired override so the display loop can apply its
        # revert mode, even though the clearing write could not be saved.
        assert service.consume_temporary_override() is not None


class TestEndpointLevel:
    def test_settings_put_returns_5xx_when_the_write_fails(self, client):
        """The defect in one line: this used to be a 200 having saved nothing."""
        with patch(
            "src.storage.json_store.write_json_atomic",
            side_effect=OSError(28, "No space left on device"),
        ):
            response = client.put("/settings/polling", json={"interval_seconds": 45})
        assert response.status_code >= 500
