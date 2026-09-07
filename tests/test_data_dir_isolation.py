"""Every store's *default* path resolves through the data-dir seam (#1762).

Historically each store resolved ``<repo>/data`` on its own via
``Path(__file__)`` gymnastics — eleven independent copies — so nothing short
of rebinding every constructor kept the test suite off the developer's real
``data/`` directory. ``src.paths.get_data_dir()`` is the one seam: it honors
``FIESTABOARD_DATA_DIR``, which the autouse ``_isolated_data_dir`` fixture in
``tests/conftest.py`` points at a throwaway ``tmp_path``.

This test constructs each store with **defaults** (no explicit path kwarg)
and asserts the resulting path landed under the isolated temp dir, not under
the repo. Before the seam existed this failed for every store.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_DATA_DIR = REPO_ROOT / "data"

# Captured while this module is being *imported* — i.e. at collection time,
# before any fixture has run. See TestSessionDataDirFloor below.
ENV_AT_IMPORT_TIME = os.environ.get("FIESTABOARD_DATA_DIR")


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Point the seam at a throwaway dir and drop the ConfigManager singleton.

    Self-contained on purpose: this file is the guard for the seam itself, so
    it must not silently depend on the conftest fixture it exists to verify.
    """
    from src.config_manager import ConfigManager

    data_dir = tmp_path / "isolated-data"
    monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(data_dir))
    ConfigManager._instance = None  # type: ignore[attr-defined]
    yield data_dir
    ConfigManager._instance = None  # type: ignore[attr-defined]


def _assert_isolated(path: Path, data_dir: Path, what: str) -> None:
    resolved = Path(path).resolve()
    assert not resolved.is_relative_to(REPO_DATA_DIR), f"{what} default resolved into the repo data/: {resolved}"
    assert resolved.is_relative_to(data_dir.resolve()), f"{what} default did not honor FIESTABOARD_DATA_DIR: {resolved}"


def test_settings_service_default_is_isolated(isolated_env):
    from src.settings.service import SettingsService

    _assert_isolated(SettingsService().settings_file, isolated_env, "SettingsService")


def test_page_storage_default_is_isolated(isolated_env):
    from src.pages.storage import PageStorage

    _assert_isolated(PageStorage().storage_file, isolated_env, "PageStorage")


def test_schedule_storage_default_is_isolated(isolated_env):
    from src.schedules.storage import ScheduleStorage

    _assert_isolated(ScheduleStorage().storage_file, isolated_env, "ScheduleStorage")


def test_collection_storage_default_is_isolated(isolated_env):
    from src.collections.storage import CollectionStorage

    _assert_isolated(CollectionStorage().storage_file, isolated_env, "CollectionStorage")


def test_panel_storage_default_is_isolated(isolated_env):
    from src.panels.storage import PanelStorage

    _assert_isolated(PanelStorage().storage_file, isolated_env, "PanelStorage")


def test_config_manager_default_is_isolated(isolated_env):
    from src.config_manager import ConfigManager

    _assert_isolated(ConfigManager()._config_path, isolated_env, "ConfigManager")


def test_backup_service_default_is_isolated(isolated_env):
    from src.backup.service import BackupService

    _assert_isolated(BackupService().data_dir, isolated_env, "BackupService")


def test_auth_service_default_is_isolated(isolated_env):
    from src.auth.service import AuthService

    _assert_isolated(AuthService()._path, isolated_env, "AuthService")


def test_trigger_dismissal_store_default_is_isolated(isolated_env):
    from src.triggers.service import TriggerService

    _assert_isolated(TriggerService()._dismissals_file, isolated_env, "TriggerService dismissal store")


def test_external_plugins_dir_default_is_isolated(isolated_env):
    from src.plugins.sources import get_external_plugins_dir

    _assert_isolated(get_external_plugins_dir(), isolated_env, "get_external_plugins_dir")


class TestSessionDataDirFloor:
    """``FIESTABOARD_DATA_DIR`` is set for the whole session, not just per test (#1894).

    The autouse ``_isolated_data_dir`` fixture is function-scoped, so it leaves
    two windows uncovered — collection time (``src/api_server.py`` resolves the
    auth file while it is being imported) and the moment after a test's
    ``monkeypatch`` teardown (background threads a test started keep logging,
    and the log handler re-enters ``ConfigManager()``). In either window an
    unset variable sent ``get_data_dir()`` at the checkout's ``data/``, writing
    ``config.json`` and ``logs/app.log`` into the repo.

    These assertions are the non-vacuous half of this file: they fail if the
    ``pytest_configure`` hook in ``tests/conftest.py`` is removed, even though
    the function-scoped fixture would still be in place.
    """

    def test_env_is_already_set_when_test_modules_are_imported(self):
        assert ENV_AT_IMPORT_TIME, (
            "FIESTABOARD_DATA_DIR was unset while this module was imported — "
            "anything resolving the data dir at import/collection time writes the repo"
        )
        assert not Path(ENV_AT_IMPORT_TIME).resolve().is_relative_to(REPO_ROOT)

    def test_a_floor_remains_when_no_function_fixture_is_active(self, tmp_path):
        """The value ``monkeypatch`` restores to must be a temp dir, not "unset".

        This is the window the function-scoped fixture cannot cover: a
        background thread a test started keeps logging after that test's
        teardown, re-enters ``ConfigManager()`` and resolves the data dir with
        nothing patched. Measured for real — a nested pytest session runs one
        test from this file with ``FIESTABOARD_DATA_DIR`` scrubbed from its
        environment, and a ``-p`` plugin records the surviving value from
        ``pytest_sessionfinish``, after every function fixture is finalized.
        """
        probe = tmp_path / "floor_probe.py"
        out = tmp_path / "floor.txt"
        probe.write_text(
            "import os\n"
            "\n"
            "\n"
            "def pytest_sessionfinish(session, exitstatus):\n"
            "    out = os.environ['FLOOR_PROBE_OUT']\n"
            "    with open(out, 'w') as fh:\n"
            "        fh.write(os.environ.get('FIESTABOARD_DATA_DIR', ''))\n"
        )
        env = dict(os.environ)
        env.pop("FIESTABOARD_DATA_DIR", None)
        env.pop("PYTEST_XDIST_WORKER", None)
        env["FLOOR_PROBE_OUT"] = str(out)
        env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                f"{__file__}::TestSessionDataDirFloor::test_get_data_dir_never_resolves_inside_the_repository",
                "-q",
                "-p",
                "floor_probe",
                "-p",
                "no:cacheprovider",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"nested session failed:\n{result.stdout}\n{result.stderr}"
        floor = out.read_text().strip()
        assert floor, "FIESTABOARD_DATA_DIR was left *unset* once the function fixtures were torn down"
        assert not Path(floor).resolve().is_relative_to(REPO_ROOT), (
            f"the surviving data dir points into the checkout: {floor}"
        )

    def test_data_dir_is_unique_per_xdist_worker(self):
        worker = os.environ.get("PYTEST_XDIST_WORKER")
        if not worker:
            pytest.skip("not running under xdist")
        assert worker in str(ENV_AT_IMPORT_TIME), (
            f"session data dir {ENV_AT_IMPORT_TIME!r} is not keyed by worker {worker!r} — "
            "parallel workers would share one directory"
        )

    def test_get_data_dir_never_resolves_inside_the_repository(self):
        from src.paths import get_data_dir

        assert not get_data_dir().resolve().is_relative_to(REPO_ROOT)


class TestAbsoluteContainerPathsGoThroughTheSeam:
    """Paths that used to be hard-coded ``/app/data/...`` now follow the seam (#1881)."""

    def test_log_dir_follows_the_data_dir_seam(self):
        from src import api_server
        from src.paths import get_data_dir

        assert api_server.LOG_DIR is None, "production must leave the LOG_DIR seam unset"
        assert api_server._log_dir() == get_data_dir() / "logs"
        assert api_server._log_file() == get_data_dir() / "logs" / "app.log"
        assert not api_server._log_dir().resolve().is_relative_to(REPO_ROOT)

    def test_cert_dir_follows_the_data_dir_seam(self, monkeypatch):
        from src.paths import get_data_dir
        from src.system import https_certs

        monkeypatch.delenv("FIESTABOARD_CERT_DIR", raising=False)
        assert https_certs._cert_dir() == get_data_dir() / "certs"
        assert not https_certs._cert_dir().resolve().is_relative_to(REPO_ROOT)
