"""Value-level contract goldens for the /version + /system API (Phase 2 §2, slice 5).

These are deliberately *values*, not shapes. ``tests/golden/responses/system.json``
records key sets and type names, so it cannot see an error string that stopped
naming the sidecar, a hint that lost its ``docker compose`` command, or a 502
that quietly became a 500 — the class of regression Phase 1's masking bug
proved shape goldens miss.

Every assertion below is a promise this domain makes to the web client and to
anyone reading a failure toast.

WRITTEN AGAINST THE UNMODIFIED TRUNK FIRST. Every ``detail`` value in this
file was recorded from ``origin/next-rebuild`` before the conversion, so the
re-pinning below is a diff a reviewer can read rather than a rewrite.

Re-pinned by the conventions pass in this same PR. What deliberately changed,
and nothing else:

* **Every ``HTTPException`` detail is now a string** (22 of the domain's 24
  raise sites were dicts). ``docs/internal/reference/API_CONVENTIONS.md``
  §"Error contract" allows exactly one shape — ``{"detail": <string>}`` — and
  a dict only when it carries a ``message`` key plus named fields. None of
  these carried ``message``; they carried ad-hoc ``status`` / ``mode`` /
  ``error`` / ``hint`` keys that no client reads. ``web/src/lib/api/core.ts``
  already renders a non-string detail with ``JSON.stringify``, so before this
  change the user was shown a raw JSON blob in the error toast; afterwards
  they are shown the sentence.
  The **status codes are unchanged** on every one of those paths, and the
  human-readable sentence inside each old dict is preserved verbatim as the
  new detail (the two generic ``str(e)`` bodies gain the "fiestaupdater
  <action> call failed" prefix that was previously only in the log line).
* Nothing else. Every success body, every status code, the auto-update
  interval semantics, and the two paths that were already string details
  (``POST /system/update/auto``'s two 422s) are unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests as requests_lib
from fastapi.testclient import TestClient

# The module the system router resolves its collaborators through. Patching
# here — not through ``src.api_server`` — is the point of the seam retirement
# in this same PR.
UPDATE_SERVICE = "src.system.update_service"

_DIGEST = "sha256:" + "ab12" * 16
_IMAGE = "fiestaboard/fiestaboard:8.0.0"

_SNAPSHOT_DOC = {
    "fiestaboard_backup": True,
    "schema_version": 1,
    "app_version": "7.0.0",
    "data": {"config": {"plugins": {}}},
    "_fiestaupdater": {"previous_digest": _DIGEST, "previous_image": _IMAGE},
}


@pytest.fixture
def client(_isolated_data_dir):
    """A TestClient whose services all resolve into this test's temp data dir."""
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def sidecar_seams(tmp_path, monkeypatch):
    """Deterministic sidecar environment: no token, tmp state file + snapshot dir."""
    state_file = tmp_path / "state.json"
    snap_dir = tmp_path / "update-backups"
    monkeypatch.setattr(f"{UPDATE_SERVICE}.SYSTEM_UPDATE_STATE_FILE", state_file)
    monkeypatch.setattr(f"{UPDATE_SERVICE}.SETTINGS_SNAPSHOT_DIR", snap_dir)
    for var in ("FIESTAUPDATER_TOKEN", "SUPERVISOR_TOKEN", "FIESTABOARD_MANAGED_EXTERNALLY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("FIESTABOARD_PROFILE", "docker")
    return state_file, snap_dir


@pytest.fixture
def snapshot(sidecar_seams):
    """One well-formed snapshot on disk, annotated with a rollback target."""
    _, snap_dir = sidecar_seams
    snap_dir.mkdir(parents=True, exist_ok=True)
    path = snap_dir / "pre-update-20260101T000000.000Z.json"
    path.write_text(json.dumps(_SNAPSHOT_DOC), encoding="utf-8")
    return path


class _RestoreOk:
    """BackupService stand-in whose restore succeeds."""

    def import_from_json(self, raw: str, reinstall_plugins: bool = True) -> dict:
        return {
            "restored_files": ["settings.json"],
            "skipped_files": [],
            "pre_restore_backup_suffix": ".pre-restore-contract",
            "reload_errors": [],
        }


def _raiser(exc):
    def _boom(*_args, **_kwargs):
        raise exc

    return _boom


# ===========================================================================
# GET /version
# ===========================================================================


def test_version_reports_the_package_version_and_a_dev_build(client, monkeypatch):
    from src import __version__

    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("PRODUCTION", raising=False)
    with patch(f"{UPDATE_SERVICE}._detect_hardware_model", return_value="Raspberry Pi 5 Model B Rev 1.0"):
        response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {
        "package_version": __version__,
        "build_version": "dev",
        "is_dev": True,
        "hardware_model": "Raspberry Pi 5 Model B Rev 1.0",
    }


def test_version_is_not_dev_when_a_production_build_is_tagged(client, monkeypatch):
    monkeypatch.setenv("VERSION", "8.34.15")
    monkeypatch.setenv("PRODUCTION", "true")
    with patch(f"{UPDATE_SERVICE}._detect_hardware_model", return_value=None):
        body = client.get("/version").json()
    assert body["build_version"] == "8.34.15"
    assert body["is_dev"] is False
    assert body["hardware_model"] is None


# ===========================================================================
# GET /system/update-check — a probe endpoint: the verdict is the payload
# ===========================================================================


def test_update_check_reports_the_newest_version_either_source_lists(client, monkeypatch):
    from urllib.parse import urlparse

    def _get(url, **_kwargs):
        resp = Mock(status_code=200)
        resp.raise_for_status = Mock()
        if urlparse(url).netloc == "hub.docker.com":
            resp.json.return_value = {"results": [{"name": "99.0.0"}, {"name": "latest"}]}
        else:
            resp.json.return_value = {"tag_name": "v98.0.0"}
        return resp

    with patch(f"{UPDATE_SERVICE}.requests.get", side_effect=_get):
        body = client.get("/system/update-check").json()
    assert body["latest_version"] == "99.0.0"
    assert body["update_available"] is True
    assert body["error"] is None
    assert body["package_url"] == "https://github.com/Fiestaboard/FiestaBoard/releases/tag/v99.0.0"


def test_update_check_answers_200_with_an_error_field_when_both_sources_are_down(client):
    """A probe endpoint reports the verdict about *something else* at 200.

    API_CONVENTIONS.md §"Status codes" allows this exactly because the body is
    a declared response_model with a named error field, so a generic client can
    still tell "checked, and it failed" from "checked, and you are current".
    """
    with patch(f"{UPDATE_SERVICE}.requests.get", side_effect=Exception("network down")):
        response = client.get("/system/update-check")
    assert response.status_code == 200
    body = response.json()
    assert body["latest_version"] is None
    assert body["update_available"] is False
    assert body["error"] == "Could not check for updates: Both Docker Hub and GitHub Releases checks failed"


# ===========================================================================
# GET /system/update/status
# ===========================================================================


def test_update_status_without_a_token_reports_the_sidecar_unavailable(client, sidecar_seams):
    response = client.get("/system/update/status")
    assert response.status_code == 200
    body = response.json()
    assert body["updater_available"] is False
    # No stored preference: the docker profile's default interval, not "off".
    assert body["auto_update_enabled"] is True
    assert body["auto_update_interval"] == "weekly"
    assert body["managed_externally"] is False
    assert body["profile"] == "docker"
    assert body["settings_snapshots"] == []
    assert body["post_upgrade_regression"] is None
    # The sidecar was never probed, so none of its bookkeeping is invented.
    assert body["last_update_status"] is None
    assert body["last_update_action"] is None


# ===========================================================================
# POST /system/update
# ===========================================================================


def test_update_without_a_token_is_503_and_names_the_compose_profile(client, sidecar_seams):
    response = client.post("/system/update")
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "FIESTAUPDATER_TOKEN is not set. Add COMPOSE_PROFILES=fiestaupdater to your .env "
        "and run 'docker compose up -d' to enable in-app updates."
    )


def test_update_with_an_unreachable_sidecar_is_503_with_manual_instructions(client, sidecar_seams, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(
        f"{UPDATE_SERVICE}.requests.post",
        side_effect=requests_lib.exceptions.ConnectionError("nope"),
    ):
        response = client.post("/system/update")
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Could not reach the fiestaupdater sidecar. Run 'docker compose pull && docker compose up -d' "
        "from your install directory to update manually."
    )


def test_update_with_an_unexpected_transport_error_is_502(client, sidecar_seams, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", side_effect=ValueError("bad url")):
        response = client.post("/system/update")
    assert response.status_code == 502
    assert response.json()["detail"] == "fiestaupdater update call failed: bad url"


def test_update_rejected_token_is_500_and_says_which_variable_to_check(client, sidecar_seams, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", return_value=Mock(status_code=401, text="invalid_token")):
        response = client.post("/system/update")
    assert response.status_code == 500
    assert response.json()["detail"] == (
        "fiestaupdater rejected our token; check FIESTAUPDATER_TOKEN matches in both services"
    )


def test_update_sidecar_error_is_502_and_quotes_the_sidecar(client, sidecar_seams, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", return_value=Mock(status_code=500, text="pull failed")):
        response = client.post("/system/update")
    assert response.status_code == 502
    assert response.json()["detail"] == "fiestaupdater returned 500: pull failed"


def test_update_happy_path_queues_and_reports_the_snapshot_it_took(client, sidecar_seams, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    accepted = Mock(status_code=202)
    accepted.json.return_value = {"previous_digest": _DIGEST}
    with (
        patch(f"{UPDATE_SERVICE}.requests.post", return_value=accepted),
        patch(f"{UPDATE_SERVICE}._updater_version", return_value={"digest": _DIGEST, "image": _IMAGE}),
    ):
        response = client.post("/system/update")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["mode"] == "sidecar"
    assert body["previous_digest"] == _DIGEST
    assert body["settings_snapshot"]["previous_digest"] == _DIGEST
    assert body["settings_snapshot"]["previous_image"] == _IMAGE


# ===========================================================================
# POST /system/update/rollback
# ===========================================================================


def test_rollback_with_both_flags_false_is_400(client, sidecar_seams):
    response = client.post(
        "/system/update/rollback",
        json={"restore_settings": False, "restore_image": False},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "At least one of restore_settings, restore_image must be true."


def test_rollback_with_no_snapshot_on_disk_is_404(client, sidecar_seams):
    response = client.post("/system/update/rollback", json={})
    assert response.status_code == 404
    assert response.json()["detail"] == "No matching settings snapshot was found."


def test_rollback_with_an_unreadable_snapshot_is_400(client, snapshot, monkeypatch):
    monkeypatch.setattr(Path, "read_text", _raiser(OSError("disk on fire")))
    response = client.post("/system/update/rollback", json={"restore_image": False})
    assert response.status_code == 400
    assert response.json()["detail"] == "Could not read snapshot: disk on fire"


def test_rollback_with_a_bad_snapshot_document_is_400(client, snapshot, monkeypatch):
    from src.backup.service import BackupError

    service = Mock()
    service.import_from_json.side_effect = BackupError("Not a FiestaBoard backup file")
    monkeypatch.setattr("src.backup.service.get_backup_service", lambda: service)
    response = client.post("/system/update/rollback", json={"restore_image": False})
    assert response.status_code == 400
    assert response.json()["detail"] == "Not a FiestaBoard backup file"


def test_rollback_aborted_by_the_environment_is_500(client, snapshot, monkeypatch):
    """An unwritable data dir is our failure, not a bad snapshot (Task 10d)."""
    from src.backup.service import BackupRestoreAborted

    service = Mock()
    service.import_from_json.side_effect = BackupRestoreAborted("could not copy settings.json aside")
    monkeypatch.setattr("src.backup.service.get_backup_service", lambda: service)
    response = client.post("/system/update/rollback", json={"restore_image": False})
    assert response.status_code == 500
    assert response.json()["detail"] == "could not copy settings.json aside"


def test_rollback_settings_only_reports_what_it_restored(client, snapshot, monkeypatch):
    monkeypatch.setattr("src.backup.service.get_backup_service", _RestoreOk)
    response = client.post("/system/update/rollback", json={"restore_image": False})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["snapshot"] == snapshot.name
    assert body["warnings"] == []
    assert body["image_rollback"] is None
    assert body["settings_rollback"] == {
        "restored_from": snapshot.name,
        "restored_files": ["settings.json"],
        "skipped_files": [],
        "pre_restore_backup_suffix": ".pre-restore-contract",
        "reload_errors": [],
    }


def test_rollback_without_a_token_is_partial_and_says_the_image_was_left_alone(client, snapshot, monkeypatch):
    monkeypatch.setattr("src.backup.service.get_backup_service", _RestoreOk)
    response = client.post("/system/update/rollback", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert body["image_rollback"] is None
    assert body["warnings"] == [
        "FIESTAUPDATER_TOKEN is not set; image rollback is unavailable. "
        "Settings have been restored but the image is unchanged."
    ]


def test_rollback_of_an_unannotated_snapshot_is_partial(client, sidecar_seams, monkeypatch):
    _, snap_dir = sidecar_seams
    snap_dir.mkdir(parents=True, exist_ok=True)
    doc = {k: v for k, v in _SNAPSHOT_DOC.items() if k != "_fiestaupdater"}
    (snap_dir / "pre-update-20260101T000000.000Z.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr("src.backup.service.get_backup_service", _RestoreOk)
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    body = client.post("/system/update/rollback", json={}).json()
    assert body["status"] == "partial"
    assert body["warnings"] == ["Snapshot does not record a previous image digest; image was not rolled back."]


def test_rollback_image_with_an_unreachable_sidecar_is_503(client, snapshot, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(
        f"{UPDATE_SERVICE}.requests.post",
        side_effect=requests_lib.exceptions.ConnectionError("nope"),
    ):
        response = client.post("/system/update/rollback", json={"restore_settings": False})
    assert response.status_code == 503
    assert response.json()["detail"] == "Could not reach the fiestaupdater sidecar; image rollback unavailable."


def test_rollback_image_with_an_unexpected_transport_error_is_502(client, snapshot, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", side_effect=ValueError("bad url")):
        response = client.post("/system/update/rollback", json={"restore_settings": False})
    assert response.status_code == 502
    assert response.json()["detail"] == "fiestaupdater rollback call failed: bad url"


def test_rollback_image_rejected_token_is_500(client, snapshot, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", return_value=Mock(status_code=401, text="invalid_token")):
        response = client.post("/system/update/rollback", json={"restore_settings": False})
    assert response.status_code == 500
    assert response.json()["detail"] == "fiestaupdater rejected our token"


def test_rollback_image_sidecar_error_is_502_and_quotes_the_sidecar(client, snapshot, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", return_value=Mock(status_code=500, text="retag failed")):
        response = client.post("/system/update/rollback", json={"restore_settings": False})
    assert response.status_code == 502
    assert response.json()["detail"] == "fiestaupdater returned 500: retag failed"


def test_rollback_image_happy_path_queues_the_recorded_digest(client, snapshot, monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", return_value=Mock(status_code=202, text="")):
        response = client.post("/system/update/rollback", json={"restore_settings": False})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["settings_rollback"] is None
    assert body["image_rollback"] == {
        "target_digest": _DIGEST,
        "target_image": _IMAGE,
        "queued": True,
    }


# ===========================================================================
# POST /system/update/auto — the two paths that were already string details
# ===========================================================================


def test_auto_update_interval_is_persisted_and_echoed(client, sidecar_seams):
    state_file, _ = sidecar_seams
    response = client.post("/system/update/auto", json={"interval": "weekly"})
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "interval": "weekly"}
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted["auto_update_interval"] == "weekly"
    assert persisted["auto_update_enabled"] is True


def test_auto_update_legacy_false_maps_to_manual(client, sidecar_seams):
    assert client.post("/system/update/auto", json={"enabled": False}).json() == {
        "enabled": False,
        "interval": "manual",
    }


def test_auto_update_rejects_an_unknown_interval_with_422(client, sidecar_seams):
    response = client.post("/system/update/auto", json={"interval": "hourly"})
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Invalid interval 'hourly'; must be one of: ['daily', 'manual', 'monthly', 'weekly']"
    )


def test_auto_update_rejects_an_empty_body_with_422(client, sidecar_seams):
    response = client.post("/system/update/auto", json={})
    assert response.status_code == 422
    assert response.json()["detail"] == "Request must include either 'interval' or 'enabled'."


# ===========================================================================
# POST /system/restart and POST /system/shutdown
# ===========================================================================


@pytest.mark.parametrize("action", ["restart", "shutdown"])
def test_system_action_without_a_token_is_503_and_names_the_compose_profile(client, sidecar_seams, action):
    response = client.post(f"/system/{action}")
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "FIESTAUPDATER_TOKEN is not set. Add COMPOSE_PROFILES=fiestaupdater to your .env "
        "and run 'docker compose up -d' to enable sidecar features."
    )


@pytest.mark.parametrize("action", ["restart", "shutdown"])
def test_system_action_with_an_unreachable_sidecar_is_503(client, sidecar_seams, monkeypatch, action):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(
        f"{UPDATE_SERVICE}.requests.post",
        side_effect=requests_lib.exceptions.ConnectionError("nope"),
    ):
        response = client.post(f"/system/{action}")
    assert response.status_code == 503
    assert response.json()["detail"] == "Could not reach the fiestaupdater sidecar."


@pytest.mark.parametrize("action", ["restart", "shutdown"])
def test_system_action_with_an_unexpected_transport_error_is_502(client, sidecar_seams, monkeypatch, action):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", side_effect=ValueError("bad url")):
        response = client.post(f"/system/{action}")
    assert response.status_code == 502
    assert response.json()["detail"] == f"fiestaupdater {action} call failed: bad url"


@pytest.mark.parametrize("action", ["restart", "shutdown"])
def test_system_action_rejected_token_is_500(client, sidecar_seams, monkeypatch, action):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", return_value=Mock(status_code=401, text="invalid_token")):
        response = client.post(f"/system/{action}")
    assert response.status_code == 500
    assert response.json()["detail"] == (
        "fiestaupdater rejected our token; check FIESTAUPDATER_TOKEN matches in both services"
    )


@pytest.mark.parametrize("action", ["restart", "shutdown"])
def test_system_action_sidecar_error_is_502_and_quotes_the_sidecar(client, sidecar_seams, monkeypatch, action):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", return_value=Mock(status_code=503, text="busy")):
        response = client.post(f"/system/{action}")
    assert response.status_code == 502
    assert response.json()["detail"] == "fiestaupdater returned 503: busy"


@pytest.mark.parametrize("action", ["restart", "shutdown"])
def test_system_action_happy_path_queues(client, sidecar_seams, monkeypatch, action):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "tok")
    with patch(f"{UPDATE_SERVICE}.requests.post", return_value=Mock(status_code=202, text="")):
        response = client.post(f"/system/{action}")
    assert response.status_code == 200
    assert response.json() == {"status": "queued", "action": action}
