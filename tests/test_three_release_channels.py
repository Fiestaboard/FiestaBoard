"""Three-channel discovery and fail-closed major-preview transitions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.system import update_service as us


def response(payload):
    result = MagicMock(status_code=200)
    result.json.return_value = payload
    return result


@pytest.mark.parametrize(
    "channel,expected", [("stable", "10.3.3"), ("beta", "10.4.0-beta.2"), ("alpha", "11.0.0-alpha.12")]
)
def test_docker_discovery_keeps_preview_lanes_isolated(channel, expected):
    tags = [
        "10.3.3",
        "10.4.0-beta.2",
        "11.0.0-alpha.99",
        "11.1.0-beta.1",
        "v11-alpha-11.0.0-alpha.9",
        "v11-alpha-11.0.0-alpha.12",
    ]
    with patch.object(us.requests, "get", return_value=response({"results": [{"name": tag} for tag in tags]})):
        assert us._check_dockerhub_for_latest(channel) == expected


def test_beta_github_discovery_cannot_offer_v11():
    releases = [{"tag_name": "v11.0.0-alpha.9"}, {"tag_name": "v11.1.0-beta.1"}, {"tag_name": "v10.4.0-beta.2"}]
    with patch.object(us.requests, "get", return_value=response(releases)):
        assert us._check_github_releases_for_latest("beta") == "10.4.0-beta.2"


def test_alpha_uses_only_published_lane_docker_tags():
    with patch.object(us.requests, "get") as get:
        assert us._check_github_releases_for_latest("alpha") is None
    get.assert_not_called()


def test_running_alpha_channel(monkeypatch):
    monkeypatch.setenv("VERSION", "11.0.0-alpha.3")
    assert us.current_channel() == "alpha"
    assert us.CHANNEL_TAGS["alpha"] == "v11-alpha"


def test_channel_endpoint_reports_versions_and_running_channel():
    versions = {"stable": "10.3.3", "beta": "10.4.0-beta.2", "alpha": "11.0.0-alpha.12"}

    async def latest(channel):
        return versions[channel]

    with (
        patch.object(us, "channel_switch_blocker", return_value=None),
        patch.object(us, "current_channel", return_value="beta"),
        patch.object(us, "_latest_for_channel", side_effect=latest),
    ):
        body = TestClient(app).get("/system/channel").json()
    assert body["channel_versions"] == versions
    assert body["running_channel"] == "beta"


@pytest.mark.parametrize(
    "confirmed,snapshot,expected",
    [(False, {"name": "saved.json"}, 409), (True, None, 503), (True, {"name": "saved.json"}, 200)],
)
def test_alpha_major_upgrade_requires_confirmation_and_backup(monkeypatch, confirmed, snapshot, expected):
    monkeypatch.setenv("VERSION", "10.3.3")
    with (
        patch.object(us, "channel_switch_blocker", return_value=None),
        patch.object(us, "_latest_for_channel", new=AsyncMock(return_value="11.0.0-alpha.12")),
        patch.object(us, "_updater_version", return_value={"image": "fiestaboard/fiestaboard:latest"}),
        patch.object(us, "_take_settings_snapshot", return_value=snapshot) as backup,
        patch.object(us, "_updater_post", return_value=MagicMock(status_code=202)) as install,
        patch.object(us, "_system_update_state_update") as save,
    ):
        result = TestClient(app).post("/system/channel", json={"channel": "alpha", "confirm_major_upgrade": confirmed})
    assert result.status_code == expected, result.text
    if expected != 200:
        install.assert_not_called()
        save.assert_not_called()
    else:
        backup.assert_called_once()
        assert install.call_args.args[1]["tag"] == "v11-alpha"


def test_backup_exception_fails_closed(monkeypatch):
    monkeypatch.setenv("VERSION", "10.3.3")
    with (
        patch.object(us, "_updater_version", return_value={"image": "fiestaboard/fiestaboard:latest"}),
        patch.object(us, "_take_settings_snapshot", side_effect=OSError("disk full")),
        patch.object(us, "_updater_post") as install,
    ):
        with pytest.raises(us.SidecarError):
            us.switch_channel("alpha", confirm_major_upgrade=True)
    install.assert_not_called()


def test_alpha_entry_preserves_original_stable_recovery(monkeypatch):
    monkeypatch.setenv("VERSION", "10.4.0-beta.2")
    us._system_update_state_update(channel_join_snapshot="stable.json")
    with (
        patch.object(us, "_updater_version", return_value={"image": "fiestaboard/fiestaboard:beta"}),
        patch.object(us, "_take_settings_snapshot", return_value={"name": "beta.json"}),
        patch.object(us, "_updater_post", return_value=MagicMock(status_code=202)),
    ):
        us.switch_channel("alpha", confirm_major_upgrade=True)
    state = us._system_update_state_load()
    assert state["channel_join_snapshot"] == "stable.json"
    assert state["alpha_join_snapshot"] == "beta.json"


@pytest.mark.asyncio
@pytest.mark.parametrize("target,snapshot,tag", [("beta", "beta.json", "beta"), ("stable", "stable.json", "latest")])
async def test_alpha_leave_restores_destination_snapshot_first(monkeypatch, tmp_path, target, snapshot, tag):
    monkeypatch.setenv("VERSION", "11.0.0-alpha.3")
    us._system_update_state_update(channel_join_snapshot="stable.json", alpha_join_snapshot="beta.json")
    order = []

    async def restore(path):
        order.append(("restore", path.name))

    def install(path, payload):
        order.append(("install", payload["tag"]))
        return MagicMock(status_code=202)

    with (
        patch.object(us, "channel_switch_blocker", return_value=None),
        patch.object(us, "_updater_version", return_value={"image": "fiestaboard/fiestaboard:v11-alpha"}),
        patch.object(us, "_resolve_snapshot_name", side_effect=lambda name: tmp_path / name),
        patch.object(us, "_restore_settings_from_snapshot", side_effect=restore),
        patch.object(us, "_updater_post", side_effect=install),
        patch("src.auth.service.get_auth_service"),
    ):
        result = await us.leave_beta(target)
    assert order == [("restore", snapshot), ("install", tag)]
    assert result["channel"] == target
    assert result["settings_restored"] is True


def test_alpha_reassert_uses_confirmed_intent_and_preserves_recovery(monkeypatch):
    monkeypatch.setenv("VERSION", "10.3.3")
    us._system_update_state_update(
        channel="alpha", channel_join_snapshot="stable.json", alpha_join_snapshot="beta.json"
    )
    with (
        patch.object(us, "channel_switch_blocker", return_value=None),
        patch.object(us, "_updater_version", return_value={"image": "fiestaboard/fiestaboard:latest"}),
        patch.object(us, "_take_settings_snapshot", return_value={"name": "reboot.json"}),
        patch.object(us, "_updater_post", return_value=MagicMock(status_code=202)) as install,
    ):
        us.reassert_release_channel()
    assert install.call_args.args[1]["tag"] == "v11-alpha"
    state = us._system_update_state_load()
    assert state["channel_join_snapshot"] == "stable.json"
    assert state["alpha_join_snapshot"] == "beta.json"


@pytest.mark.parametrize("failure", ["invalid_json", "unreadable", "null"])
def test_major_upgrade_rejects_real_incomplete_backup(monkeypatch, tmp_path, failure):
    from pathlib import Path
    from src.backup.service import BackupService

    monkeypatch.setenv("VERSION", "10.3.3")
    path = tmp_path / "settings.json"
    path.write_text("not json" if failure == "invalid_json" else "null" if failure == "null" else "{}")
    service = BackupService(tmp_path)
    original = Path.open

    def read(current, *args, **kwargs):
        if failure == "unreadable" and current == path:
            raise PermissionError("cannot read settings")
        return original(current, *args, **kwargs)

    with (
        patch.object(us, "_updater_version", return_value={"image": "fiestaboard/fiestaboard:latest"}),
        patch("src.backup.service.get_backup_service", return_value=service),
        patch.object(Path, "open", read),
        patch.object(us, "_updater_post", return_value=MagicMock(status_code=202)) as install,
        patch.object(us, "_system_update_state_update") as save,
    ):
        with pytest.raises(us.SidecarError, match="backup failed"):
            us.switch_channel("alpha", confirm_major_upgrade=True)
    install.assert_not_called()
    save.assert_not_called()


def test_boot_retention_preserves_channel_recovery_snapshots(tmp_path):
    import json

    snapshots = tmp_path / "update-backups"
    snapshots.mkdir()
    names = [f"pre-update-202601{i:02d}T000000.000Z.json" for i in range(1, 10)]
    for name in names:
        (snapshots / name).write_text("{}")
    (tmp_path / ".system-update.json").write_text(
        json.dumps({"channel_join_snapshot": names[0], "alpha_join_snapshot": names[1]})
    )
    deleted = us.prune_snapshot_dir(snapshots)
    assert deleted == 2
    assert {p.name for p in snapshots.iterdir()} == set(names[:2] + names[-5:])
