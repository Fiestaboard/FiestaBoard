"""Tests for the secrets-encryption helper (src.security.secrets)."""

from __future__ import annotations

import stat

import pytest

from src.security import secrets as secrets_mod


@pytest.fixture(autouse=True)
def _isolated_key(tmp_path, monkeypatch):
    """Point the module at a temp data dir and clear any cached cipher."""
    # Use env var path: deterministic across tests.
    monkeypatch.setattr(secrets_mod, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(secrets_mod, "_KEY_PATH", tmp_path / ".secret_key")
    monkeypatch.delenv("FIESTABOARD_SECRET_KEY", raising=False)
    secrets_mod._reset_for_tests()
    yield
    secrets_mod._reset_for_tests()


def test_encrypt_decrypt_roundtrip():
    token = secrets_mod.encrypt_secret("hunter2")
    assert token.startswith(secrets_mod.ENCRYPTED_PREFIX)
    assert "hunter2" not in token
    assert secrets_mod.decrypt_secret(token) == "hunter2"


def test_decrypt_passthrough_for_plaintext():
    # Migration helper: legacy plaintext values come through unchanged.
    assert secrets_mod.decrypt_secret("plain-api-key") == "plain-api-key"


def test_encrypt_idempotent():
    a = secrets_mod.encrypt_secret("s3cret")
    b = secrets_mod.encrypt_secret(a)
    assert a == b


def test_empty_string_not_encrypted():
    assert secrets_mod.encrypt_secret("") == ""
    assert secrets_mod.decrypt_secret("") == ""


def test_is_encrypted():
    assert secrets_mod.is_encrypted(secrets_mod.encrypt_secret("x"))
    assert not secrets_mod.is_encrypted("x")
    assert not secrets_mod.is_encrypted(None)
    assert not secrets_mod.is_encrypted(123)


def test_key_file_perms(tmp_path):
    secrets_mod.encrypt_secret("anything")
    key_path = secrets_mod._KEY_PATH
    assert key_path.exists()
    mode = stat.S_IMODE(key_path.stat().st_mode)
    # 0600
    assert mode == 0o600


def test_env_var_overrides_file(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("FIESTABOARD_SECRET_KEY", key)
    secrets_mod._reset_for_tests()
    token = secrets_mod.encrypt_secret("from-env")
    assert secrets_mod.decrypt_secret(token) == "from-env"


def test_invalid_env_key_raises(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_SECRET_KEY", "not-a-real-key")
    secrets_mod._reset_for_tests()
    with pytest.raises(RuntimeError):
        secrets_mod.encrypt_secret("x")


def test_decrypt_fails_clearly_on_wrong_key(monkeypatch):
    from cryptography.fernet import Fernet

    # Encrypt with one key…
    monkeypatch.setenv("FIESTABOARD_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    secrets_mod._reset_for_tests()
    token = secrets_mod.encrypt_secret("topsecret")
    # …then swap to a different key.
    monkeypatch.setenv("FIESTABOARD_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    secrets_mod._reset_for_tests()
    with pytest.raises(ValueError):
        secrets_mod.decrypt_secret(token)


def test_rotate_key_reencrypts():
    from cryptography.fernet import Fernet

    t1 = secrets_mod.encrypt_secret("alpha")
    t2 = secrets_mod.encrypt_secret("beta")

    new_key = Fernet.generate_key()
    rotated = secrets_mod.rotate_key(new_key, values=[t1, "plain", t2, ""])
    assert rotated[1] == "plain"
    assert rotated[3] == ""
    # New tokens decrypt under the new key (which is now the active one).
    assert secrets_mod.decrypt_secret(rotated[0]) == "alpha"
    assert secrets_mod.decrypt_secret(rotated[2]) == "beta"


def test_type_errors():
    with pytest.raises(TypeError):
        secrets_mod.encrypt_secret(123)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        secrets_mod.decrypt_secret(123)  # type: ignore[arg-type]
