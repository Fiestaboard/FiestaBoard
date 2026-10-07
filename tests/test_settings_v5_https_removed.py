"""Settings v5: the HTTPS (Beta) feature is gone (settings reorg, PR B).

What this module pins, in order:

1. the v4 -> v5 migration drops ``beta.https_enabled`` — on or off — keeps
   every other beta flag, is idempotent, and logs the count it changed;
2. a v4 install with HTTPS on upgrades to v5 with the flag gone and its
   pre-migration snapshot in ``settings.json.v4_backup``;
3. (settings v6 then removed the beta API altogether);
4. startup removes the self-signed cert files FiestaBoard generated in
   ``<data>/certs/`` — those two files, only when the cert is its self-signed
   one, and nothing else;
5. the image no longer ships the HTTPS nginx config, the cert module or the
   entrypoint branch that switched nginx over.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
from pathlib import Path

import pytest

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

        assert CURRENT_SETTINGS_SCHEMA_VERSION >= 5
        assert (5, _migrate_v4_to_v5) in MIGRATIONS


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
    # Settings v6 then moves the remaining beta flags into "plugins" (and v7
    # drops the output-plugin opt-in).
    assert on_disk["schema_version"] == 7
    assert "beta" not in on_disk
    assert "https_enabled" not in on_disk["plugins"]
    assert on_disk["plugins"]["transition_plugins_enabled"] is True
    assert service.get_plugin_settings().transition_plugins_enabled is True


def test_the_https_on_upgrade_fixture_boots_without_the_flag_or_its_certs(_isolated_data_dir):
    """The real-shaped v4 install with HTTPS on (and the cert pair the old
    entrypoint generated) boots with the flag dropped and the certs gone."""
    from tests.test_upgrade_fixtures import FIXTURES, boot

    original = (FIXTURES / "v10_beta_schema4_https_on" / "settings.json").read_bytes()
    assert json.loads(original)["beta"]["https_enabled"] is True
    certs = _plant_certs(_isolated_data_dir)

    boot("v10_beta_schema4_https_on", _isolated_data_dir)

    on_disk = json.loads((_isolated_data_dir / "settings.json").read_text())
    assert on_disk["schema_version"] == 7  # v5, v6, then v7
    assert "beta" not in on_disk  # settings v6 moved the rest into "plugins"
    assert "https_enabled" not in on_disk["plugins"]
    assert on_disk["plugins"]["transition_plugins_enabled"] is False
    assert (_isolated_data_dir / "settings.json.v4_backup").read_bytes() == original
    assert not certs.exists()


def test_plugin_settings_have_no_https_flag():
    from src.settings.service import PluginSettings

    assert "https_enabled" not in PluginSettings.from_dict({"https_enabled": True}).to_dict()


# ---------------------------------------------------------------------------
# 3. The beta API — gone in settings v6 (tests/test_settings_v6_per_display_transitions.py)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 4. Leftover cert files
# ---------------------------------------------------------------------------


def _pem(der: bytes) -> str:
    body = base64.encodebytes(der).decode()
    return f"-----BEGIN CERTIFICATE-----\n{body}-----END CERTIFICATE-----\n"


#: Stand-in DER for the pair the old entrypoint generated: self-signed, so
#: its issuer and subject both carry ``O = FiestaBoard, CN = fiestaboard.local``.
GENERATED_DER = b"\x30issuer O=FiestaBoard CN=fiestaboard.local subject O=FiestaBoard CN=fiestaboard.local"
#: A user's own cert for the same host name, issued by someone else.
USER_DER = b"\x30issuer O=Example CA CN=Example Root subject O=FiestaBoard CN=fiestaboard.local"


def _plant_certs(data_dir: Path, der: bytes = GENERATED_DER) -> Path:
    certs = data_dir / "certs"
    certs.mkdir(parents=True)
    (certs / "fiestaboard.crt").write_text(_pem(der))
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

    def test_it_keeps_a_pair_the_user_put_there(self, tmp_path):
        """The old beta API allowed a manual cert drop under the same names;
        a key FiestaBoard did not generate must survive the upgrade."""
        from src.system.legacy_https import remove_legacy_https_certs

        certs = _plant_certs(tmp_path, der=USER_DER)
        assert remove_legacy_https_certs(tmp_path) == 0
        assert sorted(p.name for p in certs.iterdir()) == ["fiestaboard.crt", "fiestaboard.key"]

    def test_it_keeps_a_cert_it_cannot_read(self, tmp_path):
        from src.system.legacy_https import remove_legacy_https_certs

        certs = tmp_path / "certs"
        certs.mkdir()
        (certs / "fiestaboard.crt").write_text("not a pem")
        (certs / "fiestaboard.key").write_text("test_key_placeholder")
        assert remove_legacy_https_certs(tmp_path) == 0
        assert (certs / "fiestaboard.key").exists()

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
