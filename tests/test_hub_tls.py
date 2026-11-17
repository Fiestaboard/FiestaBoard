"""Deployment TLS must fail closed and preserve each installation's identity."""

import importlib
import os
import ssl
import subprocess

import pytest


def configure(env, data, snippets):
    # Assert the missing feature explicitly so the first run is a RED test,
    # rather than aborting collection with an import error.
    assert importlib.util.find_spec("src.system.tls"), "H16 TLS startup is not implemented"
    return importlib.import_module("src.system.tls").configure_tls(env, data, snippets)


@pytest.fixture
def locations(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    snippets = tmp_path / "nginx"
    snippets.mkdir()
    return data, snippets


SELF_SIGNED = {"FIESTABOARD_TLS_MODE": "self-signed", "FIESTABOARD_TLS_HOSTS": "localhost,127.0.0.1,::1"}


def test_default_off_removes_only_stale_tls_snippet(locations):
    data, snippets = locations
    (snippets / "tls.conf").write_text("old TLS listener")
    (snippets / "frame-headers.conf").write_text("keep")
    assert configure({}, data, snippets) is None
    assert not (snippets / "tls.conf").exists()
    assert (snippets / "frame-headers.conf").read_text() == "keep"
    assert list(data.iterdir()) == []


def test_self_signed_identity_is_private_persistent_and_separate_from_legacy_cleanup(locations):
    from src.system.legacy_https import remove_legacy_https_certs

    data, snippets = locations
    cert = configure(SELF_SIGNED, data, snippets)
    key = data / "tls/server.key"
    original = (cert.read_bytes(), key.read_bytes())
    assert (data / "tls").stat().st_mode & 0o777 == 0o700
    assert key.stat().st_mode & 0o777 == 0o600
    assert cert.stat().st_mode & 0o777 == 0o644
    assert configure(SELF_SIGNED, data, snippets) == cert
    assert (cert.read_bytes(), key.read_bytes()) == original
    assert remove_legacy_https_certs(data) == 0
    assert (cert.read_bytes(), key.read_bytes()) == original
    configure({"FIESTABOARD_TLS_MODE": "off"}, data, snippets)
    assert (cert.read_bytes(), key.read_bytes()) == original


def test_reused_self_signed_public_cert_permissions_are_upgraded_without_rotation(locations):
    data, snippets = locations
    cert = configure(SELF_SIGNED, data, snippets)
    key = data / "tls/server.key"
    cert.chmod(0o600)  # Identity persisted by the initial H16 release.
    original = (cert.read_bytes(), key.read_bytes())
    assert configure(SELF_SIGNED, data, snippets) == cert
    assert cert.stat().st_mode & 0o777 == 0o644
    assert key.stat().st_mode & 0o777 == 0o600
    assert (data / "tls").stat().st_mode & 0o777 == 0o700
    assert (cert.read_bytes(), key.read_bytes()) == original


@pytest.mark.parametrize(
    "hosts",
    [
        "",
        "*.example.com",
        "a;return 200",
        "a\nDNS:evil",
        "https://hub.local",
        "a,,b",
        "-bad",
        "a" * 254,
        ",".join(f"h{i}" for i in range(33)),
    ],
)
def test_invalid_sans_fail_before_creating_identity(locations, hosts):
    data, snippets = locations
    with pytest.raises(ValueError):
        configure({**SELF_SIGNED, "FIESTABOARD_TLS_HOSTS": hosts}, data, snippets)
    assert not (data / "tls").exists()
    assert not (snippets / "tls.conf").exists()


def test_changed_hostname_requires_deliberate_rotation(locations):
    data, snippets = locations
    cert = configure(SELF_SIGNED, data, snippets)
    original = cert.read_bytes()
    with pytest.raises(ValueError):
        configure({**SELF_SIGNED, "FIESTABOARD_TLS_HOSTS": "other.example.com"}, data, snippets)
    assert cert.read_bytes() == original


@pytest.mark.parametrize("mode", ["yes", "acme", "", "SELF-SIGNED"])
def test_unknown_mode_is_not_silently_downgraded(locations, mode):
    with pytest.raises(ValueError):
        configure({"FIESTABOARD_TLS_MODE": mode}, *locations)


@pytest.mark.parametrize("kind", ["directory-link", "cert-link", "key-link", "partial"])
def test_generated_identity_rejects_symlinks_and_partial_state(locations, tmp_path, kind):
    data, snippets = locations
    outside = tmp_path / "outside"
    outside.mkdir()
    if kind == "directory-link":
        (data / "tls").symlink_to(outside, target_is_directory=True)
    else:
        tls = data / "tls"
        tls.mkdir(mode=0o700)
        (tls / "server.crt").write_text("original certificate")
        if kind != "partial":
            (tls / "server.key").write_text("original key")
            target = tls / ("server.crt" if kind == "cert-link" else "server.key")
            target.unlink()
            target.symlink_to(outside / "untouched")
    with pytest.raises(ValueError):
        configure(SELF_SIGNED, data, snippets)
    assert list(outside.iterdir()) == []


def test_custom_certificate_is_read_only_input_and_key_match_is_checked(locations, tmp_path):
    data, snippets = locations
    source_data = tmp_path / "source"
    source_data.mkdir()
    cert = configure(SELF_SIGNED, source_data, snippets)
    key = source_data / "tls/server.key"
    cert.chmod(0o600)
    original = (cert.read_bytes(), key.read_bytes(), cert.stat().st_mode, key.stat().st_mode)
    env = {
        "FIESTABOARD_TLS_MODE": "custom",
        "FIESTABOARD_TLS_CERT_FILE": str(cert),
        "FIESTABOARD_TLS_KEY_FILE": str(key),
    }
    assert configure(env, data, snippets) == cert
    assert (cert.read_bytes(), key.read_bytes(), cert.stat().st_mode, key.stat().st_mode) == original
    assert list(data.iterdir()) == []
    other_data = tmp_path / "other"
    other_data.mkdir()
    configure(SELF_SIGNED, other_data, snippets)
    with pytest.raises(ValueError):
        configure({**env, "FIESTABOARD_TLS_KEY_FILE": str(other_data / "tls/server.key")}, data, snippets)


@pytest.mark.parametrize(
    "cert,key",
    [
        ("", ""),
        ("relative.pem", "/key.pem"),
        ("/cert.pem;", "/key.pem"),
        ('/cert".pem', "/key.pem"),
        ("/missing.pem", "/missing.key"),
    ],
)
def test_invalid_custom_paths_fail_closed(locations, cert, key):
    with pytest.raises(ValueError):
        configure(
            {"FIESTABOARD_TLS_MODE": "custom", "FIESTABOARD_TLS_CERT_FILE": cert, "FIESTABOARD_TLS_KEY_FILE": key},
            *locations,
        )


@pytest.mark.parametrize("offset", [-3600, 366 * 24 * 3600])
def test_certificate_outside_validity_window_is_rejected_without_replacement(locations, monkeypatch, offset):
    import time

    data, snippets = locations
    cert = configure(SELF_SIGNED, data, snippets)
    original = cert.read_bytes()
    # Keep genuine certificate bytes; move only the verifier's wall clock to
    # before notBefore or after notAfter. OpenSSL 3.5 refuses negative -days.
    now = time.time()
    monkeypatch.setattr("src.system.tls.time.time", lambda: now + offset)
    with pytest.raises(ValueError, match="expired or not yet valid"):
        configure(SELF_SIGNED, data, snippets)
    assert cert.read_bytes() == original


def test_generation_failure_does_not_leave_partial_identity(locations, monkeypatch):
    data, snippets = locations
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(ValueError):
        configure(SELF_SIGNED, data, snippets)
    assert not (data / "tls").exists()
    assert list(data.iterdir()) == []


def test_generated_cert_can_be_loaded_as_trust_anchor(locations):
    data, snippets = locations
    cert = configure(SELF_SIGNED, data, snippets)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, data / "tls/server.key")
    assert ssl.create_default_context(cafile=str(cert)).check_hostname


def test_cli_invalid_mode_exits_nonzero_without_starting_server(tmp_path):
    result = subprocess.run(
        [os.sys.executable, "-m", "src.system.tls"],
        env={**os.environ, "FIESTABOARD_TLS_MODE": "invalid", "FIESTABOARD_DATA_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "FIESTABOARD_TLS_MODE" in result.stderr


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("nginx unavailable"),
        subprocess.TimeoutExpired(["nginx", "-t"], timeout=30),
        subprocess.CalledProcessError(1, ["nginx", "-t"], stderr="operator private diagnostics"),
    ],
)
def test_boot_nginx_validation_errors_are_bounded_and_fail_closed(monkeypatch, capsys, tmp_path, error):
    from src.system import tls

    prepared = []
    monkeypatch.setattr(tls, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(tls, "configure_tls", lambda *args: prepared.append(True))

    def reject(command, **kwargs):
        assert prepared == [True]
        assert command == ["nginx", "-t"]
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["capture_output"] and kwargs["check"]
        assert 0 < kwargs["timeout"] <= 30
        raise error

    monkeypatch.setattr(tls.subprocess, "run", reject)
    assert tls.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "[tls] nginx configuration validation failed; refusing to start services\n"
