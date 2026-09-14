"""Leaving the beta before the release catches up (#1955 follow-on).

There are two ways off a beta, and they are not equally safe.

The ordinary one is to wait: once ``9.0.0`` ships it outranks every
``9.0.0-beta.N``, Update Now installs it, and the box reports stable from
then on. Same data generation, no risk. That is the graduation path.

This file is the other one — the escape hatch. Leaving *before* the release
catches up means ``9.0.0-beta.12 -> 8.37.5``: a downgrade across a major,
onto a build that will refuse to read data the beta migrated (#1961). Done
naively the user swaps "stuck on beta" for "stable that will not start".

So leaving restores the snapshot taken when they joined, *before* the image
flips — the same ordering ``rollback()`` already uses, and for the same
reason: the older container has to boot onto configuration it understands.

Which makes the join snapshot load-bearing. ``SETTINGS_SNAPSHOT_RETENTION``
is 5 and prunes by mtime, so weeks of beta updates would quietly delete the
one snapshot that is the way back. It is exempted.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import src.system.update_service as update_service


@pytest.fixture
def sidecar(monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv("FIESTABOARD_MANAGED_EXTERNALLY", raising=False)

    posted: list[tuple[str, dict]] = []

    def fake_post(path, json=None, **_):
        posted.append((path, json or {}))
        return MagicMock(status_code=202, text="{}")

    with (
        patch("src.system.update_service._updater_probe", return_value=True),
        patch(
            "src.system.update_service._updater_version",
            return_value={"image": "fiestaboard/fiestaboard:latest", "digest": "sha256:abc"},
        ),
        patch("src.system.update_service._updater_post", side_effect=fake_post),
    ):
        yield posted


@pytest.fixture
def snapshot_dir(tmp_path, monkeypatch):
    d = tmp_path / "update-backups"
    d.mkdir(parents=True)
    monkeypatch.setattr(update_service, "_settings_snapshot_dir", lambda: d)
    return d


def _join_snapshot(snapshot_dir, name="pre-update-20260101T000000.000Z.json"):
    (snapshot_dir / name).write_text(json.dumps({"settings": {"from": "stable"}}))
    return name


class TestJoiningRecordsTheWayBack:
    def test_the_join_snapshot_is_remembered(self, sidecar, snapshot_dir, monkeypatch):
        monkeypatch.setenv("VERSION", "8.37.5")
        with patch(
            "src.system.update_service._take_settings_snapshot",
            return_value={"name": "pre-update-x.json"},
        ):
            update_service.switch_channel("beta")
        state = update_service._system_update_state_load()
        assert state.get("channel_join_snapshot") == "pre-update-x.json", (
            "nothing recorded which snapshot is the way back out of the beta"
        )

    def test_a_refused_join_records_nothing(self, sidecar, snapshot_dir, monkeypatch):
        """Same rule as the channel itself: a wish is not a choice."""
        monkeypatch.setenv("VERSION", "8.37.5")
        state = update_service._system_update_state_load()
        state.pop("channel_join_snapshot", None)
        update_service._system_update_state_save(state)

        with (
            patch("src.system.update_service._updater_post", return_value=MagicMock(status_code=401, text="no")),
            patch("src.system.update_service._take_settings_snapshot", return_value={"name": "x.json"}),
            pytest.raises(update_service.SidecarError),
        ):
            update_service.switch_channel("beta")
        assert update_service._system_update_state_load().get("channel_join_snapshot") is None


class TestLeavingRestoresBeforeFlipping:
    @pytest.mark.asyncio
    async def test_settings_are_restored_before_the_image_changes(self, sidecar, snapshot_dir, monkeypatch):
        """The whole point. A stable build must boot onto readable config."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        name = _join_snapshot(snapshot_dir)
        update_service._system_update_state_update(channel="beta", channel_join_snapshot=name)

        order: list[str] = []

        async def restore(path):
            order.append("restore")
            return {"restored": True}

        def post(p, json=None, **_):
            order.append("install")
            return MagicMock(status_code=202, text="{}")

        with (
            patch("src.system.update_service._restore_settings_from_snapshot", side_effect=restore),
            patch("src.system.update_service._updater_post", side_effect=post),
            patch("src.system.update_service._take_settings_snapshot", return_value=None),
        ):
            await update_service.leave_beta()

        assert order == ["restore", "install"], (
            f"got {order}; an image flip before the restore drops an 8.x build "
            "onto 9.x data, which it refuses to read (#1961)"
        )

    @pytest.mark.asyncio
    async def test_it_installs_the_stable_tag(self, sidecar, snapshot_dir, monkeypatch):
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        name = _join_snapshot(snapshot_dir)
        update_service._system_update_state_update(channel="beta", channel_join_snapshot=name)

        with (
            patch("src.system.update_service._restore_settings_from_snapshot", return_value={"restored": True}),
            patch("src.system.update_service._take_settings_snapshot", return_value=None),
        ):
            await update_service.leave_beta()

        path, payload = sidecar[-1]
        assert path.lstrip("/") == "install"
        assert payload["tag"] == "latest"

    @pytest.mark.asyncio
    async def test_the_channel_is_recorded_as_stable(self, sidecar, snapshot_dir, monkeypatch):
        """Or the boot re-assert would drag them straight back to beta."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        name = _join_snapshot(snapshot_dir)
        update_service._system_update_state_update(channel="beta", channel_join_snapshot=name)

        with (
            patch("src.system.update_service._restore_settings_from_snapshot", return_value={"restored": True}),
            patch("src.system.update_service._take_settings_snapshot", return_value=None),
        ):
            await update_service.leave_beta()

        assert update_service._system_update_state_load().get("channel") == "stable"


class TestWhenThereIsNoWayBackRecorded:
    @pytest.mark.asyncio
    async def test_it_still_leaves_but_says_the_restore_was_skipped(self, sidecar, snapshot_dir, monkeypatch):
        """Refusing outright would strand the user on a beta they want off.

        Someone who joined before the join snapshot was recorded, or whose
        snapshot failed, still gets to leave — they are told the settings
        restore did not happen so they can restore a backup by hand.
        """
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        state = update_service._system_update_state_load()
        state.pop("channel_join_snapshot", None)
        state["channel"] = "beta"
        update_service._system_update_state_save(state)

        with patch("src.system.update_service._take_settings_snapshot", return_value=None):
            result = await update_service.leave_beta()

        assert sidecar, "refused to leave the beta at all"
        assert result["settings_restored"] is False
        assert result.get("warning")

    @pytest.mark.asyncio
    async def test_a_recorded_snapshot_that_is_gone_is_handled(self, sidecar, snapshot_dir, monkeypatch):
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        update_service._system_update_state_update(channel="beta", channel_join_snapshot="vanished.json")
        with patch("src.system.update_service._take_settings_snapshot", return_value=None):
            result = await update_service.leave_beta()
        assert result["settings_restored"] is False
        assert sidecar


class TestTheJoinSnapshotSurvivesPruning:
    def test_it_is_not_pruned_by_ordinary_churn(self, snapshot_dir, monkeypatch):
        """Weeks of beta updates must not delete the only way back."""
        name = _join_snapshot(snapshot_dir, "pre-update-20200101T000000.000Z.json")  # oldest by name
        update_service._system_update_state_update(channel="beta", channel_join_snapshot=name)

        for i in range(update_service.SETTINGS_SNAPSHOT_RETENTION + 5):
            (snapshot_dir / f"pre-update-20270101T0000{i:02d}.000Z.json").write_text(json.dumps({"settings": {}}))

        update_service._prune_settings_snapshots()

        assert (snapshot_dir / name).exists(), (
            "the join snapshot was pruned; retention keeps the 5 newest by mtime "
            "and this one is the oldest, so it goes first — taking the only way "
            "back off the beta with it"
        )

    def test_ordinary_snapshots_are_still_pruned(self, snapshot_dir, monkeypatch):
        """The exemption must not turn pruning off."""
        name = _join_snapshot(snapshot_dir, "pre-update-20200101T000000.000Z.json")
        update_service._system_update_state_update(channel="beta", channel_join_snapshot=name)

        for i in range(update_service.SETTINGS_SNAPSHOT_RETENTION + 5):
            (snapshot_dir / f"pre-update-20270101T0000{i:02d}.000Z.json").write_text(json.dumps({"settings": {}}))

        update_service._prune_settings_snapshots()

        others = [p for p in snapshot_dir.glob("*.json") if p.name != name]
        assert len(others) <= update_service.SETTINGS_SNAPSHOT_RETENTION, (
            f"{len(others)} ordinary snapshots survived; pruning stopped working"
        )
