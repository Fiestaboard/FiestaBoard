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

from pathlib import Path

import pytest

REPO_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


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


def test_external_plugins_dir_default_is_isolated(isolated_env):
    from src.plugins.sources import get_external_plugins_dir

    _assert_isolated(get_external_plugins_dir(), isolated_env, "get_external_plugins_dir")
