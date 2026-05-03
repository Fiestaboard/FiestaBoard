"""Self-signed HTTPS certificate management for the FiestaBoard container.

This module supports the opt-in **HTTPS (Beta)** setting. When the user
enables HTTPS we generate a long-lived self-signed certificate that nginx
serves on port 3000 inside the container. The cert files live under
``/app/data/certs`` so they persist across container rebuilds via the
existing ``./data:/app/data`` bind mount.

Each FiestaBoard instance generates its own keypair and certificate; we
never bake a shared private key into the image.

The cert includes Subject Alternative Names for ``localhost``,
``127.0.0.1``, ``fiestaboard.local`` (the default mDNS name), the
container hostname, and any IPv4 addresses we can detect on the host
network. Browsers will show a "not trusted" warning since the cert is
self-signed -- this is expected for the beta and is documented in the UI.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Directory holding the cert + key. Lives under /app/data so the bind
# mount in docker-compose preserves it across container rebuilds.
DEFAULT_CERT_DIR = Path("/app/data/certs")

CERT_FILENAME = "fiestaboard.crt"
KEY_FILENAME = "fiestaboard.key"

# 10 years -- self-signed cert; no rotation infrastructure needed.
CERT_VALID_DAYS = 3650


def _cert_dir() -> Path:
    """Resolve the cert directory.

    Honours the ``FIESTABOARD_CERT_DIR`` env var so tests can use a
    temporary directory without writing to ``/app/data``.
    """
    override = os.environ.get("FIESTABOARD_CERT_DIR")
    if override:
        return Path(override)
    return DEFAULT_CERT_DIR


def cert_paths() -> tuple[Path, Path]:
    """Return ``(cert_path, key_path)``."""
    base = _cert_dir()
    return base / CERT_FILENAME, base / KEY_FILENAME


def cert_exists() -> bool:
    """Return True when both the cert and key files are present."""
    cert, key = cert_paths()
    return cert.is_file() and key.is_file()


def _detect_lan_ips() -> List[str]:
    """Best-effort discovery of IPv4 addresses on this host.

    Used to populate ``IP:`` Subject Alternative Names so the cert is
    accepted when the user browses by LAN IP. Failures are non-fatal --
    we always include 127.0.0.1 elsewhere.
    """
    ips: list[str] = []
    try:
        # Default-route trick: the OS picks the interface whose address
        # would be used to reach an external host. We never actually
        # send a packet because UDP connect() doesn't.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError as e:
        logger.debug("LAN IP detection via default route failed: %s", e)

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            # getaddrinfo tuple shape: (family, type, proto, canonname, sockaddr)
            # where sockaddr for AF_INET is (host, port).
            sockaddr = info[4]
            addr = sockaddr[0]
            if addr and addr not in ips:
                ips.append(addr)
    except (OSError, socket.gaierror) as e:
        logger.debug("LAN IP detection via hostname failed: %s", e)

    # Filter loopback (we add 127.0.0.1 separately) and obvious junk.
    return [ip for ip in ips if ip and not ip.startswith("127.")]


def _build_san_entries(extra_hosts: Optional[List[str]] = None) -> List[str]:
    """Build the list of subjectAltName entries for the cert.

    Always includes ``localhost``, ``127.0.0.1``, ``fiestaboard.local``,
    and the container hostname. Detected LAN IPs are appended.
    """
    dns_names: list[str] = ["localhost", "fiestaboard.local"]
    ip_addrs: list[str] = ["127.0.0.1"]

    try:
        host = socket.gethostname()
        if host and host not in dns_names:
            dns_names.append(host)
        # Some setups expose `<host>.local` too.
        if host and not host.endswith(".local"):
            local_name = f"{host}.local"
            if local_name not in dns_names:
                dns_names.append(local_name)
    except OSError as e:
        logger.debug("Hostname lookup failed: %s", e)

    for ip in _detect_lan_ips():
        if ip not in ip_addrs:
            ip_addrs.append(ip)

    if extra_hosts:
        for entry in extra_hosts:
            if not entry:
                continue
            # Heuristic: looks like an IPv4 literal -> IP SAN, else DNS.
            parts = entry.split(".")
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                if entry not in ip_addrs:
                    ip_addrs.append(entry)
            elif entry not in dns_names:
                dns_names.append(entry)

    san: list[str] = [f"DNS:{n}" for n in dns_names]
    san.extend(f"IP:{ip}" for ip in ip_addrs)
    return san


def _openssl_available() -> bool:
    return shutil.which("openssl") is not None


def generate_cert(
    extra_hosts: Optional[List[str]] = None,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Generate a self-signed certificate + key into the cert directory.

    Args:
        extra_hosts: Additional DNS names or IPv4 literals to include as
            SubjectAltName entries.
        overwrite: When False (default), reuse the existing cert if both
            files are already present. When True, regenerate.

    Returns:
        Tuple of (cert_path, key_path).

    Raises:
        RuntimeError: If openssl is unavailable or the subprocess fails.
    """
    cert_path, key_path = cert_paths()
    if not overwrite and cert_path.is_file() and key_path.is_file():
        logger.info("Existing FiestaBoard cert found at %s; reusing.", cert_path)
        return cert_path, key_path

    if not _openssl_available():
        raise RuntimeError(
            "openssl CLI not found; cannot generate self-signed certificate."
        )

    cert_path.parent.mkdir(parents=True, exist_ok=True)

    san_entries = _build_san_entries(extra_hosts)
    logger.info(
        "Generating self-signed FiestaBoard certificate (SANs: %s)",
        ", ".join(san_entries),
    )

    # Build a minimal openssl config with the SAN extension. Using a
    # temp file keeps the command line short and avoids quoting issues.
    config_text = (
        "[req]\n"
        "distinguished_name = dn\n"
        "x509_extensions = v3_req\n"
        "prompt = no\n"
        "[dn]\n"
        "CN = fiestaboard.local\n"
        "O = FiestaBoard\n"
        "[v3_req]\n"
        "basicConstraints = CA:FALSE\n"
        "keyUsage = digitalSignature, keyEncipherment\n"
        "extendedKeyUsage = serverAuth\n"
        f"subjectAltName = {','.join(san_entries)}\n"
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cnf", delete=False
    ) as cfg_file:
        cfg_file.write(config_text)
        cfg_path = cfg_file.name

    try:
        cmd = [
            "openssl", "req", "-x509",
            "-newkey", "rsa:2048",
            "-sha256",
            "-nodes",
            "-days", str(CERT_VALID_DAYS),
            "-keyout", str(key_path),
            "-out", str(cert_path),
            "-config", cfg_path,
        ]
        try:
            result = subprocess.run(  # noqa: S603 - args list, no shell
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            logger.debug("openssl stderr: %s", result.stderr.strip())
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"openssl failed to generate cert: {e.stderr or e.stdout}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("openssl timed out generating cert") from e
    finally:
        try:
            os.unlink(cfg_path)
        except OSError as e:
            logger.debug("Failed to remove temporary openssl config %s: %s", cfg_path, e)

    # Lock down the private key permissions. The cert is fine world-readable.
    try:
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)
    except OSError as e:
        logger.warning("Failed to chmod cert files: %s", e)

    logger.info("Certificate written to %s", cert_path)
    return cert_path, key_path


def remove_cert() -> bool:
    """Delete the cert + key files. Returns True if anything was removed."""
    removed = False
    for path in cert_paths():
        try:
            if path.is_file():
                path.unlink()
                removed = True
                logger.info("Removed %s", path)
        except OSError as e:
            logger.warning("Failed to remove %s: %s", path, e)
    return removed
