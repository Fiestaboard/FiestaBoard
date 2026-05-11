"""Tests for src.auth.service: hashing, sessions, user store."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.auth import service as auth_service


@pytest.fixture
def svc(tmp_path) -> auth_service.AuthService:
    return auth_service.AuthService(auth_file=tmp_path / "auth.json")


# --- Password hashing ------------------------------------------------------


def test_hash_password_verify_roundtrip():
    h = auth_service.hash_password("correct horse battery staple")
    assert h.startswith("scrypt$")
    assert auth_service.verify_password("correct horse battery staple", h)
    assert not auth_service.verify_password("wrong password!!", h)


def test_hash_password_unique_salt():
    a = auth_service.hash_password("samepass1")
    b = auth_service.hash_password("samepass1")
    assert a != b  # different salts


def test_verify_password_rejects_bad_format():
    assert not auth_service.verify_password("x", "not-a-real-hash")
    assert not auth_service.verify_password("x", "")
    assert not auth_service.verify_password("x", "scrypt$bad$dollars")


def test_hash_password_rejects_empty():
    with pytest.raises(ValueError):
        auth_service.hash_password("")


# --- User store -----------------------------------------------------------


def test_create_initial_user_then_authenticate(svc):
    assert not svc.has_user()
    svc.create_initial_user("admin", "supersecret")
    assert svc.has_user()
    token = svc.authenticate("admin", "supersecret")
    assert isinstance(token, str)
    assert svc.verify_session(token) == "admin"


def test_create_initial_user_already_setup(svc):
    svc.create_initial_user("admin", "supersecret")
    with pytest.raises(auth_service.AlreadySetup):
        svc.create_initial_user("admin2", "anothersecret")


def test_authenticate_wrong_password(svc):
    svc.create_initial_user("admin", "supersecret")
    with pytest.raises(auth_service.InvalidCredentials):
        svc.authenticate("admin", "wrong")
    with pytest.raises(auth_service.InvalidCredentials):
        svc.authenticate("nobody", "supersecret")


def test_authenticate_setup_required(svc):
    with pytest.raises(auth_service.SetupRequired):
        svc.authenticate("admin", "supersecret")


def test_change_password(svc):
    svc.create_initial_user("admin", "oldpassword")
    svc.change_password("admin", "oldpassword", "brandnewpassword")
    with pytest.raises(auth_service.InvalidCredentials):
        svc.authenticate("admin", "oldpassword")
    assert svc.authenticate("admin", "brandnewpassword")


def test_change_password_wrong_current(svc):
    svc.create_initial_user("admin", "oldpassword")
    with pytest.raises(auth_service.InvalidCredentials):
        svc.change_password("admin", "wrong", "brandnewpassword")


def test_change_password_validates_new(svc):
    svc.create_initial_user("admin", "oldpassword")
    with pytest.raises(ValueError):
        svc.change_password("admin", "oldpassword", "short")  # < 8


def test_username_validation(svc):
    with pytest.raises(ValueError):
        svc.create_initial_user("", "supersecret")
    with pytest.raises(ValueError):
        svc.create_initial_user("has space", "supersecret")
    with pytest.raises(ValueError):
        svc.create_initial_user("has/slash", "supersecret")
    # Allowed characters
    svc.create_initial_user("user.name-1_99@example", "supersecret")


def test_password_min_length(svc):
    with pytest.raises(ValueError):
        svc.create_initial_user("admin", "short")


# --- Session tokens --------------------------------------------------------


def test_verify_session_rejects_garbage(svc):
    svc.create_initial_user("admin", "supersecret")
    assert svc.verify_session(None) is None
    assert svc.verify_session("") is None
    assert svc.verify_session("no-dot") is None
    assert svc.verify_session("bad.sig") is None


def test_verify_session_rejects_tampering(svc):
    svc.create_initial_user("admin", "supersecret")
    token = svc.authenticate("admin", "supersecret")
    # Flip one character of the signature.
    head, sig = token.rsplit(".", 1)
    swapped_char = "b" if sig[0] != "b" else "c"
    tampered = head + "." + swapped_char + sig[1:]
    assert svc.verify_session(tampered) is None


def test_verify_session_expired(monkeypatch, svc):
    svc.create_initial_user("admin", "supersecret")
    # Force a 1-second TTL.
    monkeypatch.setenv("FIESTABOARD_SESSION_TTL_SECONDS", "1")
    token = svc.authenticate("admin", "supersecret")
    assert svc.verify_session(token) == "admin"
    # Simulate the clock moving forward past expiry.
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 5)
    assert svc.verify_session(token) is None


def test_persistence_across_instances(tmp_path):
    p = tmp_path / "auth.json"
    s1 = auth_service.AuthService(auth_file=p)
    s1.create_initial_user("admin", "supersecret")
    token = s1.authenticate("admin", "supersecret")

    # New instance against the same file should see the user…
    s2 = auth_service.AuthService(auth_file=p)
    assert s2.has_user()
    # …and accept tokens minted by the first instance (same signing key).
    assert s2.verify_session(token) == "admin"


def test_auth_file_perms(tmp_path):
    import stat as stat_mod

    p = tmp_path / "auth.json"
    s = auth_service.AuthService(auth_file=p)
    s.create_initial_user("admin", "supersecret")
    mode = stat_mod.S_IMODE(p.stat().st_mode)
    assert mode == 0o600


def test_is_auth_enabled(monkeypatch):
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)
    assert not auth_service.is_auth_enabled()
    for v in ("true", "True", "1", "yes", "on"):
        monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", v)
        assert auth_service.is_auth_enabled()
    for v in ("", "false", "0", "no", "off"):
        monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", v)
        assert not auth_service.is_auth_enabled()
