"""Tests for src.auth.service: hashing, sessions, user store."""

from __future__ import annotations

import time

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


def test_change_password_invalidates_old_sessions(svc):
    """Stolen cookies must stop working once the password is rotated."""
    svc.create_initial_user("admin", "oldpassword")
    old_token = svc.authenticate("admin", "oldpassword")
    assert svc.verify_session(old_token) == "admin"
    svc.change_password("admin", "oldpassword", "brandnewpassword")
    # Old token is now rejected even though it hasn't expired yet.
    assert svc.verify_session(old_token) is None
    # A freshly-minted session from the new password works.
    new_token = svc.authenticate("admin", "brandnewpassword")
    assert svc.verify_session(new_token) == "admin"


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
    # Simulate the clock moving forward past expiry. _now_ms uses
    # time.time_ns under the hood, so monkeypatch that.
    real_ns = time.time_ns
    monkeypatch.setattr(time, "time_ns", lambda: real_ns() + 5 * 1_000_000_000)
    assert svc.verify_session(token) is None


def _token_expires_at_ms(token: str) -> int:
    """Pull the ``expires_at`` (ms) field out of a signed session token.

    Token layout is ``<user_b64>.<issued>.<expires>.<nonce>.<signature>``.
    """
    payload, _sig = token.rsplit(".", 1)
    _user_b64, _issued, expires_s, _nonce = payload.split(".")
    return int(expires_s)


def test_authenticate_remember_extends_ttl(svc):
    """``remember=True`` mints a token with the longer remember-me TTL."""
    svc.create_initial_user("admin", "supersecret")
    short = svc.authenticate("admin", "supersecret", remember=False)
    long = svc.authenticate("admin", "supersecret", remember=True)
    # The remembered token outlives the plain session token by roughly the
    # gap between the 7-day and 30-day defaults.
    assert _token_expires_at_ms(long) - _token_expires_at_ms(short) > 20 * 24 * 3600 * 1000
    # Both are still valid sessions for the user.
    assert svc.verify_session(short) == "admin"
    assert svc.verify_session(long) == "admin"


def test_authenticate_default_uses_session_ttl(monkeypatch, svc):
    """Default (no remember kwarg) uses the short session TTL window."""
    svc.create_initial_user("admin", "supersecret")
    monkeypatch.setenv("FIESTABOARD_SESSION_TTL_SECONDS", "60")
    monkeypatch.setenv("FIESTABOARD_REMEMBER_ME_TTL_SECONDS", "600")
    plain = svc.authenticate("admin", "supersecret")
    remembered = svc.authenticate("admin", "supersecret", remember=True)
    now_ms = auth_service._now_ms()
    # Plain token expires ~60s out; remembered ~600s out.
    assert _token_expires_at_ms(plain) - now_ms < 120 * 1000
    assert _token_expires_at_ms(remembered) - now_ms > 300 * 1000


def test_remember_me_ttl_env_override(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_REMEMBER_ME_TTL_SECONDS", "12345")
    assert auth_service._remember_me_ttl_seconds() == 12345
    # Invalid / non-positive values fall back to the default.
    monkeypatch.setenv("FIESTABOARD_REMEMBER_ME_TTL_SECONDS", "0")
    assert auth_service._remember_me_ttl_seconds() == auth_service._DEFAULT_REMEMBER_ME_TTL_SECONDS
    monkeypatch.setenv("FIESTABOARD_REMEMBER_ME_TTL_SECONDS", "notanumber")
    assert auth_service._remember_me_ttl_seconds() == auth_service._DEFAULT_REMEMBER_ME_TTL_SECONDS


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


def test_is_auth_enabled(monkeypatch, tmp_path):
    """The env var pins the mode regardless of stored preference."""
    # Isolate the singleton + stored preference from any leftover state.
    monkeypatch.setattr(auth_service, "_service", auth_service.AuthService(auth_file=tmp_path / "auth.json"))

    # Truthy env var -> always enabled.
    for v in ("true", "True", "1", "yes", "on"):
        monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", v)
        assert auth_service.is_auth_enabled()
        assert auth_service.auth_mode() == "enabled"
    # Explicit falsy env var -> always disabled.
    for v in ("false", "0", "no", "off"):
        monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", v)
        assert not auth_service.is_auth_enabled()
        assert auth_service.auth_mode() == "disabled"
    # Unset env var, no stored preference -> *undecided*, which is
    # treated as "auth required" so the install is never silently open.
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)
    assert auth_service.auth_mode() == "undecided"
    assert auth_service.is_auth_enabled()


def test_auth_mode_uses_stored_preference(monkeypatch, tmp_path):
    """When the env var is unset, the stored ``auth_pref`` wins."""
    svc = auth_service.AuthService(auth_file=tmp_path / "auth.json")
    monkeypatch.setattr(auth_service, "_service", svc)
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)

    assert auth_service.auth_mode() == "undecided"

    svc.set_auth_preference("disabled")
    assert auth_service.auth_mode() == "disabled"
    assert not auth_service.is_auth_enabled()

    svc.set_auth_preference("enabled")
    assert auth_service.auth_mode() == "enabled"
    assert auth_service.is_auth_enabled()

    svc.set_auth_preference(None)
    assert auth_service.auth_mode() == "undecided"


def test_env_var_overrides_stored_preference(monkeypatch, tmp_path):
    svc = auth_service.AuthService(auth_file=tmp_path / "auth.json")
    monkeypatch.setattr(auth_service, "_service", svc)
    svc.set_auth_preference("enabled")
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    assert auth_service.auth_mode() == "disabled"
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    svc.set_auth_preference("disabled")
    assert auth_service.auth_mode() == "enabled"


def test_create_initial_user_records_preference(svc):
    """Calling setup is an explicit "auth on" decision."""
    assert svc.get_auth_preference() is None
    svc.create_initial_user("admin", "supersecret")
    assert svc.get_auth_preference() == "enabled"


def test_change_username_renames_and_rotates_sessions(svc):
    svc.create_initial_user("admin", "supersecret")
    old_token = svc.authenticate("admin", "supersecret")
    assert svc.verify_session(old_token) == "admin"

    new = svc.change_username("admin", "supersecret", "owner")
    assert new == "owner"
    # Old cookie no longer accepted (watermark bumped).
    assert svc.verify_session(old_token) is None
    # The renamed user authenticates under the new name.
    new_token = svc.authenticate("owner", "supersecret")
    assert svc.verify_session(new_token) == "owner"


def test_change_username_wrong_password(svc):
    svc.create_initial_user("admin", "supersecret")
    with pytest.raises(auth_service.InvalidCredentials):
        svc.change_username("admin", "wrong", "owner")
    # Username unchanged after a failed attempt.
    assert svc.get_user("admin") is not None
    assert svc.get_user("owner") is None


def test_change_username_validates_new_name(svc):
    svc.create_initial_user("admin", "supersecret")
    with pytest.raises(ValueError):
        svc.change_username("admin", "supersecret", "bad name")  # space


def test_change_username_unknown_user(svc):
    svc.create_initial_user("admin", "supersecret")
    with pytest.raises(auth_service.InvalidCredentials):
        svc.change_username("ghost", "supersecret", "owner")


def test_set_auth_preference_persists_across_instances(tmp_path):
    p = tmp_path / "auth.json"
    s1 = auth_service.AuthService(auth_file=p)
    s1.set_auth_preference("disabled")
    s2 = auth_service.AuthService(auth_file=p)
    assert s2.get_auth_preference() == "disabled"


def test_set_auth_preference_rejects_garbage(svc):
    with pytest.raises(ValueError):
        svc.set_auth_preference("maybe")
