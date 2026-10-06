"""Settings v5: the HTTPS (Beta) feature is gone (settings reorg, PR B).

What this module pins, in order:

1. the v4 -> v5 migration drops ``beta.https_enabled`` — on or off — keeps
   every other beta flag, is idempotent, and logs the count it changed;
2. a v4 install with HTTPS on upgrades to v5 with the flag gone and its
   pre-migration snapshot in ``settings.json.v4_backup``;
3. the beta API no longer reports or accepts the flag, and has no cert
   status or restart hint;
4. startup removes the self-signed cert files FiestaBoard generated in
   ``<data>/certs/`` — those two files and nothing else;
5. the image no longer ships the HTTPS nginx config, the cert module or the
   entrypoint branch that switched nginx over.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent


def _v4_data(beta: dict | None) -> dict:
    data: dict = {"schema_version": 4, "board": {"board_type": "black", "devices": ["flagship"]}}
    if beta is not None:
        data["beta"] = beta
    return data


# ---------------------------------------------------------------------------
# 1. The migration
# ---------------------------------------------------------------------------


class TestMigrateV4ToV5:
    @pytest.mark.parametrize("was_on", [True, False])
    def test_it_drops_https_enabled_whatever_its_value(self, was_on):
        from src.settings.service import _migrate_v4_to_v5

        data = _v4_data({"https_enabled": was_on, "transition_plugins_enabled": True})
        assert _migrate_v4_to_v5(data) == 1
        assert data["beta"] == {"transition_plugins_enabled": True}

    def test_it_keeps_the_other_beta_flags(self):
        from src.settings.service import _migrate_v4_to_v5

        data = _v4_data({"https_enabled": True, "transition_plugins_enabled": False, "output_plugins_enabled": True})
        _migrate_v4_to_v5(data)
        assert data["beta"] == {"transition_plugins_enabled": False, "output_plugins_enabled": True}

    def test_it_is_idempotent(self):
        from src.settings.service import _migrate_v4_to_v5

        data = _v4_data({"https_enabled": True, "transition_plugins_enabled": False})
        _migrate_v4_to_v5(data)
        once = copy.deepcopy(data)
        assert _migrate_v4_to_v5(data) == 0
        assert data == once

    @pytest.mark.parametrize("beta", [None, {}, "not-a-dict", {"transition_plugins_enabled": True}])
    def test_a_file_without_the_flag_needs_nothing(self, beta):
        from src.settings.service import _migrate_v4_to_v5

        data = _v4_data(beta)
        before = copy.deepcopy(data)
        assert _migrate_v4_to_v5(data) == 0
        assert data == before

    def test_it_is_the_registered_v5_migration(self):
        from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION, MIGRATIONS, _migrate_v4_to_v5

        assert CURRENT_SETTINGS_SCHEMA_VERSION == 5
        assert MIGRATIONS[-1] == (5, _migrate_v4_to_v5)


# ---------------------------------------------------------------------------
# 2. A v4 install with HTTPS on
# ---------------------------------------------------------------------------


def test_a_v4_file_with_https_on_loads_at_v5_without_it(tmp_path, caplog):
    from src.settings.service import SettingsService

    path = tmp_path / "settings.json"
    path.write_text(json.dumps(_v4_data({"https_enabled": True, "transition_plugins_enabled": True})))
    v4 = path.read_bytes()

    with caplog.at_level(logging.INFO, logger="src.settings.service"):
        service = SettingsService(settings_file=str(path))

    assert "Settings schema migration v4->v5: 1 change(s) applied" in caplog.text
    assert (tmp_path / "settings.json.v4_backup").read_bytes() == v4
    on_disk = json.loads(path.read_text())
    assert on_disk["schema_version"] == 5
    assert "https_enabled" not in on_disk["beta"]
    assert on_disk["beta"]["transition_plugins_enabled"] is True
    assert service.get_beta_settings().transition_plugins_enabled is True


def test_the_https_on_upgrade_fixture_boots_without_the_flag_or_its_certs(_isolated_data_dir):
    """The real-shaped v4 install with HTTPS on (and the cert pair the old
    entrypoint generated) boots with the flag dropped and the certs gone."""
    from tests.test_upgrade_fixtures import FIXTURES, boot

    original = (FIXTURES / "v10_beta_schema4_https_on" / "settings.json").read_bytes()
    assert json.loads(original)["beta"]["https_enabled"] is True
    certs = _plant_certs(_isolated_data_dir)

    boot("v10_beta_schema4_https_on", _isolated_data_dir)

    on_disk = json.loads((_isolated_data_dir / "settings.json").read_text())
    assert on_disk["schema_version"] == 5
    assert on_disk["beta"] == {"transition_plugins_enabled": False}
    assert (_isolated_data_dir / "settings.json.v4_backup").read_bytes() == original
    assert not certs.exists()


def test_beta_settings_have_no_https_flag():
    from src.settings.service import BetaSettings

    assert "https_enabled" not in BetaSettings().to_dict()
    assert "https_enabled" not in BetaSettings.from_dict({"https_enabled": True}).to_dict()


# ---------------------------------------------------------------------------
# 3. The beta API
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    from src.api_server import app

    return TestClient(app)


def test_get_beta_reports_only_the_flags(client):
    body = client.get("/settings/beta").json()
    assert set(body) == {"settings"}
    assert "https_enabled" not in body["settings"]
    assert body["settings"]["transition_plugins_enabled"] is False


def test_put_beta_ignores_a_stale_https_flag(client):
    response = client.put("/settings/beta", json={"https_enabled": True})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"settings"}
    assert "https_enabled" not in body["settings"]
    assert "https_enabled" not in client.get("/settings/all").json()["beta"]


def test_put_beta_still_toggles_transition_plugins(client):
    response = client.put("/settings/beta", json={"transition_plugins_enabled": True})
    assert response.status_code == 200
    assert response.json() == {"settings": {"transition_plugins_enabled": True, "output_plugins_enabled": False}}


# ---------------------------------------------------------------------------
# 4. Leftover cert files
# ---------------------------------------------------------------------------


def _plant_certs(data_dir: Path) -> Path:
    certs = data_dir / "certs"
    certs.mkdir(parents=True)
    (certs / "fiestaboard.crt").write_text("test_cert_placeholder")
    (certs / "fiestaboard.key").write_text("test_key_placeholder")
    return certs


class TestLegacyCertCleanup:
    def test_it_removes_the_generated_pair_and_the_emptied_dir(self, tmp_path):
        from src.system.legacy_https import remove_legacy_https_certs

        certs = _plant_certs(tmp_path)
        assert remove_legacy_https_certs(tmp_path) == 2
        assert not certs.exists()

    def test_it_leaves_files_it_did_not_generate(self, tmp_path):
        from src.system.legacy_https import remove_legacy_https_certs

        certs = _plant_certs(tmp_path)
        (certs / "my-own.pem").write_text("test_user_file")
        assert remove_legacy_https_certs(tmp_path) == 2
        assert sorted(p.name for p in certs.iterdir()) == ["my-own.pem"]

    def test_no_certs_dir_is_a_no_op(self, tmp_path):
        from src.system.legacy_https import remove_legacy_https_certs

        assert remove_legacy_https_certs(tmp_path) == 0
        assert list(tmp_path.iterdir()) == []

    def test_a_failed_delete_is_logged_not_raised(self, tmp_path, monkeypatch, caplog):
        from src.system.legacy_https import remove_legacy_https_certs

        _plant_certs(tmp_path)

        def refuse(self, *args, **kwargs):
            raise PermissionError("read-only")

        monkeypatch.setattr(Path, "unlink", refuse)
        with caplog.at_level(logging.WARNING, logger="src.system.legacy_https"):
            assert remove_legacy_https_certs(tmp_path) == 0
        assert "fiestaboard.crt" in caplog.text

    def test_startup_removes_them_from_the_data_dir(self, _isolated_data_dir):
        from src.api_server import _run_startup_migrations

        certs = _plant_certs(_isolated_data_dir)
        _run_startup_migrations()
        assert not certs.exists()


# ---------------------------------------------------------------------------
# 5. The image
# ---------------------------------------------------------------------------


class TestImageServesPlainHttp:
    def test_the_https_nginx_config_is_gone(self):
        assert not (REPO_ROOT / "nginx.https.conf").exists()
        assert "nginx.https.conf" not in (REPO_ROOT / "Dockerfile").read_text()

    def test_the_cert_module_and_cli_are_gone(self):
        assert not (REPO_ROOT / "src" / "system" / "https_certs.py").exists()
        assert not (REPO_ROOT / "src" / "system" / "https_certs_cli.py").exists()

    def test_the_entrypoint_no_longer_switches_nginx(self):
        entrypoint = (REPO_ROOT / "entrypoint.sh").read_text()
        for marker in ("https_enabled", "https_certs", "nginx.https.conf", "nginx.http.conf", "configure_https"):
            assert marker not in entrypoint, marker
