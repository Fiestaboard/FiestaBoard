"""First-run detection off ``config.json`` (plan D13, D18).

``is_first_run`` is "no board has a usable output AND the setup wizard was
neither completed nor skipped". Pinned here:

- a board an output plugin drives is usable on its own — a Pixoo-only
  install is not "first run" forever because it has no Vestaboard key;
- the wizard's outcome is stored server-side (``settings.json`` →
  ``wizard.state``, ``GET``/``PUT /settings/wizard``): skipping the wizard
  sticks across browsers, not just in one browser's ``localStorage``;
- the key is written only once set, so a file saved by an older build
  round-trips unchanged (the ``beta.output_plugins_enabled`` precedent);
- ``DELETE /config/board`` (the wizard-reset helper) clears it again.

Upgrades are pinned per fixture in ``tests/test_upgrade_fixtures.py``.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_credential_env(monkeypatch):
    """The runner's board env vars would make a fresh install read as configured."""
    for name in (
        "BOARD_READ_WRITE_KEY",
        "FB_READ_WRITE_KEY",
        "BOARD_LOCAL_API_KEY",
        "FB_LOCAL_API_KEY",
        "BOARD_HOST",
        "FB_HOST",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def data_dir(_isolated_data_dir):
    return _isolated_data_dir


@pytest.fixture
def client(data_dir):
    from src.api_server import app

    return TestClient(app)


def _first_run(client) -> bool:
    return client.get("/config/validate").json()["is_first_run"]


def _settings():
    from src.settings.service import get_settings_service

    return get_settings_service()


def test_a_fresh_install_is_first_run(client):
    assert _first_run(client) is True


@pytest.mark.parametrize("state", ["completed", "skipped"])
def test_a_finished_or_skipped_wizard_is_not_first_run(client, state):
    resp = client.put("/settings/wizard", json={"state": state})
    assert resp.status_code == 200
    assert resp.json() == {"state": state}
    assert _first_run(client) is False


def test_the_wizard_state_reads_back(client):
    assert client.get("/settings/wizard").json() == {"state": None}
    client.put("/settings/wizard", json={"state": "skipped"})
    assert client.get("/settings/wizard").json() == {"state": "skipped"}


def test_an_unknown_wizard_state_is_422(client):
    assert client.put("/settings/wizard", json={"state": "maybe"}).status_code == 422


def test_the_wizard_state_survives_a_restart(client, data_dir):
    from tests.conftest import _drop_all_singletons

    client.put("/settings/wizard", json={"state": "completed"})
    _drop_all_singletons()
    assert _settings().get_wizard_state() == "completed"


def test_an_unset_wizard_state_is_not_written(client, data_dir):
    _settings().set_polling_interval(30)
    assert "wizard" not in json.loads((data_dir / "settings.json").read_text())


def test_an_output_plugin_board_alone_is_not_first_run(client):
    """Not a Vestaboard and no Vestaboard key anywhere: still a configured install."""
    _settings().set_boards(
        [{"name": "Sign", "device_type": "panel", "output": "acme_sign", "output_config": {"host": "192.0.2.9"}}]
    )
    assert _first_run(client) is False


def test_a_fiestapanel_board_alone_is_not_first_run(client):
    _settings().set_boards([{"name": "TV", "device_type": "flagship", "api_mode": "virtual"}])
    assert _first_run(client) is False


def test_resetting_the_board_config_clears_the_wizard_state(client):
    client.put("/settings/wizard", json={"state": "skipped"})
    assert client.delete("/config/board").status_code == 200
    assert client.get("/settings/wizard").json() == {"state": None}
    assert _first_run(client) is True
