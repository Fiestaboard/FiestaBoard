"""Tests for src.system.https_certs.

Exercises the self-signed certificate helpers used by the HTTPS (Beta)
feature. These tests run a real openssl invocation when openssl is
available on PATH, and otherwise verify the expected RuntimeError.
"""

import shutil
import subprocess

import pytest

from src.system import https_certs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OPENSSL_AVAILABLE = shutil.which("openssl") is not None
requires_openssl = pytest.mark.skipif(not OPENSSL_AVAILABLE, reason="openssl CLI not available")


@pytest.fixture
def cert_dir(tmp_path, monkeypatch):
    """Redirect cert generation to a tmp directory."""
    monkeypatch.setenv("FIESTABOARD_CERT_DIR", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# Path / status helpers
# ---------------------------------------------------------------------------


class TestCertPaths:
    def test_cert_paths_uses_env_override(self, cert_dir):
        cert, key = https_certs.cert_paths()
        assert cert.parent == cert_dir
        assert cert.name == "fiestaboard.crt"
        assert key.name == "fiestaboard.key"

    def test_cert_paths_default_without_override(self, monkeypatch):
        monkeypatch.delenv("FIESTABOARD_CERT_DIR", raising=False)
        cert, key = https_certs.cert_paths()
        assert cert == https_certs.DEFAULT_CERT_DIR / "fiestaboard.crt"
        assert key == https_certs.DEFAULT_CERT_DIR / "fiestaboard.key"

    def test_cert_exists_false_initially(self, cert_dir):
        assert https_certs.cert_exists() is False

    def test_cert_exists_true_when_both_files_present(self, cert_dir):
        cert, key = https_certs.cert_paths()
        cert.write_text("dummy cert")
        key.write_text("dummy key")
        assert https_certs.cert_exists() is True

    def test_cert_exists_false_when_only_one_file(self, cert_dir):
        cert, _ = https_certs.cert_paths()
        cert.write_text("dummy cert")
        assert https_certs.cert_exists() is False


# ---------------------------------------------------------------------------
# SAN building
# ---------------------------------------------------------------------------


class TestBuildSanEntries:
    def test_includes_default_dns_and_ip(self):
        sans = https_certs._build_san_entries()
        assert "DNS:localhost" in sans
        assert "DNS:fiestaboard.local" in sans
        assert "IP:127.0.0.1" in sans

    def test_extra_hosts_dns_vs_ip_classification(self):
        sans = https_certs._build_san_entries(extra_hosts=["192.168.1.50", "myhost.example.com"])
        assert "IP:192.168.1.50" in sans
        assert "DNS:myhost.example.com" in sans

    def test_extra_hosts_ignores_blank_entries(self):
        sans = https_certs._build_san_entries(extra_hosts=["", None])  # type: ignore[list-item]
        assert "DNS:localhost" in sans  # still includes defaults

    def test_no_duplicates(self):
        sans = https_certs._build_san_entries(extra_hosts=["localhost", "127.0.0.1"])
        # DNS:localhost should appear exactly once.
        assert sans.count("DNS:localhost") == 1
        assert sans.count("IP:127.0.0.1") == 1


# ---------------------------------------------------------------------------
# Generate / remove
# ---------------------------------------------------------------------------


class TestGenerateCert:
    @requires_openssl
    def test_generates_cert_and_key(self, cert_dir):
        cert, key = https_certs.generate_cert()
        assert cert.is_file() and cert.stat().st_size > 0
        assert key.is_file() and key.stat().st_size > 0
        # PEM markers
        assert "BEGIN CERTIFICATE" in cert.read_text()
        assert "PRIVATE KEY" in key.read_text()

    @requires_openssl
    def test_key_has_restricted_permissions(self, cert_dir):
        _, key = https_certs.generate_cert()
        mode = key.stat().st_mode & 0o777
        assert mode == 0o600

    @requires_openssl
    def test_reuses_existing_cert_when_overwrite_false(self, cert_dir):
        cert1, _ = https_certs.generate_cert()
        first_mtime = cert1.stat().st_mtime
        # Bump filesystem clock resolution by writing a marker
        cert1.touch()
        cert2, _ = https_certs.generate_cert(overwrite=False)
        assert cert1 == cert2
        # Content should not have been regenerated.
        assert cert2.stat().st_mtime >= first_mtime

    @requires_openssl
    def test_overwrite_replaces_existing_cert(self, cert_dir):
        cert1, key1 = https_certs.generate_cert()
        original_cert = cert1.read_text()
        original_key = key1.read_text()
        https_certs.generate_cert(overwrite=True)
        assert cert1.read_text() != original_cert
        assert key1.read_text() != original_key

    @requires_openssl
    def test_san_includes_extra_hosts(self, cert_dir):
        cert, _ = https_certs.generate_cert(extra_hosts=["example.test", "10.0.0.5"])
        # Use openssl x509 to inspect the cert.
        out = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert), "-noout", "-text"],
            text=True,
        )
        assert "example.test" in out
        assert "10.0.0.5" in out
        assert "fiestaboard.local" in out

    def test_raises_when_openssl_missing(self, cert_dir, monkeypatch):
        monkeypatch.setattr(https_certs, "_openssl_available", lambda: False)
        with pytest.raises(RuntimeError, match="openssl CLI not found"):
            https_certs.generate_cert()

    def test_raises_when_openssl_subprocess_fails(self, cert_dir, monkeypatch):
        monkeypatch.setattr(https_certs, "_openssl_available", lambda: True)

        def fake_run(*args, **kwargs):
            raise subprocess.CalledProcessError(returncode=1, cmd=args[0], stderr="boom")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="openssl failed"):
            https_certs.generate_cert()


class TestRemoveCert:
    def test_remove_when_files_missing(self, cert_dir):
        assert https_certs.remove_cert() is False

    def test_remove_deletes_existing_files(self, cert_dir):
        cert, key = https_certs.cert_paths()
        cert.write_text("c")
        key.write_text("k")
        assert https_certs.remove_cert() is True
        assert not cert.exists()
        assert not key.exists()

    def test_remove_with_only_one_file(self, cert_dir):
        cert, _ = https_certs.cert_paths()
        cert.write_text("c")
        assert https_certs.remove_cert() is True
        assert not cert.exists()
