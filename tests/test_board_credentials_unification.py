"""Board credentials unification (issue #1760).

Board connection credentials historically lived in TWO places: the legacy
``config.json -> board.*`` block (written by the setup wizard and env-var
seeding) and the maintained ``settings.json -> board.boards[]`` store
(written by Settings). They were copied once at first boot and then
diverged — the structural root of the #948/#1102 "board went offline after
I changed a key" family.

These tests pin the unified contract:

* A schema-versioned settings migration imports the legacy config.json
  credentials exactly once (gated on ``schema_version``, never heuristics),
  and never overwrites a maintained settings credential.
* Every runtime reader of board credentials goes through the settings
  store; nothing silently falls back to the stale config.json copy.
* ``GET/PUT /config/board`` is a deprecated shim over settings — the wire
  shapes are unchanged, ``Deprecation``/``Link`` successor headers are set,
  and writes land in settings.json only. The config.json board block stays
  on disk untouched as a rollback copy for older versions.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

# Clearly-fake test credentials (never real keys).
LIVE_KEY = "test_live_settings_key"
STALE_KEY = "test_stale_config_key"
LIVE_HOST = "192.0.2.20"
STALE_HOST = "192.0.2.99"

_BOARD_ENV_VARS = (
    "BOARD_API_MODE",
    "BOARD_LOCAL_API_KEY",
    "BOARD_HOST",
    "BOARD_READ_WRITE_KEY",
    "BOARD_NOTE_ARRAY_TOKEN",
    "FB_API_MODE",
    "FB_LOCAL_API_KEY",
    "FB_HOST",
    "FB_READ_WRITE_KEY",
)


@pytest.fixture
def data_dir(_isolated_data_dir: Path, monkeypatch) -> Path:
    """The isolated data dir, with board env vars cleared for determinism."""
    for var in _BOARD_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    _isolated_data_dir.mkdir(parents=True, exist_ok=True)
    return _isolated_data_dir


@pytest.fixture
def client(data_dir) -> TestClient:
    """A TestClient whose services resolve from the isolated data dir."""
    from src.api_server import app

    return TestClient(app)


def _write_config(data_dir: Path, **board) -> None:
    """Write a legacy config.json with the given board block fields."""
    block = {
        "api_mode": "local",
        "local_api_key": "",
        "cloud_key": "",
        "note_array_token": "",
        "host": "",
        "transition_strategy": None,
        "transition_interval_ms": None,
        "transition_step_size": None,
    }
    block.update(board)
    (data_dir / "config.json").write_text(json.dumps({"board": block}))


def _board(**overrides) -> dict:
    board = {
        "id": "b1",
        "name": "My Board",
        "device_type": "flagship",
        "board_color": "black",
        "enabled": True,
        "paused": False,
        "api_mode": "local",
        "host": "",
        "port": 7000,
        "local_api_key": "",
        "cloud_key": "",
    }
    board.update(overrides)
    return board


def _write_settings(data_dir: Path, boards: list[dict], schema_version: int = 2) -> None:
    payload = {
        "schema_version": schema_version,
        "board": {"board_type": "black", "boards": boards},
    }
    (data_dir / "settings.json").write_text(json.dumps(payload))


def _settings_on_disk(data_dir: Path) -> dict:
    return json.loads((data_dir / "settings.json").read_text())


def _new_settings_service():
    from src.settings.service import SettingsService

    return SettingsService()


# ── 1. schema-versioned migration ───────────────────────────────────────────


class TestLegacyCredentialMigration:
    """The legacy config.json board block is imported via a settings schema
    migration — run once, gated on schema_version, idempotent."""

    def test_upgrade_imports_config_credentials_into_settings(self, data_dir):
        """Legacy install: config.json has the credentials, settings.json has
        a credential-less board at a pre-migration schema version. After boot
        the settings store carries the credentials and is stamped with the
        new schema version."""
        from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION

        _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST, api_mode="local")
        _write_settings(data_dir, [_board()], schema_version=2)

        svc = _new_settings_service()

        first = svc.get_board_settings().boards[0]
        assert first["local_api_key"] == STALE_KEY
        assert first["host"] == STALE_HOST

        on_disk = _settings_on_disk(data_dir)
        assert CURRENT_SETTINGS_SCHEMA_VERSION >= 3, "board-credential migration must bump the settings schema"
        assert on_disk["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION
        assert on_disk["board"]["boards"][0]["local_api_key"] == STALE_KEY

    def test_migration_is_gated_on_schema_version_not_heuristics(self, data_dir):
        """A settings file already at the current schema version is never
        re-seeded from config.json — even when its board has no credentials.

        This is the root #948 fix: a user who cleared or changed credentials
        in Settings must never have the stale config.json copy resurrected by
        a boot-time heuristic ("board has no key, copy it over again")."""
        from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION

        _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST)
        _write_settings(data_dir, [_board()], schema_version=CURRENT_SETTINGS_SCHEMA_VERSION)

        svc = _new_settings_service()

        first = svc.get_board_settings().boards[0]
        assert first.get("local_api_key", "") == "", "stale config.json credentials were re-copied heuristically"
        assert first.get("host", "") == ""

    def test_migration_never_overwrites_maintained_settings_credentials(self, data_dir):
        """Precedence: settings is the maintained copy. A board that already
        carries a credential keeps it through the migration, and re-running
        the boot (idempotence) changes nothing."""
        from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION

        _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST)
        _write_settings(data_dir, [_board(local_api_key=LIVE_KEY, host=LIVE_HOST)], schema_version=2)

        svc = _new_settings_service()
        first = svc.get_board_settings().boards[0]
        assert first["local_api_key"] == LIVE_KEY
        assert first["host"] == LIVE_HOST

        # Idempotent re-run: a second boot leaves everything as-is.
        svc2 = _new_settings_service()
        first2 = svc2.get_board_settings().boards[0]
        assert first2["local_api_key"] == LIVE_KEY
        assert first2["host"] == LIVE_HOST
        assert _settings_on_disk(data_dir)["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION

    def test_fresh_install_seeds_credentials_from_config(self, data_dir):
        """First boot ever (no settings.json): the default board inherits the
        config.json credentials (which env vars may have seeded there)."""
        _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST)

        svc = _new_settings_service()

        first = svc.get_board_settings().boards[0]
        assert first["local_api_key"] == STALE_KEY
        assert first["host"] == STALE_HOST

    def test_env_cloud_key_flows_into_settings_on_first_boot(self, data_dir, monkeypatch):
        """CI-style env flow: BOARD_READ_WRITE_KEY seeds config.json via the
        ConfigManager, and the settings store picks it up on first boot."""
        monkeypatch.setenv("BOARD_READ_WRITE_KEY", "test_key")

        svc = _new_settings_service()

        first = svc.get_board_settings().boards[0]
        assert first["cloud_key"] == "test_key"

    def test_devices_era_settings_still_import_legacy_credentials(self, data_dir):
        """Devices-era fixture: a raw ``board`` dict with ``devices`` and NO
        ``boards`` list — a shape ``BoardSettings.from_dict`` still parses.

        This shape used to slip between the migration gate (which needed a
        raw ``boards[0]``) and the first-boot seed (which needs ``board``
        absent): schema stamped v3 with the credentials stranded in
        config.json forever — dark board, and no wizard to recover with. The
        migration must run the legacy import against the POST-PARSE board
        list (#1866 review).
        """
        from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION

        _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST)
        payload = {
            "schema_version": 2,
            "board": {"board_type": "black", "devices": ["flagship"]},
        }
        (data_dir / "settings.json").write_text(json.dumps(payload))

        svc = _new_settings_service()

        first = svc.get_board_settings().boards[0]
        assert first["local_api_key"] == STALE_KEY, "devices-era install stranded its credentials in config.json"
        assert first["host"] == STALE_HOST

        on_disk = _settings_on_disk(data_dir)
        assert on_disk["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION
        assert on_disk["board"]["boards"][0]["local_api_key"] == STALE_KEY

    def test_virtual_primary_is_never_clobbered_by_stale_credentials(self, data_dir):
        """A FiestaPanel primary (api_mode="virtual") carries no credential
        fields by nature — that is configured, not credential-less. The
        migration must not import stale physical credentials over it
        (flipping api_mode and creating a ghost client); mirror
        ``BoardInstance.has_connection_attempt``, which counts virtual as a
        connection attempt (#1866 review).
        """
        _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST, api_mode="local")
        _write_settings(data_dir, [_board(api_mode="virtual")], schema_version=2)

        svc = _new_settings_service()

        first = svc.get_board_settings().boards[0]
        assert first["api_mode"] == "virtual", "stale physical credentials flipped a virtual primary"
        assert first.get("local_api_key", "") == ""
        assert first.get("host", "") == ""

    def test_transient_config_read_failure_aborts_migration_for_retry(self, data_dir):
        """A transient failure reading config.json must not stamp the new
        schema version with nothing imported. The migration run aborts —
        schema_version stays pre-migration, nothing half-stamped — and the
        next (healthy) boot completes the import (#1866 review).
        """
        _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST)
        _write_settings(data_dir, [_board()], schema_version=2)

        with patch(
            "src.config_manager.get_config_manager",
            side_effect=RuntimeError("transient config read failure"),
        ):
            _new_settings_service()

        assert _settings_on_disk(data_dir)["schema_version"] == 2, (
            "migration stamped the new schema version despite the failed legacy read"
        )

        svc = _new_settings_service()
        assert svc.get_board_settings().boards[0]["local_api_key"] == STALE_KEY
        from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION

        assert _settings_on_disk(data_dir)["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION

    def test_token_only_install_does_not_seed_a_flagship_board(self, data_dir):
        """BOARD_NOTE_ARRAY_TOKEN-only fresh install: a note-array token can
        never drive the default flagship board. Seeding it anyway satisfied
        has_connection_attempt — wizard suppressed, no client possible.
        Nothing imports, so the wizard appears (pre-#1760 behavior)
        (#1866 review).
        """
        from src.devices import BoardInstance

        _write_config(data_dir, note_array_token="test_na_token")

        svc = _new_settings_service()

        first = svc.get_board_settings().boards[0]
        assert first.get("note_array_token", "") == "", "a note-array token was seeded onto a flagship board"
        assert not BoardInstance.from_dict(first).has_connection_attempt, (
            "token-only seed suppressed the setup wizard with no buildable client"
        )

    def test_token_still_imports_into_a_note_array_primary(self, data_dir):
        """The counterpart guard: when the primary IS a note array, the legacy
        token imports exactly as before."""
        _write_config(data_dir, note_array_token="test_na_token")
        _write_settings(data_dir, [_board(device_type="note_array")], schema_version=2)

        svc = _new_settings_service()

        assert svc.get_board_settings().boards[0]["note_array_token"] == "test_na_token"

    def test_migrated_credentials_drive_client_construction(self, data_dir):
        """Upgrade acceptance: after the migration, the board runtime is built
        from the migrated settings credentials (under the board's own id, not
        a legacy fallback slot)."""
        from src.main import DisplayService

        _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST)
        _write_settings(data_dir, [_board()], schema_version=2)

        service = DisplayService()
        service._build_board_clients(sync_cache=False)

        assert "b1" in service.runtimes
        client = service.runtimes["b1"].client
        assert client.api_key == STALE_KEY


# ── 2. divergence: every reader sees the settings copy ──────────────────────


@pytest.fixture
def diverged(data_dir) -> Path:
    """The #948 repro state: settings carries the live key A (user changed it
    in the UI), config.json still holds the stale key B."""
    from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION

    _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST)
    _write_settings(
        data_dir,
        [_board(local_api_key=LIVE_KEY, host=LIVE_HOST)],
        schema_version=CURRENT_SETTINGS_SCHEMA_VERSION,
    )
    return data_dir


class TestDivergedReadersSeeSettings:
    """With settings key A and stale config.json key B, every repointed
    reader must see A."""

    def test_welcome_message_uses_settings_credentials(self, diverged, client):
        with patch("src.board_client.BoardClient") as mock_bc:
            instance = MagicMock()
            instance.render.return_value = (True, True)
            mock_bc.return_value = instance
            response = client.post("/send-welcome-message")

        assert response.status_code == 200
        kwargs = mock_bc.call_args.kwargs
        assert kwargs["api_key"] == LIVE_KEY
        assert kwargs["host"] == LIVE_HOST

    def test_board_client_build_uses_settings_credentials(self, diverged):
        from src.main import DisplayService

        service = DisplayService()
        service._build_board_clients(sync_cache=False)

        assert "b1" in service.runtimes
        client = service.runtimes["b1"].client
        assert client.api_key == LIVE_KEY
        assert STALE_KEY not in {getattr(rt.client, "api_key", None) for rt in service.runtimes.values()}

    def test_get_config_board_returns_settings_view(self, diverged, client):
        response = client.get("/config/board")
        assert response.status_code == 200
        config = response.json()["config"]
        assert config["host"] == LIVE_HOST
        assert config["api_mode"] == "local"
        # Non-empty credential is masked, proving it is set (and came from
        # settings — the stale config.json copy has a different host).
        assert config["local_api_key"] == "***"

    def test_system_info_reports_settings_connection(self, diverged, client):
        response = client.get("/debug/system-info")
        assert response.status_code == 200
        data = response.json()
        assert data["board_ip"] == LIVE_HOST
        assert data["connection_mode"] == "local"

    def test_network_diagnostics_uses_settings_credentials(self, diverged, client):
        with patch("src.network_diagnostics.run_full_diagnostics", return_value={}) as diag:
            response = client.get("/debug/network-diagnostics")
        assert response.status_code == 200
        kwargs = diag.call_args.kwargs
        assert kwargs["board_host"] == LIVE_HOST
        assert kwargs["board_api_key"] == LIVE_KEY


class TestNoStaleConfigFallback:
    """A credential-less settings board must read as unconfigured — never
    silently served by the stale config.json copy."""

    def _cleared(self, data_dir):
        from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION

        _write_config(data_dir, local_api_key=STALE_KEY, host=STALE_HOST)
        _write_settings(data_dir, [_board()], schema_version=CURRENT_SETTINGS_SCHEMA_VERSION)

    def test_client_build_never_falls_back_to_stale_config(self, data_dir):
        """User cleared the credentials in Settings: no ghost client is built
        from whatever is left in config.json."""
        from src.main import DisplayService

        self._cleared(data_dir)
        service = DisplayService()
        with patch("src.main.BoardClient") as legacy_client:
            service._build_board_clients(sync_cache=False)

        legacy_client.assert_not_called()
        assert service.board_clients == {}

    def test_system_info_without_boards_never_reads_stale_config(self, client):
        """Even with no boards[] entries at all, the stale config.json values
        must not be reported as the live connection."""
        ss = Mock()
        board_settings = Mock()
        board_settings.boards = []
        ss.get_board_settings.return_value = board_settings
        ss.should_send_to_board.return_value = False
        with (
            patch("src.api_server.get_settings_service", return_value=ss),
            patch("src.api_server._get_board_client", return_value=None),
            patch("src.api_server.Config") as mock_config,
        ):
            mock_config.BOARD_API_MODE = "local"
            mock_config.BOARD_HOST = STALE_HOST
            mock_config.BOARD_LOCAL_API_KEY = STALE_KEY
            mock_config.BOARD_READ_WRITE_KEY = ""
            response = client.get("/debug/system-info")

        assert response.status_code == 200
        data = response.json()
        assert data["board_ip"] == ""
        assert data["board_configured"] is False


# ── 3. /config/board deprecation shim ───────────────────────────────────────


class TestConfigBoardShim:
    """GET/PUT /config/board keep their recorded wire shapes, carry the
    deprecation headers, and write through settings only."""

    # Recorded response shapes of the pre-#1760 endpoints (golden).
    GET_SHAPE = {"config", "api_modes"}
    CONFIG_KEYS = {
        "api_mode",
        "local_api_key",
        "cloud_key",
        "note_array_token",
        "host",
        "transition_strategy",
        "transition_interval_ms",
        "transition_step_size",
    }
    PUT_SHAPE = {"status", "config"}

    def test_get_config_board_shape_is_stable(self, diverged, client):
        response = client.get("/config/board")
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == self.GET_SHAPE
        assert data["api_modes"] == ["local", "cloud"]
        assert set(data["config"].keys()) == self.CONFIG_KEYS

    def test_put_config_board_shape_is_stable(self, diverged, client):
        response = client.put("/config/board", json={"api_mode": "local", "host": "192.0.2.50"})
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == self.PUT_SHAPE
        assert data["status"] == "success"
        assert set(data["config"].keys()) == self.CONFIG_KEYS

    def test_config_board_shim_sends_deprecation_headers(self, diverged, client):
        for response in (
            client.get("/config/board"),
            client.put("/config/board", json={"host": "192.0.2.50"}),
        ):
            assert response.headers.get("Deprecation") == "true"
            link = response.headers.get("Link", "")
            assert "/settings/board" in link
            assert 'rel="successor-version"' in link

    def test_put_config_board_writes_settings_not_config(self, diverged, client):
        # Warm the config manager first: its constructor normalizes
        # config.json (defaults merge / version snapshot) on first load,
        # which is unrelated to the PUT under test.
        assert client.get("/config/full").status_code == 200
        board_block_before = json.loads((diverged / "config.json").read_text())["board"]

        response = client.put(
            "/config/board",
            json={"api_mode": "local", "host": "192.0.2.50", "local_api_key": "test_new_key"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # The write landed in settings.json (visible through the settings API)…
        settings_view = client.get("/settings/board").json()
        assert settings_view["boards"][0]["host"] == "192.0.2.50"
        on_disk = _settings_on_disk(diverged)
        assert on_disk["board"]["boards"][0]["local_api_key"] == "test_new_key"
        assert on_disk["board"]["boards"][0]["host"] == "192.0.2.50"

        # …and the config.json board block was not touched: it keeps the
        # stale values as a vestigial rollback copy for older versions.
        board_block_after = json.loads((diverged / "config.json").read_text())["board"]
        assert board_block_after == board_block_before
        assert board_block_after["local_api_key"] == STALE_KEY
        assert board_block_after["host"] == STALE_HOST

    def test_put_config_board_preserves_masked_credentials(self, diverged, client):
        """A masked '***' credential in the PUT body keeps the stored value —
        the same contract the legacy config writer had."""
        response = client.put("/config/board", json={"host": "192.0.2.50", "local_api_key": "***"})
        assert response.status_code == 200
        on_disk = _settings_on_disk(diverged)
        assert on_disk["board"]["boards"][0]["local_api_key"] == LIVE_KEY


class TestFirstRunDetectionAfterUnification:
    """First-run must mean *never configured*, not *misconfigured* (#1760).

    Before the unification, ``configureBoard()``-style writes through
    ``PUT /config/board`` left credentials in config.json forever, so the
    wizard gate never re-armed. With settings as the single source, a board
    whose credentials are incomplete (e.g. a note array missing its token)
    must surface as a per-board error — not flip the install back into the
    setup wizard.
    """

    def test_incomplete_note_array_is_not_first_run(self, client):
        client.put(
            "/settings/board",
            json={
                "boards": [
                    {
                        "name": "My Board",
                        "device_type": "note_array",
                        "notes_wide": 4,
                        "notes_tall": 1,
                        "enabled": True,
                        "api_mode": "local",
                        "host": "localhost",
                        "local_api_key": "test-key",
                    }
                ]
            },
        )
        result = client.get("/config/validate").json()
        assert result["is_first_run"] is False

    def test_partial_host_only_board_is_not_first_run(self, client):
        client.put(
            "/settings/board",
            json={
                "boards": [{"name": "My Board", "device_type": "flagship", "api_mode": "local", "host": "192.0.2.9"}]
            },
        )
        result = client.get("/config/validate").json()
        assert result["is_first_run"] is False

    def test_truly_blank_board_still_first_run(self, client):
        client.put(
            "/settings/board",
            json={
                "boards": [
                    {
                        "name": "My Board",
                        "device_type": "flagship",
                        "api_mode": "local",
                        "host": "",
                        "local_api_key": "",
                    }
                ]
            },
        )
        result = client.get("/config/validate").json()
        assert result["is_first_run"] is True

    def test_wizard_reset_still_first_run(self, client):
        client.put("/config/board", json={"host": "192.0.2.9", "local_api_key": "test-key"})
        assert client.get("/config/validate").json()["is_first_run"] is False
        client.delete("/config/board")
        assert client.get("/config/validate").json()["is_first_run"] is True
