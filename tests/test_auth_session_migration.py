"""Versioned cookies fail closed on both sides of a beta downgrade."""

import json

import pytest

from src.auth.service import AuthService, SessionToken


def test_legacy_cookie_rejected_and_cutoff_advanced_once(tmp_path):
    path = tmp_path / "auth.json"
    service = AuthService(path)
    service.create_initial_user("admin", "correct-password")
    old_cutoff = service.get_user("admin")["sessions_valid_after_ms"]
    data = json.loads(path.read_text())
    data.pop("session_registry_version", None)
    path.write_text(json.dumps(data))
    legacy_payload = SessionToken("admin", old_cutoff, old_cutoff + 86400000).encode().removeprefix("v2.")
    legacy = service._sign(legacy_payload)
    migrated = AuthService(path)
    assert migrated.verify_session(legacy) is None
    assert migrated.get_user("admin")["sessions_valid_after_ms"] > old_cutoff
    token = migrated.authenticate("admin", "correct-password")
    assert token.startswith("v2.")
    # Legacy verifier expects exactly four signed payload components.
    assert len(token.rsplit(".", 1)[0].split(".")) != 4
    restarted = AuthService(path)
    assert restarted.verify_session(token) == "admin"
    assert (
        restarted.get_user("admin")["sessions_valid_after_ms"] == migrated.get_user("admin")["sessions_valid_after_ms"]
    )


async def _exercise_leave_beta(tmp_path, monkeypatch, fail_save=False):
    from types import SimpleNamespace

    from src.auth import service as auth_module
    from src.system import update_service

    svc = AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", "correct-password")
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setattr(update_service, "channel_switch_blocker", lambda: None)
    monkeypatch.setattr(update_service, "_updater_version", lambda: {"image": "fiestaboard/fiestaboard:beta"})
    monkeypatch.setattr(update_service, "_channel_join_snapshot_name", lambda: None)
    posted = []
    token = svc.authenticate("admin", "correct-password")
    before = svc.get_user("admin")["sessions_valid_after_ms"]

    def post(*args, **kwargs):
        posted.append(args)
        assert svc.verify_session(token) is None
        assert svc.get_user("admin")["sessions_valid_after_ms"] > before
        return SimpleNamespace(status_code=202)

    monkeypatch.setattr(update_service, "_updater_post", post)
    if fail_save:

        def fail():
            raise OSError("disk full")

        monkeypatch.setattr(svc, "_save", fail)
        import pytest

        with pytest.raises(OSError):
            await update_service.leave_beta()
        assert posted == []
    else:
        await update_service.leave_beta()
        assert len(posted) == 1
        token = svc.authenticate("admin", "correct-password")
        before = svc.get_user("admin")["sessions_valid_after_ms"]
        await update_service.leave_beta()
        assert len(posted) == 2


@pytest.mark.asyncio
async def test_managed_downgrade_invalidates_even_after_repeated_cycles(tmp_path, monkeypatch):
    await _exercise_leave_beta(tmp_path, monkeypatch)


@pytest.mark.asyncio
async def test_failed_cutoff_write_prevents_downgrade(tmp_path, monkeypatch):
    await _exercise_leave_beta(tmp_path, monkeypatch, fail_save=True)
