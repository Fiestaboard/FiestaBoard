"""Prepare opt-in nginx TLS before any server starts.

Deployment configuration only: this does not restore the retired HTTPS Beta
setting. HTTP/ingress keep their existing listener and routing. Certificates
live outside the legacy cleanup directory, and identity rotation is explicit.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

from src.paths import get_data_dir

# Mozilla intermediate v5.7 OpenSSL cipher list (TLS 1.2 only):
# https://ssl-config.mozilla.org/guidelines/5.7.json
# TLS 1.3 uses the library defaults. DHE suites remain inactive unless nginx
# has DH parameters configured; ECDHE needs no additional parameter file.
TLS12_CIPHERS = (
    "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:"
    "DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305"
)


def _openssl(*args: str) -> str:
    """Run bounded, noninteractive OpenSSL without shell/config interpolation."""
    try:
        result = subprocess.run(
            ["openssl", *args], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=True
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # OpenSSL diagnostics can contain operator-supplied paths; never dump
        # input contents or key material into startup logs.
        raise ValueError("TLS certificate operation failed; check certificate files and OpenSSL availability") from exc
    return result.stdout


def _hosts(raw: str) -> list[tuple[str, str]]:
    values = raw.split(",")
    if len(values) > 32:
        raise ValueError("FIESTABOARD_TLS_HOSTS supports at most 32 DNS names or IP addresses")
    hosts = []
    for value in values:
        value = value.strip()
        try:
            host = ("IP", str(ipaddress.ip_address(value)))
        except ValueError:
            if (
                not value
                or len(value) > 253
                or not all(
                    re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in value.split(".")
                )
            ):
                raise ValueError("FIESTABOARD_TLS_HOSTS requires comma-separated DNS names or IP addresses") from None
            host = ("DNS", value.lower())
        if host not in hosts:
            hosts.append(host)
    return hosts


def _config_path(path: Path) -> str:
    # Quoted nginx paths may include spaces, but no variables, directives,
    # quote escapes, or control characters. Use fixed filename extensions
    # only for generated material; custom certificate files need no suffix.
    text = str(path)
    if not path.is_absolute() or not re.fullmatch(r"[A-Za-z0-9_./ -]+", text):
        raise ValueError("TLS certificate paths must be absolute paths using letters, numbers, spaces, /, _, - or .")
    return f'"{text}"'


def _validate_pair(cert: Path, key: Path) -> None:
    _config_path(cert)
    _config_path(key)
    if not cert.is_file() or not key.is_file():
        raise ValueError("TLS requires a readable certificate and private key")
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # Returning an empty password rejects encrypted keys without ever
        # prompting on stdin (which would otherwise hang container startup).
        context.load_cert_chain(cert, key, password=lambda: "")
        dates = _openssl("x509", "-in", str(cert), "-noout", "-startdate", "-enddate")
        parsed = dict(line.split("=", 1) for line in dates.splitlines())
        now = time.time()
        if not ssl.cert_time_to_seconds(parsed["notBefore"]) <= now < ssl.cert_time_to_seconds(parsed["notAfter"]):
            raise ValueError("TLS certificate is expired or not yet valid; install a current certificate")
    except (OSError, ssl.SSLError, KeyError) as exc:
        raise ValueError(
            "TLS certificate/key cannot be loaded; use a matching PEM chain and unencrypted private key"
        ) from exc


def _self_signed(data_dir: Path, hosts: list[tuple[str, str]]) -> tuple[Path, Path]:
    directory = data_dir / "tls"
    cert, key = directory / "server.crt", directory / "server.key"
    _config_path(cert)
    if directory.is_symlink():
        raise ValueError("TLS identity directory must not be a symlink")
    if directory.exists():
        if not directory.is_dir() or any(p.is_symlink() or not p.is_file() for p in (cert, key)):
            raise ValueError("TLS identity is incomplete or contains symlinks; restore it or deliberately rotate it")
        if directory.stat().st_mode & 0o077 or key.stat().st_mode & 0o077:
            raise ValueError("TLS identity requires directory mode 0700 and private key mode 0600")
    else:
        # Publish both files together. A failed generation cannot leave a
        # partial identity that the next boot could silently replace.
        data_dir.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".tls-", dir=data_dir))
        try:
            temporary_key, temporary_cert = temporary / "server.key", temporary / "server.crt"
            temporary_key.touch(mode=0o600)
            _openssl(
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-sha256",
                "-nodes",
                "-days",
                "365",
                "-subj",
                "/CN=FiestaBoard hub",
                "-addext",
                "basicConstraints=critical,CA:FALSE",
                "-addext",
                "keyUsage=critical,digitalSignature,keyEncipherment",
                "-addext",
                "extendedKeyUsage=serverAuth",
                "-addext",
                "subjectAltName=" + ",".join(f"{kind}:{value}" for kind, value in hosts),
                "-keyout",
                str(temporary_key),
                "-out",
                str(temporary_cert),
            )
            temporary_key.chmod(0o600)
            temporary_cert.chmod(0o644)
            _validate_pair(temporary_cert, temporary_key)
            temporary.rename(directory)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    _validate_pair(cert, key)
    for kind, value in hosts:
        output = _openssl("x509", "-in", str(cert), "-noout", "-checkip" if kind == "IP" else "-checkhost", value)
        # x509's checkhost/checkip print a mismatch but still exit successfully
        # on supported OpenSSL versions, so check the documented result text.
        if "does match certificate" not in output:
            raise ValueError("TLS certificate does not cover FIESTABOARD_TLS_HOSTS; deliberately rotate the identity")
    # Upgrade persisted H16 certificates too, without changing the identity
    # or relaxing the private directory/key permissions. Custom inputs are
    # never changed by this self-signed-only path.
    cert.chmod(0o644)
    return cert, key


def configure_tls(environ: Mapping[str, str], data_dir: Path, snippet_dir: Path) -> Path | None:
    """Write the TLS listener only after validating its complete configuration.

    Any error aborts boot; callers must not catch it and launch plaintext
    services. Disabling TLS removes only its snippet and keeps identity files.
    """
    mode = environ.get("FIESTABOARD_TLS_MODE", "off")
    snippet = snippet_dir / "tls.conf"
    if mode == "off":
        snippet.unlink(missing_ok=True)
        return None
    if mode == "self-signed":
        cert, key = _self_signed(data_dir, _hosts(environ.get("FIESTABOARD_TLS_HOSTS", "")))
    elif mode == "custom":
        cert = Path(environ.get("FIESTABOARD_TLS_CERT_FILE", ""))
        key = Path(environ.get("FIESTABOARD_TLS_KEY_FILE", ""))
        _validate_pair(cert, key)
    else:
        raise ValueError("FIESTABOARD_TLS_MODE must be off, self-signed or custom")
    snippet_dir.mkdir(parents=True, exist_ok=True)
    contents = (
        "# Generated at startup; HTTP and HA ingress remain available.\n"
        "listen 3443 ssl;\nlisten [::]:3443 ssl;\n"
        f"ssl_certificate {_config_path(cert)};\nssl_certificate_key {_config_path(key)};\n"
        f"ssl_protocols TLSv1.2 TLSv1.3;\nssl_ciphers {TLS12_CIPHERS};\n"
        "ssl_session_tickets off;\n"
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=snippet_dir, prefix=".tls-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
        temporary.replace(snippet)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return cert


def main() -> int:
    """Entrypoint runs this as the same unprivileged user as nginx."""
    try:
        configure_tls(os.environ, get_data_dir(), Path("/etc/nginx/fiestaboard"))
    except (ValueError, OSError) as exc:
        print(f"[tls] {exc}", file=sys.stderr)
        return 1
    try:
        # Check the complete active config as nginx's runtime user, after all
        # snippets are written/removed and before entrypoint starts services.
        subprocess.run(
            ["nginx", "-t"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=True
        )
    except (OSError, subprocess.SubprocessError):
        # nginx diagnostics may contain operator-supplied paths or directives.
        # Operators can run nginx -t directly to inspect those privately.
        print("[tls] nginx configuration validation failed; refusing to start services", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
